import json
from pathlib import Path
import tempfile
import unittest

from research.native_envelope import AGGRESSIVE_SETTINGS, effective_subset, isolated_command


class NativeEnvelopeTests(unittest.TestCase):
    def test_isolation_mounts_auth_readonly_without_copying_or_changing_sandbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);auth=root/'original';auth.mkdir();(auth/'auth.json').write_text('sentinel-not-a-real-secret')
            runtime=root/'runtime';runtime.mkdir()
            command=['bwrap','--unshare-pid','--bind',str(auth),'/home/ubuntu/.codex',
                     '--bind',str(runtime),'/runtime','--setenv','CODEX_HOME','/home/ubuntu/.codex',
                     '--','/opt/codex/bin/codex','app-server','--stdio']
            result,settings=isolated_command(command,runtime,auth)
            self.assertEqual((auth/'auth.json').read_text(),'sentinel-not-a-real-secret')
            self.assertFalse((runtime/'codex-home/auth.json').exists())
            index=result.index('--ro-bind');self.assertEqual(result[index+1:index+3],[str(auth/'auth.json'),'/runtime/codex-home/auth.json'])
            self.assertGreater(index,result.index(str(runtime)))
            self.assertIn('--unshare-pid',result);self.assertIn('--strict-config',result)
            self.assertNotIn('--ignore-user-config',result)
            self.assertNotIn(str(auth),result)
            self.assertNotIn('tools.view_image',settings)
            self.assertFalse(settings['features.view_image'])
            self.assertTrue((runtime/'system.txt').read_text().strip())
            self.assertNotIn('sentinel-not-a-real-secret',(runtime/'codex-home/config.toml').read_text())
            self.assertEqual(command[command.index('CODEX_HOME')+1],'/home/ubuntu/.codex')

    def test_missing_mount_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);auth=root/'auth';auth.mkdir();(auth/'auth.json').touch();runtime=root/'runtime';runtime.mkdir()
            with self.assertRaisesRegex(RuntimeError,'mount layout changed'):
                isolated_command(['bwrap','--','codex'],runtime,auth)

    def test_effective_verification_rejects_ignored_settings(self):
        expected={'include_environment_context':False,'features.view_image':False}
        config={'include_environment_context':False,'features':{'view_image':False},
                'model':'gpt-6.1-sol','model_reasoning_effort':'low','model_provider':'openai','forced_login_method':'chatgpt'}
        self.assertEqual(effective_subset(config,expected)['model_reasoning_effort'],'low')
        config['features']['view_image']=True
        with self.assertRaisesRegex(RuntimeError,'mismatch features.view_image'):
            effective_subset(config,expected)
        del config['features']['view_image']
        with self.assertRaisesRegex(RuntimeError,'missing features.view_image'):
            effective_subset(config,expected)


if __name__=='__main__':unittest.main()
