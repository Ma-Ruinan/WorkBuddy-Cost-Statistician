"""WorkBuddy JSONL adapter. No database, directory time or outer status substitutes."""
import collections
import json
from pathlib import Path
import re
from common import (DataError, assign_users, date_selected, in_scope, iso, number, segment)

PRODUCT = 'WorkBuddy'
METHOD = '�ỰJSONL��usage��conversationRequestId��messageIdȥ�أ����߼���ڲ����������˳��룻present_files·��ȥ�ز����������'


def default_source(args):
    if args.db:
        raise DataError('WorkBuddyʹ�ûỰJSONL����ʹ��--logs-root')
    return Path(args.logs_root).resolve() if args.logs_root else Path.home()/'.workbuddy'/'projects'


def usage_value(pd, evidence):
    u = pd['usage']
    if u.get('requests') != 1:
        raise DataError('usage.requests����1�����Ⱥ˲���ü������壺'+evidence)
    inp = number(u['inputTokens'], 'usage.inputTokens') if 'inputTokens' in u else None
    out = number(u['outputTokens'], 'usage.outputTokens') if 'outputTokens' in u else None
    details = u.get('inputTokensDetails')
    cache = sum(number(x['cached_tokens'], 'cached_tokens') for x in details) if isinstance(details, list) and details and all('cached_tokens' in x for x in details) else None
    raw = pd.get('rawUsage') or {}
    if 'prompt_tokens' in raw and inp is not None and raw['prompt_tokens'] != inp:
        raise DataError('rawUsage��usage��������һ�£�'+evidence)
    if 'completion_tokens' in raw and out is not None and raw['completion_tokens'] != out:
        raise DataError('rawUsage��usage�������һ�£�'+evidence)
    raw_cache = (raw.get('prompt_tokens_details') or {}).get('cached_tokens')
    if raw_cache is not None and cache is not None and raw_cache != cache:
        raise DataError('rawUsage��usage��������һ�£�'+evidence)
    if inp is not None and out is not None and u.get('totalTokens') is not None and u['totalTokens'] != inp+out:
        raise DataError('usage.totalTokens�ϼƲ�һ�£�'+evidence)
    return {'input': inp, 'output': out, 'cache': cache, 'calls': 1,
            'model': pd.get('model'), 'evidence': evidence,
            'warning': '�����ֶβ�����' if None in (inp,out,cache) else None}


def collect(source, tasks, args, mapping, tz):
    result, excluded = [], []
    paths = [source] if source.is_file() else sorted(source.rglob('*.jsonl'))
    if not paths:
        raise DataError('δ�ҵ��ỰJSONL��'+str(source))
    for path in paths:
        rows = []
        for lineno, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if line.strip():
                r = json.loads(line); r['_line'] = lineno; rows.append(r)
        users = []
        for r in rows:
            if r.get('type') == 'message' and r.get('role') == 'user':
                text = '\n'.join(x.get('text', '') for x in r.get('content', []) if isinstance(x, dict))
                q = re.search(r'<user_query>(.*?)</user_query>', text, re.S)
                users.append({'id': r['id'], 'time': r['timestamp'], 'text': q.group(1) if q else text, 'raw': r})
        if not users:
            continue
        directory = users[0]['raw'].get('cwd') or next((r['cwd'] for r in rows if r.get('cwd')), '')
        if not in_scope(directory, args.workspace):
            continue
        session = users[0]['raw'].get('sessionId') or next((r['sessionId'] for r in rows if r.get('sessionId')), None)
        if not session:
            raise DataError('JSONLδ�ҵ�sessionId��'+str(path))
        if args.session and session not in args.session:
            continue
        for user, task, root, kind, until in assign_users(users, session, tasks, mapping, excluded, str(path), strip_scene=True):
            root_time = next(u['time'] for u in users if u['id'] == root)
            if not date_selected(root_time, args, tz):
                continue
            start = user['time']; rr = [r for r in rows if start <= r.get('timestamp', -1) < until]
            finished = [r for r in rr if r.get('type') == 'message' and r.get('role') == 'assistant' and r.get('status') == 'completed']
            end = max((r['timestamp'] for r in finished), default=None)
            if end is not None and end > until:
                raise DataError('�û�����ִ�������ص�����˲���Ϣ�빤�߹�����'+session)
            usages, seq = {}, {}
            for r in rr:
                pd = r.get('providerData', {})
                if not pd.get('usage'):
                    continue
                if not pd.get('conversationRequestId') or not pd.get('messageId'):
                    raise DataError('��������ȱ���������Ϣ��ʶ��'+str(path)+':'+str(r['_line']))
                key = (pd['conversationRequestId'], pd['messageId'])
                if key in usages and usages[key]['raw'] != pd['usage']:
                    raise DataError('��ͬ���ñ�ʶ���ֲ�ͬ��������˲��Ƿ�Ϊ�ۼƸ���')
                step = pd.get('stepSeq')
                seqkey = (pd['conversationRequestId'], step)
                if step is not None and seqkey in seq and seq[seqkey] != key:
                    raise DataError('ͬһ������Ŷ�Ӧ���ģ����Ϣ������ֱ���ۼ�')
                if step is not None: seq[seqkey] = key
                usages[key] = {'raw': pd['usage'], 'value': usage_value(pd, f'JSONL:{r["_line"]}'), 'request':key[0], 'message':key[1], 'step':step}
            calls, results = {}, {}
            for r in rr:
                if r.get('type') not in ('function_call', 'function_call_result'):
                    continue
                cid = r.get('callId')
                if not cid:
                    raise DataError('���߼�¼ȱ��callId��'+str(path)+':'+str(r['_line']))
                target = calls if r['type'] == 'function_call' else results
                if cid in target:
                    old = {k:v for k,v in target[cid].items() if k != '_line'}
                    new = {k:v for k,v in r.items() if k != '_line'}
                    if old != new:
                        raise DataError('�ظ����߼�¼���ݱ仯����˲飺'+cid)
                target[cid] = r
            if set(results) - set(calls):
                raise DataError('���߽��δ�ҵ����ã���־Ƭ�β�����')
            tools, deliveries = [], []
            for cid, call in calls.items():
                r = results.get(cid, {}); tr = r.get('providerData', {}).get('toolResult', {})
                raw = tr.get('rawResponse', {}); code = raw.get('exitCode')
                if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
                    raise DataError('�����˳������ͱ仯��'+cid)
                status = r.get('status')
                failed = status in ('error', 'failed') or bool(raw.get('is_error')) or bool(tr.get('isError')) or code not in (None,0)
                msg = str(raw.get('error') or tr.get('content') or r.get('output', '')) if failed else ''
                tools.append({'id':cid, 'name':call['name'], 'status':status, 'exit_code':code,
                              'failed':failed, 'time':iso(r.get('timestamp', call['timestamp']),tz),
                              'message':msg[:1600] if failed else '', 'message_truncated':failed and len(msg)>1600,
                              'evidence':f'JSONL:{r.get("_line",call["_line"])}'})
                if call['name'] == 'present_files' and status == 'completed' and not failed:
                    deliveries.append({'id':cid, 'input':call.get('arguments')})
            final_text = '\n'.join(x.get('text','') for x in finished[-1].get('content',[]) if isinstance(x,dict)) if finished else ''
            value = segment(PRODUCT, task, root, kind, user['id'], session, start, end,
                            directory, path, [x['value'] for x in usages.values()], tools, deliveries,
                            'WebSearch', tz, extra=re.search(r'@scene#\d+:.*', user['text'], re.S).group(0) if re.search(r'@scene#\d+:', user['text']) else None,
                            final_text=final_text, errors_complete=set(calls)==set(results))
            value['usage_identities'] = [{k:v for k,v in x.items() if k not in ('raw','value')} for x in usages.values()]
            result.append(value)
    return result, excluded


if __name__ == '__main__':
    from common import run_cli
    raise SystemExit(run_cli(PRODUCT, collect, default_source, METHOD))
