import unittest
import zipfile
import test_agent_tree as fixtures
import report


class ExcelSelectionTests(unittest.TestCase):
    def test_unmatched_question_not_exported_and_failed_run_retained(self):
        case=fixtures.AgentTreeTests();case.setUp()
        try:
            case.tasks.append(dict(id='UNMATCHED_ID',name='UNMATCHED_NAME',prompt='Not executed.'))
            data=case.collect(case.fixture())
            data['meta']=dict(timezone='Asia/Shanghai',method='test',source='synthetic',collected_at='test',read_twice_equal=True,snapshot_sha256='test')
            data['runs'][0]['status']='记录不完整'
            path=case.root/'report.xlsx';report.excel_report(data,path)
            with zipfile.ZipFile(path) as z:
                text=''.join(z.read(n).decode('utf8') for n in z.namelist() if n.endswith('.xml'))
            self.assertNotIn('UNMATCHED_ID',text);self.assertNotIn('UNMATCHED_NAME',text)
            self.assertIn('记录不完整',text)
            self.assertEqual(data['missing_tasks'],['UNMATCHED_ID'])
        finally:case.tearDown()
