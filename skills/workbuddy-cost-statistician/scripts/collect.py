"""WorkBuddy JSONL task trees; parent summaries never substitute for child usage."""
import collections
import json
from pathlib import Path
import re
from common import DataError,assign_users,date_selected,in_scope,iso,number,segment
from agent_tree import enrich

PRODUCT='WorkBuddy'
METHOD='主会话按题目关联；通过Agent结果的subAgent标识递归读取子日志；模型请求与工具调用跨执行主体去重；不重复累计父摘要'

def default_source(args):
    if args.db:raise DataError('WorkBuddy使用JSONL，请使用--logs-root')
    return Path(args.logs_root).resolve() if args.logs_root else Path.home()/'.workbuddy'/'projects'

def usage_value(pd,evidence):
    u=pd['usage']
    if u.get('requests')!=1:raise DataError('usage.requests不是1，需核查调用语义：'+evidence)
    inp=number(u['inputTokens'],'inputTokens') if 'inputTokens' in u else None
    out=number(u['outputTokens'],'outputTokens') if 'outputTokens' in u else None
    details=u.get('inputTokensDetails')
    cache=sum(number(x['cached_tokens'],'cached_tokens') for x in details) if isinstance(details,list) and details and all('cached_tokens' in x for x in details) else None
    raw=pd.get('rawUsage') or {}
    for key,value in [('prompt_tokens',inp),('completion_tokens',out)]:
        if key in raw and value is not None and raw[key]!=value:raise DataError('rawUsage与usage不一致：'+evidence)
    rc=(raw.get('prompt_tokens_details') or {}).get('cached_tokens')
    if rc is not None and cache is not None and rc!=cache:raise DataError('缓存字段不一致：'+evidence)
    if None not in (inp,out) and u.get('totalTokens') is not None and u['totalTokens']!=inp+out:raise DataError('Token合计不一致：'+evidence)
    return dict(input=inp,output=out,cache=cache,calls=1,model=pd.get('model'),evidence=evidence,
                warning='用量字段不完整' if None in (inp,out,cache) else None)

def user_records(rows):
    result=[]
    for r in rows:
        if r.get('type')=='message' and r.get('role')=='user':
            pd=r.get('providerData') or {}
            if pd.get('isMeta') is True or pd.get('startsNewUserRequest') is False:continue
            text='\n'.join(x.get('text','') for x in r.get('content',[]) if isinstance(x,dict))
            query=re.search(r'<user_query>(.*?)</user_query>',text,re.S)
            result.append(dict(id=r['id'],time=r['timestamp'],text=query.group(1) if query else text,raw=r))
    return result

class WorkBuddyTree:
    def __init__(self,source,tz):
        self.tz=tz;self.nodes={};self.rows={};self.graph=collections.defaultdict(list);self.times=collections.defaultdict(list)
        paths=[source,*sorted((source.parent/source.stem/'subagents').rglob('*.jsonl'))] if source.is_file() else sorted(source.rglob('*.jsonl'))
        if not paths:raise DataError('未找到会话JSONL：'+str(source))
        aliases={};orphans=[]
        for path in paths:
            rows=[]
            for lineno,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
                if line.strip():
                    r=json.loads(line);r['_line']=lineno;rows.append(r)
            key=str(path.resolve());users=user_records(rows)
            session=next((r.get('sessionId') for r in rows if r.get('sessionId')),None)
            directory=next((r.get('cwd') for r in rows if r.get('cwd')),'')
            child='subagents' in path.parts
            if child:
                at=path.parts.index('subagents');folder=Path(*path.parts[:at]);tree_root=str((folder.parent/(folder.name+'.jsonl')).resolve())
            else:tree_root=key
            self.nodes[key]=dict(session=session or path.stem,source=key,directory=directory,
                created=min((r.get('timestamp',0) for r in rows),default=0),child=child,tree_root=tree_root)
            self.rows[key]=rows
            for alias in {path.stem,session} - {None}:
                alias_key=(tree_root,alias)
                if alias_key in aliases and aliases[alias_key]!=key:raise DataError('子日志标识对应多个文件：'+str(alias))
                aliases[alias_key]=key
            if child:orphans.append(key)
        linked=set();roles=collections.defaultdict(list)
        for node,rows in self.rows.items():
            results={r.get('callId'):r for r in rows if r.get('type')=='function_call_result'}
            for r in rows:
                if r.get('type')!='function_call' or r.get('name') not in ('Agent','Task','spawn_agent'):continue
                result=results.get(r.get('callId'),{});tr=result.get('providerData',{}).get('toolResult') or {}
                sa=tr.get('subAgent') or {};raw=tr.get('rawResponse') or {};args=r.get('arguments') or {}
                if isinstance(args,str):args=json.loads(args)
                target=sa.get('sessionId') or sa.get('agentId') or raw.get('agent_id') or raw.get('agentId') or args.get('resume')
                if not target:
                    match=re.search(r'agentId\s*:\s*([A-Za-z0-9_-]+)',str(result.get('output','')))
                    target=match.group(1) if match else None
                child=aliases.get((self.nodes[node]['tree_root'],target)) if target else None
                if target and not child:child='missing:'+str(target)
                self.graph[node].append(dict(child=child,time=r['timestamp'],call=r.get('callId'),
                    evidence=node+'#JSONL:'+str(r['_line']),not_started=result.get('status') in ('error','failed') and not target))
                if child:linked.add(child);self.times[child].append(r['timestamp'])
                for role in {args.get('name'),(sa.get('descriptor') or {}).get('role')}-{None}:
                    roles[(self.nodes[node]['tree_root'],role)].append((r['timestamp'],child))
        # A later test can continue a named child with SendMessage instead of Agent(resume).
        for node,rows in self.rows.items():
            results={r.get('callId'):r for r in rows if r.get('type')=='function_call_result'}
            for r in rows:
                if r.get('type')!='function_call' or r.get('name')!='SendMessage':continue
                args=r.get('arguments') or {}
                if isinstance(args,str):args=json.loads(args)
                if args.get('type')!='message':continue
                recipient=args.get('recipient');tree_root=self.nodes[node]['tree_root']
                known=[(time,target) for time,target in roles[(tree_root,recipient)] if time<=r['timestamp']]
                target=max(known,key=lambda x:x[0])[1] if known else aliases.get((tree_root,recipient))
                # Replies to the parent do not launch another child execution.
                if target==node or (target in self.nodes and not self.nodes[target]['child']):continue
                if not target and self.nodes[node]['child']:continue
                result=results.get(r.get('callId'),{})
                self.graph[node].append(dict(child=target,time=r['timestamp'],call=r.get('callId'),
                    evidence=node+'#JSONL:'+str(r['_line']),resume=True,not_started=result.get('status') in ('error','failed') and not target))
                if target:linked.add(target);self.times[target].append(r['timestamp'])
        for node in orphans:
            if node not in linked:
                root=self.nodes[node]['tree_root']
                if root in self.nodes:
                    self.graph[root].append(dict(child=None,time=self.nodes[node]['created'],call=None,
                        evidence=node+'#unlinked-subagent-file'))
        for values in self.graph.values():values.sort(key=lambda e:(e['time'],e.get('child') or ''))

    def edges(self,node):return self.graph[node]
    def next_edge_time(self,node,at):return min((t for t in self.times[node] if t>at),default=float('inf'))

    def piece(self,node,start,until,task='CHILD',root='CHILD',kind='子Agent',user='CHILD'):
        info=self.nodes[node];rr=[r for r in self.rows[node] if start<=r.get('timestamp',-1)<until]
        finished=[r for r in rr if r.get('type')=='message' and r.get('role')=='assistant' and r.get('status')=='completed']
        end=max((r['timestamp'] for r in finished),default=None)
        usages={};seq={}
        for r in rr:
            pd=r.get('providerData') or {}
            if not pd.get('usage'):continue
            if not pd.get('conversationRequestId') or not pd.get('messageId'):raise DataError('有用量但缺少请求标识：'+node+':'+str(r['_line']))
            key=(pd['conversationRequestId'],pd['messageId']);step=pd.get('stepSeq');seqkey=(key[0],step)
            if key in usages and usages[key]['raw']!=pd['usage']:raise DataError('相同模型标识出现不同用量')
            if step is not None and seqkey in seq and seq[seqkey]!=key:raise DataError('同一步骤序号对应多个模型消息')
            if step is not None:seq[seqkey]=key
            value=usage_value(pd,node+'#JSONL:'+str(r['_line']))
            value.update(_identity='WorkBuddy#request:'+key[0]+'#message:'+key[1],_time_ms=r['timestamp'],agent_session=info['session'])
            # Repeated appearances of a model response may be attached to multiple tool calls.
            if key not in usages:usages[key]=dict(raw=pd['usage'],value=value)
        if finished and not usages:
            evidence=node+'#JSONL:'+str(finished[-1]['_line'])
            usages[('missing',evidence)]={'raw':{},'value':dict(input=None,output=None,cache=None,calls=None,model=None,
                evidence=evidence,warning='已完成子执行或主执行缺少模型用量记录',
                _identity='WorkBuddy#missing-usage:'+evidence,_time_ms=finished[-1]['timestamp'],agent_session=info['session'])}
        calls={};results={}
        for r in rr:
            if r.get('type') not in ('function_call','function_call_result'):continue
            cid=r.get('callId')
            if not cid:raise DataError('工具记录缺少callId：'+node+':'+str(r['_line']))
            target=calls if r['type']=='function_call' else results
            if cid in target:
                old={k:v for k,v in target[cid].items() if k not in ('_line','id','parentId')}
                new={k:v for k,v in r.items() if k not in ('_line','id','parentId')}
                if old!=new:raise DataError('重复工具记录内容变化：'+cid)
            else:target[cid]=r
        if set(results)-set(calls):raise DataError('工具结果未找到调用：'+node)
        tools=[];deliveries=[]
        for cid,call in calls.items():
            r=results.get(cid,{});tr=r.get('providerData',{}).get('toolResult') or {};raw=tr.get('rawResponse') or {};code=raw.get('exitCode')
            if code is not None and (not isinstance(code,int) or isinstance(code,bool)):raise DataError('工具退出码类型变化：'+cid)
            status=r.get('status');failed=status in ('error','failed') or bool(raw.get('is_error')) or bool(tr.get('isError')) or code not in (None,0)
            msg=str(raw.get('error') or tr.get('content') or r.get('output','')) if failed else ''
            tools.append(dict(id=cid,name=call['name'],status=status,exit_code=code,failed=failed,
                time=iso(r.get('timestamp',call['timestamp']),self.tz),message=msg[:1600],message_truncated=len(msg)>1600,
                evidence=node+'#JSONL:'+str(r.get('_line',call['_line'])),
                _identity='WorkBuddy#call:'+cid+'#time:'+str(call['timestamp']),_time_ms=call['timestamp'],agent_session=info['session'],result_complete=bool(r) and status in ('completed','error','failed')))
            if call['name']=='present_files' and status=='completed' and not failed:deliveries.append(dict(id=cid,input=call.get('arguments')))
        text='\n'.join(x.get('text','') for x in finished[-1].get('content',[]) if isinstance(x,dict)) if finished else ''
        user_row=next((u for u in user_records(self.rows[node]) if u['id']==user),None)
        scene=re.search(r'@scene#\d+:.*',user_row['text'],re.S) if user_row else None
        value=segment(PRODUCT,task,root,kind,user,info['session'],start,end,info['directory'],node,
            [u['value'] for u in usages.values()],tools,deliveries,'WebSearch',self.tz,
            extra=scene.group(0) if scene else None,final_text=text,errors_complete=all(t['result_complete'] for t in tools))
        value['_node']=node;value['_until']=until
        assistants=[r for r in rr if r.get('type')=='message' and r.get('role')=='assistant']
        value['_terminal']=bool(finished) and (not assistants or assistants[-1].get('status')=='completed') and all(t['result_complete'] for t in tools)
        return value

def collect(source,tasks,args,mapping,tz):
    store=WorkBuddyTree(source,tz);excluded=[];segments=[]
    for node,info in store.nodes.items():
        if info['child']:continue
        if not in_scope(info['directory'],args.workspace) or (args.session and info['session'] not in args.session):continue
        users=user_records(store.rows[node])
        for user,task,root,kind,until in assign_users(users,info['session'],tasks,mapping,excluded,node,strip_scene=True):
            if not date_selected(next(u['time'] for u in users if u['id']==root),args,tz):continue
            segments.append(store.piece(node,user['time'],until,task,root,kind,user['id']))
    enrich(segments,store,'WebSearch')
    included={e['node'] for s in segments for e in s['agent_executions']}
    for node,info in store.nodes.items():
        if info['child'] and node not in included:excluded.append(dict(session=info['session'],source=node,reason='未关联到所选父任务的子日志',time_ms=info['created']))
    return segments,excluded

if __name__=='__main__':
    from common import run_cli
    raise SystemExit(run_cli(PRODUCT,collect,default_source,METHOD))
