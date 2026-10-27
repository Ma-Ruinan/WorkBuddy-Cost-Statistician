"""Observable accounting across internal recovery, metadata and log formats."""
import hashlib
import json
import unittest
import test_agent_tree as fixtures
import collect as adapter
import common


class CollectionTests(unittest.TestCase):
    def setUp(self):self.case=fixtures.AgentTreeTests();self.case.setUp()
    def tearDown(self):self.case.tearDown()

    def rows(self,path):return list(adapter.log_records(path))
    def write(self,path,rows):
        path.write_text('\n'.join(json.dumps({k:v for k,v in r.items() if k!='_line'}) for r in rows),encoding='utf8')

    def test_auto_summary_and_recovery_keep_later_usage_in_same_run(self):
        self.case.nodes['root']['models'].append(('later-model',10000,18000,100,200,20))
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root.jsonl';rows=self.rows(path)
        for uid,when,fields in [('summary',5000,{'isSummary':True,'isCompacted':True}),('recovery',5100,{})]:
            rows.append(dict(id=uid,timestamp=self.case.at+when,type='message',role='user',content=[{'text':'Internal recovery.'}],
                             providerData={'isCompactInternal':True,**fields}))
        self.write(path,sorted(rows,key=lambda r:r['timestamp']))
        actual=self.case.collect(source)
        self.assertEqual(len(actual['runs']),1);self.assertEqual(actual['runs'][0]['segment_count'],1)
        self.assertEqual(actual['runs'][0]['values'],baseline['runs'][0]['values'])
        self.assertEqual(actual['summary'],baseline['summary'])

    def test_compacted_real_question_is_not_dropped_without_internal_flag(self):
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root.jsonl';rows=self.rows(path)
        rows[0]['providerData']={'startsNewUserRequest':True,'isCompacted':True}
        self.write(path,rows);self.assertEqual(self.case.collect(source)['runs'][0]['values'],baseline['runs'][0]['values'])

    def test_unmarked_new_user_remains_a_boundary(self):
        source=self.case.fixture();path=source/'root.jsonl';rows=self.rows(path)
        rows.append(dict(id='another-user',timestamp=self.case.at+10000,type='message',role='user',content=[{'text':'A different question.'}]))
        self.write(path,sorted(rows,key=lambda r:r['timestamp']))
        actual=self.case.collect(source)
        self.assertTrue(any(x.get('message')=='another-user' for x in actual['excluded']))
        self.assertLess(actual['runs'][0]['end_ms'] or 0,self.case.at+20000)

    def test_quoted_scene_before_question_preserves_all_metrics(self):
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root.jsonl';rows=self.rows(path)
        rows[0]['content'][0]['text']='@scene#50:"Research" '+self.case.tasks[0]['prompt']
        self.write(path,rows);actual=self.case.collect(source)['runs'][0]
        self.assertEqual(actual['values'],baseline['runs'][0]['values'])
        self.assertIn('@scene#50:',str(actual['conditions']));self.assertNotIn(self.case.tasks[0]['prompt'],str(actual['conditions']))

    def test_escaped_quoted_scene_can_follow_question(self):
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root.jsonl';rows=self.rows(path)
        rows[0]['content'][0]['text']+=r' @scene#50:\"Research\"'
        self.write(path,rows);self.assertEqual(self.case.collect(source)['runs'][0]['values'],baseline['runs'][0]['values'])

    def test_scene_on_continue_does_not_lose_the_next_segment(self):
        self.case.nodes['root']['users'].append(('root-u2',40000,'继续'))
        self.case.nodes['root']['models'].append(('root-m2',40500,60000,100,300,10))
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root.jsonl';rows=self.rows(path)
        next(r for r in rows if r['id']=='root-u2')['content'][0]['text']='@scene#50:"Research" 继续'
        self.write(path,rows);actual=self.case.collect(source)
        self.assertEqual(len(actual['runs']),1);self.assertEqual(actual['runs'][0]['segment_count'],2)
        self.assertEqual(actual['runs'][0]['values'],baseline['runs'][0]['values'])

    def test_attachment_references_preserve_exact_question_and_conditions(self):
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root.jsonl';rows=self.rows(path)
        attachment=str(self.case.workspace/'intermediate.txt')
        rows[0]['content'][0]['text']='@scene#50:"Research" @"'+attachment+'" '+self.case.tasks[0]['prompt']
        self.write(path,rows);actual=self.case.collect(source)['runs'][0]
        self.assertEqual(actual['values'],baseline['runs'][0]['values']);self.assertIn(attachment,str(actual['conditions']))

    def test_attachment_does_not_allow_a_different_question_to_match(self):
        source=self.case.fixture();path=source/'root.jsonl';rows=self.rows(path)
        rows[0]['content'][0]['text']='@"input.txt" Entirely different question.'
        self.write(path,rows);self.assertEqual(self.case.collect(source)['runs'],[])

    def test_deferred_child_search_is_classified_without_double_counting(self):
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root/subagents/agent-c1.jsonl';rows=self.rows(path)
        call=next(r for r in rows if r.get('type')=='function_call' and r.get('callId')=='search1-1')
        call['name']='DeferExecuteTool';call['arguments']={'toolName':'domain_search','params':{'query':'Synthetic query.'}}
        self.write(path,rows);actual=self.case.collect(source)['runs'][0]
        self.assertEqual(actual['values'],baseline['runs'][0]['values'])
        tool=next(t for t in actual['tools'] if t['id']=='search1-1')
        self.assertTrue(tool['failed']);self.assertEqual(tool['name'],'DeferExecuteTool');self.assertEqual(tool['effective_name'],'domain_search')

    def test_other_deferred_tool_is_not_inferred_to_be_search(self):
        source=self.case.fixture();path=source/'root/subagents/agent-c1.jsonl';rows=self.rows(path)
        call=next(r for r in rows if r.get('type')=='function_call' and r.get('callId')=='search1-0')
        call['name']='DeferExecuteTool';call['arguments']={'toolName':'fetch_document'}
        self.write(path,rows);actual=self.case.collect(source)['runs'][0]
        self.assertEqual(actual['values']['search_calls'],5);self.assertEqual(actual['values']['tool_calls'],11)

    def test_multiline_tool_output_keeps_costs_and_physical_evidence_lines(self):
        source=self.case.fixture();baseline=self.case.collect(source);path=source/'root/subagents/agent-c1.jsonl';rows=self.rows(path)
        result=next(r for r in rows if r.get('type')=='function_call_result');result['output']='first line\nsecond line'
        self.write(path,rows);path.write_text(path.read_text(encoding='utf8').replace('first line\\nsecond line','first line\nsecond line'),encoding='utf8')
        before=hashlib.sha256(path.read_bytes()).hexdigest();actual=self.case.collect(source)['runs'][0]
        self.assertEqual(actual['values'],baseline['runs'][0]['values']);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
        last=self.rows(path)[-1]
        physical=next(i for i,line in enumerate(path.read_text(encoding='utf8').splitlines(),1) if last['id'] in line)
        self.assertEqual(last['_line'],physical)

    def test_outside_workspace_malformed_logs_do_not_abort_selected_task(self):
        source=self.case.fixture();baseline=self.case.collect(source);self.case.args.session=None
        outside=source/'outside.jsonl';header=dict(id='outside-u',type='message',role='user',timestamp=self.case.at,sessionId='outside',cwd=str(self.case.root/'outside-workspace'))
        outside.write_text(json.dumps(header)+'\n{"truncated":',encoding='utf8')
        child=source/'outside/subagents/bad.jsonl';child.parent.mkdir(parents=True);child.write_text('{broken',encoding='utf8')
        self.assertEqual(self.case.collect(source)['runs'][0]['values'],baseline['runs'][0]['values'])

    def test_selected_truncated_child_is_not_silently_ignored(self):
        source=self.case.fixture();path=source/'root/subagents/agent-c1.jsonl'
        path.write_text(path.read_text(encoding='utf8')+'\n{"truncated":',encoding='utf8')
        with self.assertRaisesRegex(common.DataError,'agent-c1.*JSONL'):
            self.case.collect(source)


if __name__=='__main__':unittest.main()
