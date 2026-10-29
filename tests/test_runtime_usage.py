import datetime as dt
import json
import unittest
import test_agent_tree as fixtures
from runtime_usage import RuntimeUsage
from common import DataError


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.AgentTreeTests();self.case.setUp()
        self.logs=self.case.root/'runtime';self.logs.mkdir()
        self.case.args.runtime_logs=str(self.logs)
        self.tz=dt.timezone(dt.timedelta(hours=8))

    def tearDown(self):self.case.tearDown()

    def line(self,mid,kind='compress',sid='root',inp=100,out=20,at=10000,request='req',flag='done'):
        when=dt.datetime.fromtimestamp((self.case.at+at)/1000,self.tz).strftime('%Y/%m/%d %H:%M:%S.%f')[:-3]
        return '['+when+'] [Info] [pid=12] qua.end: '+json.dumps(dict(message_id=mid,conversation_id=sid,
            conversation_request_id=request,request_type=kind,prompt_tokens=str(inp),completion_tokens=str(out),finish_flag=flag,model='test'))+'\n'

    def test_auxiliary_usage_in_task_and_titles_separate(self):
        src=self.case.fixture();baseline=self.case.collect(src)
        (self.logs/'app.log').write_text(self.line('c')+self.line('w','webfetch',sid='c1',at=6000)+
            self.line('chat','chat',inp=0,out=0)+self.line('title','conversation_topic',sid='topic',at=1000),encoding='utf8')
        result=self.case.collect(src)['runs'][0];old=baseline['runs'][0]
        self.assertEqual(result['values']['input_tokens'],old['values']['input_tokens']+200)
        self.assertEqual(result['values']['output_tokens'],old['values']['output_tokens']+40)
        self.assertEqual(result['values']['tool_calls'],old['values']['tool_calls'])
        self.assertIsNone(result['values']['cache_rate'])
        # One process logged root and child: title ownership is ambiguous.
        self.assertEqual(result['application_usage'],[])

    def test_rotation_duplicates_and_title(self):
        text=self.line('chat','chat')+self.line('title','conversation_topic',sid='topic')
        (self.logs/'app.log').write_text(text,encoding='utf8')
        (self.logs/'app.log.1').write_text(text,encoding='utf8')
        reader=RuntimeUsage(self.logs,self.tz)
        self.assertEqual(len(reader.records),2)
        self.assertEqual(len(reader.titles({'root'},self.case.at,self.case.at+20000)),1)
        self.assertEqual(reader.select('root',self.case.at+11000,self.case.at+20000),[])

    def test_conflicting_duplicate_rejected(self):
        (self.logs/'app.log').write_text(self.line('c')+self.line('c',inp=101),encoding='utf8')
        with self.assertRaises(DataError):RuntimeUsage(self.logs,self.tz)

    def test_missing_logs_keep_known_values_and_warn(self):
        result=self.case.collect(self.case.fixture())['runs'][0]
        self.assertIsNotNone(result['values']['input_tokens'])
        self.assertTrue(any('辅助模型成本可能未覆盖' in w for w in result['warnings']))

    def test_failed_billable_and_zero_interrupted_requests(self):
        (self.logs/'app.log').write_text(self.line('paid',flag='error')+self.line('empty',flag='manualStop',inp=0,out=0),encoding='utf8')
        rows=RuntimeUsage(self.logs,self.tz).select('root',self.case.at,self.case.at+20000)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['input'],100);self.assertEqual(rows[0]['calls'],0)

    def test_jsonl_runtime_overlap_is_not_counted_twice(self):
        src=self.case.fixture();baseline=self.case.collect(src)['runs'][0]
        u=baseline['usage_records'][0];key=u['_identity'];req=key.split('#request:')[1].split('#message:')[0];mid=key.split('#message:')[1]
        (self.logs/'app.log').write_text(self.line(mid,'chat',sid=u['agent_session'],inp=u['input'],out=u['output'],at=u['_time_ms']-self.case.at,request=req),encoding='utf8')
        actual=self.case.collect(src)['runs'][0]
        self.assertEqual(actual['values'],baseline['values'])

if __name__=='__main__':unittest.main()
