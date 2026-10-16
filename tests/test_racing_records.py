"""Prevent incomplete or no-model runs from entering real API win-rate tables."""
import importlib.util,json,pathlib,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('racing_selected',ROOT/'scripts/racing.py');racing=importlib.util.module_from_spec(spec);spec.loader.exec_module(racing)
class EvaluationRecords(unittest.TestCase):
    def fixture(self,out,summary,final):
        recipe=json.loads((ROOT/'recipes/racing.json').read_text());recipe['args']['seed']=304
        (out/'manifest.json').write_text(json.dumps({'recipe':recipe,'hypothesis':'fixture; no model calls'}))
        summary['digest']='fixture';final['state_sha']='fixture'
        (out/'replay_check.json').write_text(json.dumps({'state_sha':'fixture'}))
        (out/'summary.json').write_text(json.dumps(summary));(out/'service').mkdir();(out/'service/final.json').write_text(json.dumps(final));(out/'service/replay_check.json').write_text(json.dumps({'state_sha':'fixture'}));return recipe
    def test_preflight_cannot_be_relabelled_as_api_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','won':True,'driver':'camera-reference-executor-preflight-NOT-GPT','model':None,'artificial_delay':True},{'valid_trial':True,'deterministic':True,'player_modes':{'A':'oracle'}})
            rec=racing.record_run(out,'eval',recipe)
            self.assertFalse(rec['real_time_api_acceptance']);self.assertIsNone(rec['won'])
    def test_complete_subscription_loss_is_retained(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','auth':'chatgpt','won':False,'replay_matches':True},{})
            rec=racing.record_run(out,'simulate',recipe)
            self.assertEqual(rec['execution_integrity'],'verified');self.assertIs(rec['won'],False);self.assertFalse(rec['real_time_api_acceptance'])
    def test_abort_cannot_be_counted_as_clean_loss_or_success(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','auth':'chatgpt','won':True,'replay_matches':True},{})
            rec=racing.record_run(out,'simulate',recipe,returncode=1)
            self.assertEqual(rec['execution_integrity'],'incomplete_or_unverified');self.assertIsNone(rec['won'])
    def test_api_acceptance_requires_intact_images_and_replay_hash(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);recipe=self.fixture(out,{'status':'complete','won':True,'model':'gpt-6.1-sol','service_tier':'ultrafast','artificial_delay':False,'calls':1},{'valid_trial':True,'deterministic':True,'player_modes':{'A':'model'}})
            call=out/'decision_00000';call.mkdir();image=call/'image_0.png';image.write_bytes(b'fixture pixels, no provider')
            (call/'input.json').write_text(json.dumps({'image_sha256':[racing.digest(image)]}))
            (call/'result.json').write_text(json.dumps({'model':'gpt-6.1-sol','service_tier':'ultrafast'}))
            self.assertTrue(racing.record_run(out,'eval',recipe)['real_time_api_acceptance'])
            image.write_bytes(b'changed pixels')
            self.assertIsNone(racing.record_run(out,'eval',recipe)['won'])
            (out/'service/replay_check.json').write_text('{"state_sha":"wrong"}')
            self.assertFalse(racing.record_run(out,'eval',recipe)['replay_hash_matches'])
if __name__=='__main__':unittest.main()
