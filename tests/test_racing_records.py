"""Prevent incomplete or no-model runs from entering real API win-rate tables."""
import importlib.util,json,pathlib,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('racing_selected',ROOT/'scripts/racing.py');racing=importlib.util.module_from_spec(spec);spec.loader.exec_module(racing)
class EvaluationRecords(unittest.TestCase):
    def test_cli_keeps_subscription_default_and_writes_the_shared_record(self):
        """Long-lived process boundary: a retained complete loss remains a completed simulation."""
        with tempfile.TemporaryDirectory() as directory:
            out=pathlib.Path(directory)/'run'
            def driver(command, **kwargs):
                self.assertEqual(command[2],'sim')
                out.mkdir()
                self.fixture(out,{'status':'complete','auth':'chatgpt','won':False,'replay_matches':True},{})
                return SimpleNamespace(returncode=0)
            with patch.dict('os.environ',{'RACING_ENV_ROOT':directory}), patch.object(racing.subprocess,'run',side_effect=driver):
                racing.main(['simulate','--seed','304','--output',str(out)])
            record=json.loads((out/'evaluation-record.json').read_text())
            self.assertEqual((record['provider'],record['clock'],record['status']),('subscription','virtual','completed'))
            self.assertFalse(record['summary']['won'])

    def test_budget_cli_uses_the_named_ceiling_and_preserves_an_existing_ledger(self):
        """Long-lived monetary boundary: creating a budget cannot reset previous charges."""
        with tempfile.TemporaryDirectory() as directory:
            ledger=pathlib.Path(directory)/'ledger.json'
            argv=['budget','--ledger',str(ledger),'--budget-usd','30']
            racing.main(argv)
            before=ledger.read_bytes()
            self.assertEqual(json.loads(before)['limit_usd'],30)
            with self.assertRaises(FileExistsError):
                racing.main(argv)
            self.assertEqual(ledger.read_bytes(),before)

    def fixture(self,out,summary,final):
        recipe=json.loads((ROOT/'recipes/racing.json').read_text());recipe['args']['seed']=304
        (out/'manifest.json').write_text(json.dumps({'recipe':recipe,'hypothesis':'fixture; no model calls'}))
        summary['digest']='fixture';final['state_sha']='fixture'
        (out/'replay_check.json').write_text(json.dumps({'state_sha':'fixture'}))
        (out/'summary.json').write_text(json.dumps(summary));(out/'service').mkdir();(out/'service/final.json').write_text(json.dumps(final));(out/'service/replay_check.json').write_text(json.dumps({'state_sha':'fixture'}));return recipe
    def test_preflight_cannot_be_relabelled_as_api_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','won':True,'driver':'camera-reference-executor-preflight-NOT-GPT','model':None,'artificial_delay':True},{'valid_trial':True,'deterministic':True,'player_modes':{'A':'oracle'}})
            rec=racing.evaluation_record(out,'eval')
            self.assertFalse(rec['real_time_api_acceptance']);self.assertIsNone(rec['won'])
    def test_complete_subscription_loss_is_retained(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','auth':'chatgpt','won':False,'replay_matches':True},{})
            rec=racing.evaluation_record(out,'simulate')
            self.assertEqual(rec['execution_integrity'],'verified');self.assertIs(rec['won'],False);self.assertFalse(rec['real_time_api_acceptance'])
    def test_abort_cannot_be_counted_as_clean_loss_or_success(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','auth':'chatgpt','won':True,'replay_matches':True},{})
            rec=racing.evaluation_record(out,'simulate',returncode=1)
            self.assertEqual(rec['execution_integrity'],'incomplete_or_unverified');self.assertIsNone(rec['won'])
    def test_api_acceptance_requires_intact_images_and_replay_hash(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','won':True,'model':'gpt-6.1-sol','service_tier':'ultrafast','artificial_delay':False,'calls':1},{'valid_trial':True,'deterministic':True,'player_modes':{'A':'model'}})
            call=out/'decision_00000';call.mkdir();image=call/'image_0.png';image.write_bytes(b'fixture pixels, no provider')
            (call/'input.json').write_text(json.dumps({'image_sha256':[racing.digest(image)]}))
            (call/'result.json').write_text(json.dumps({'model':'gpt-6.1-sol','service_tier':'ultrafast'}))
            self.assertTrue(racing.evaluation_record(out,'eval')['real_time_api_acceptance'])
            image.write_bytes(b'changed pixels')
            self.assertIsNone(racing.evaluation_record(out,'eval')['won'])
            (out/'service/replay_check.json').write_text('{"state_sha":"wrong"}')
            self.assertFalse(racing.evaluation_record(out,'eval')['replay_hash_matches'])
if __name__=='__main__':unittest.main()
