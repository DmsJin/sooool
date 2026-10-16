import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from research.native_envelope import effective_subset
from research.run_episode import DecisionPool, run, validate_episode_effort
from research.subscription import SubscriptionClient, checked_native_thread, validate_subscription_effort
from research.policies import make_prompt, STRATEGIES
from research.wire_schema import decision_schema


class SubscriptionEffortTests(unittest.TestCase):
    def test_historical_default_and_supported_choices(self):
        self.assertEqual(validate_subscription_effort(), 'low')
        self.assertEqual(validate_episode_effort({'provider':'subscription'}), 'low')
        self.assertEqual(validate_episode_effort({'provider':'subscription','effort':'medium'}), 'medium')
        for value in ('high', None, True, 1, 'MEDIUM'):
            with self.assertRaises(ValueError):
                validate_subscription_effort(value)

    def test_effort_aliases_keep_task_prompt_and_schema_byte_identical(self):
        pairs=[('tracking_dodge_safe_intercept_v2','tracking_dodge_safe_intercept_medium_v11'),
               ('tracking_dodge_mechanics_v10','tracking_dodge_mechanics_medium_v11')]
        observation={'image_frames':[31,61,91],'held':[0,1,1,0],
                     'visual_memory':[{'frame':1,'boss':[224,86]}]}
        profile={'p50_s':2.28,'p95_s':2.95,'control_age_p50_s':2.20,'control_age_p95_s':2.57}
        for source,alias in pairs:
            self.assertIs(STRATEGIES[source],STRATEGIES[alias])
            self.assertEqual(json.dumps(decision_schema(source,1,48)),json.dumps(decision_schema(alias,1,48)))
            for wait in (False,True):
                for intro in (0,135):
                    ob={**observation,'clock':{'intro':intro}}
                    low={'structured':True,'wait_for_move':wait,'chunk_size':1,'max_duration':48,
                         'pixel_controls':True,'speed':1,'effort':'low','candidate':source}
                    medium={**low,'effort':'medium','candidate':alias}
                    self.assertEqual(make_prompt(source,ob,low,profile).encode(),
                                     make_prompt(alias,ob,medium,profile).encode())

    def test_effective_config_must_match_requested_effort(self):
        config={'model':'gpt-6.1-sol','model_reasoning_effort':'medium',
                'model_provider':'openai','forced_login_method':'chatgpt'}
        self.assertEqual(effective_subset(config,{},effort='medium')['model_reasoning_effort'],'medium')
        with self.assertRaisesRegex(RuntimeError,'model_reasoning_effort'):
            effective_subset(config,{})
        config['model_reasoning_effort']='low'
        with self.assertRaisesRegex(RuntimeError,'model_reasoning_effort'):
            effective_subset(config,{},effort='medium')

    def test_actual_thread_effort_checked_without_trusting_request(self):
        self.assertEqual(checked_native_thread({'model':'gpt-6.1-sol','reasoningEffort':'low'},'gpt-6.1-sol'),'low')
        with self.assertRaisesRegex(RuntimeError,'model/effort mismatch'):
            checked_native_thread({'model':'gpt-6.1-sol','reasoningEffort':'low'},'gpt-6.1-sol','medium')
        with self.assertRaisesRegex(RuntimeError,'model/effort mismatch'):
            checked_native_thread({'model':'gpt-6.1-sol'},'gpt-6.1-sol','medium')

    def test_api_medium_rejected_before_files_pool_or_browser(self):
        with tempfile.TemporaryDirectory() as temp:
            for provider in ('api','unknown',None):
                config={'provider':provider,'effort':'medium'};output=Path(temp)/str(provider)
                with patch('research.run_episode.BrowserEnv') as browser, patch('research.run_episode.cf.ThreadPoolExecutor') as pool, patch('research.api_client.ApiClient') as api:
                    with self.assertRaisesRegex(ValueError,'API episode effort currently supports low only'):
                        run(config,output)
                    with self.assertRaisesRegex(ValueError,'API episode effort currently supports low only'):
                        DecisionPool(config,output)
                    browser.assert_not_called();pool.assert_not_called();api.assert_not_called()
                self.assertFalse(output.exists())

    def native_stub(self, effective='medium', actual='medium'):
        """Native protocol fixture: no subprocess, authentication, or model calls."""
        calls=[]
        class Runner:
            def _sandbox_command(self,workspace,runtime):
                return ['bwrap','--','codex']
            def _read_lines(self,*args):pass
            def _initialize_session(self):pass
            def _rpc(self,method,params,*args):
                calls.append((method,params))
                if method=='account/read':return {'account':{'type':'chatgpt'}},None
                if method=='config/read':
                    return {'config':{'model':'gpt-6.1-sol','model_reasoning_effort':effective,
                                      'model_provider':'openai','forced_login_method':'chatgpt'}},None
                if method=='thread/start':
                    return {'model':'gpt-6.1-sol','reasoningEffort':actual,'thread':{'id':'stub'}},None
                if method=='turn/start':return {},None
                raise AssertionError(method)
            def _request_action(self,prompt,attached,directory):
                self._rpc('turn/start',{'effort':'low'},None)
                return '[[0,1,1,0,1]]',{'tokenUsage':{}}
            def close(self):
                if self.runtime:self.runtime.cleanup()
                if getattr(self,'stderr',None):self.stderr.close()
        modules={}
        for name in ('latency_bench','latency_bench.core','latency_bench.core.config','latency_bench.policy','latency_bench.policy.codex'):
            modules[name]=types.ModuleType(name)
        modules['latency_bench.core.config'].load_config=lambda path:{'policy':{}}
        modules['latency_bench.policy.codex'].CodexPolicyRunner=Runner
        return modules,calls

    def test_medium_propagates_config_turn_and_verified_response_metadata(self):
        modules,calls=self.native_stub()
        process=types.SimpleNamespace(stdin=io.StringIO(),stdout=io.StringIO())
        with tempfile.TemporaryDirectory() as temp, patch.dict('sys.modules',modules), patch('research.subscription.subprocess.Popen',return_value=process) as popen:
            root=Path(temp);client=SubscriptionClient(root/'suite',root/'native',effort='medium',lean=True)
            try:
                result=client.act('unchanged game task',[b'\x89PNG\r\n\x1a\nfixture'],root/'call')
                self.assertEqual(result['meta']['effort'],'medium')
                self.assertEqual(result['meta']['native_reasoning_effort'],'medium')
                self.assertEqual(result['meta']['effective_config_effort'],'medium')
                self.assertEqual(next(params for method,params in calls if method=='turn/start')['effort'],'medium')
                self.assertIn('model_reasoning_effort="medium"',popen.call_args.args[0])
                self.assertEqual(json.loads((root/'native/effective_native.json').read_text())['model_reasoning_effort'],'medium')
            finally:client.close()

    def test_medium_fails_closed_if_native_ignores_it(self):
        process=types.SimpleNamespace(stdin=io.StringIO(),stdout=io.StringIO())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            modules,_=self.native_stub(effective='low')
            with patch.dict('sys.modules',modules), patch('research.subscription.subprocess.Popen',return_value=process):
                with self.assertRaisesRegex(RuntimeError,'model_reasoning_effort'):
                    SubscriptionClient(root/'suite',root/'bad-config',effort='medium')
            modules,_=self.native_stub(actual='low')
            with patch.dict('sys.modules',modules), patch('research.subscription.subprocess.Popen',return_value=process):
                client=SubscriptionClient(root/'suite',root/'bad-thread',effort='medium')
                with self.assertRaisesRegex(RuntimeError,'model/effort mismatch'):
                    client.act('task',[b'\x89PNG\r\n\x1a\nfixture'],root/'bad-call')
                self.assertFalse((root/'bad-call/response.json').exists())


if __name__=='__main__':unittest.main()
