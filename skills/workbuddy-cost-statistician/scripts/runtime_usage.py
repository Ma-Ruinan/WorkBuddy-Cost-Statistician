"""Read model telemetry alongside conversation JSONL; never infer usage amounts."""
import collections
import datetime as dt
import json
from pathlib import Path
import re
from common import DataError


class RuntimeUsage:
    def __init__(self, source, tz):
        self.records = []; self.tz = tz; self.issues=[]
        paths = [source] if source.is_file() else sorted(source.rglob('*.log*')) if source.exists() else []
        seen = {}
        for path in paths:
            if not path.is_file(): continue
            with path.open(encoding='utf-8-sig', errors='replace') as stream:
                for line_no, line in enumerate(stream, 1):
                    if 'qua.end: ' not in line: continue
                    try:
                        data = json.loads(line.split('qua.end: ', 1)[1])
                        match = re.search(r'^\[([\d/]+ [\d:.]+)\].*?\[pid=(\d+)\]', line)
                        if not match: raise ValueError('missing timestamp')
                        at = int(dt.datetime.strptime(match[1], '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=tz).timestamp()*1000)
                    except (ValueError, TypeError):
                        self.issues.append((line, str(path)+'#line:'+str(line_no)))
                        continue
                    if not data.get('message_id'): continue
                    key = 'WorkBuddy#request:'+data.get('conversation_request_id','')+'#message:'+data['message_id']
                    # Zero-usage interrupted streams are not completed model calls.
                    usage = []
                    for field in ('prompt_tokens', 'completion_tokens'):
                        raw = str(data.get(field, ''))
                        usage.append(int(raw) if raw.isdigit() else None)
                    completed=data.get('finish_flag')=='done'
                    if not completed and not any(v for v in usage if v is not None): continue
                    record = dict(input=usage[0], output=usage[1], cache=None, calls=int(completed),
                        model=data.get('model'), evidence=str(path)+'#line:'+str(line_no),
                        warning=None, _identity=key, _time_ms=at, agent_session=data.get('conversation_id'),
                        cost_kind=data.get('request_type','unknown'), completed=completed,
                        _pid=match[2], _log=str(path), _process_day=(str(path.parent),match[1][:10],match[2]))
                    # Cache usage is not published by this telemetry schema.
                    prior = seen.get(key)
                    if prior and (prior['input'],prior['output']) != tuple(usage):
                        raise DataError('运行日志重复请求的用量冲突：'+record['evidence'])
                    if not prior: seen[key]=record
        self.records = list(seen.values())

    def select(self, session, start, until):
        return [dict(r) for r in self.records if r['agent_session']==session
                and start<=r['_time_ms']<until and r['cost_kind']!='conversation_topic']

    def titles(self, sessions, start, end):
        # Topic requests have separate conversation IDs. Only associate a process
        # when its chat telemetry proves one session in this physical log.
        owners=collections.defaultdict(set)
        for r in self.records:
            if r['cost_kind']=='chat': owners[r['_process_day']].add(r['agent_session'])
        return [dict(r) for r in self.records if r['cost_kind']=='conversation_topic'
                and start<=r['_time_ms']<=end and len(owners[r['_process_day']])==1
                and owners[r['_process_day']]<=sessions]


def default_logs(source):
    for parent in (source, *source.parents):
        if parent.name=='projects': return parent.parent/'logs'
    return source.parent/'logs'
