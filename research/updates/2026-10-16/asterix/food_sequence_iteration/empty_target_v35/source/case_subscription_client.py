"""Default/minimal native subscription clients; preserve the existing external sandbox."""
import json
import pathlib
import threading
import time

_INIT_LOCK = threading.Lock()

MINIMAL_CONFIG = {
    'developer_instructions': '',
    'project_doc_max_bytes': 0,
    'skills.include_instructions': False,
    'include_apps_instructions': False,
    'include_collaboration_mode_instructions': False,
    'include_environment_context': False,
    'include_permissions_instructions': False,
    'memories.use_memories': False,
    'memories.generate_memories': False,
    'mcp_servers': {},
    'web_search': 'disabled',
    **{'features.' + key: False for key in (
        'apps', 'plugins', 'shell_tool', 'unified_exec', 'multi_agent',
        'multi_agent_v2', 'browser_use', 'browser_use_external',
        'browser_use_full_cdp_access', 'computer_use', 'image_generation',
        'view_image', 'sleep_tool', 'skill_search', 'workspace_dependencies',
        'code_mode_host', 'recommended_plugins',
    )},
}


def minimal_command(command, auth_source, system_path='/runtime/minimal-system.txt'):
    """Add one read-only auth mount and config flags; never relax sandbox flags."""
    command = list(command)
    native_index = command.index('/opt/codex/bin/codex')
    separator = max(i for i in range(native_index) if command[i] == '--')
    command[separator:separator] = ['--ro-bind', str(auth_source), '/home/ubuntu/.codex/auth.json']
    command.append('--strict-config')
    config = {**MINIMAL_CONFIG, 'model_instructions_file': system_path}
    for key, value in config.items():
        command.extend(['-c', key+'='+json.dumps(value)])
    return command


class CaseSubscriptionClient:
    def __init__(self, suite, output, profile='minimal', quota_stop_percent=50, system_file=None):
        if profile not in ('default','minimal'):
            raise ValueError('Unknown wrapper profile')
        output = pathlib.Path(output)
        output.mkdir(parents=True, exist_ok=True)
        import sys
        sys.path.insert(0,str(suite/'code'))
        from latency_bench.policy.codex import CodexPolicyRunner
        from subscription_client import SubscriptionClient
        self.profile = profile
        self.output = output
        self.last_total_s = None
        self._captured_runner = None
        with _INIT_LOCK:
            original = CodexPolicyRunner._sandbox_command
            if profile == 'minimal':
                if system_file is None:
                    system_file = pathlib.Path(__file__).with_name('minimal_system.txt')
                    if not system_file.is_file():
                        system_file = pathlib.Path(__file__).parent/'policy_cases/prompt_search/minimal_system.txt'
                if not pathlib.Path(system_file).read_text().strip():
                    raise ValueError('Nonempty minimal system instructions required')
                isolated_home = output/'isolated_codex_home'
                isolated_home.mkdir(mode=0o700)
                (isolated_home/'auth.json').touch(mode=0o600)
                auth_source = pathlib.Path('/home/ubuntu/.codex/auth.json')
                if not auth_source.is_file():
                    raise RuntimeError('Existing native subscription auth file is required; no auth copy/fallback')
                instructions = pathlib.Path(system_file).read_text()
                owner = self
                def replacement(runner, workspace, runtime):
                    owner._captured_runner = runner
                    runner.settings['codex_home'] = str(isolated_home)
                    (runtime/'minimal-system.txt').write_text(instructions)
                    return minimal_command(original(runner,workspace,runtime),auth_source)
                CodexPolicyRunner._sandbox_command = replacement
            try:
                self.client = SubscriptionClient(suite,output,quota_stop_percent)
            except Exception:
                if self._captured_runner is not None:
                    self._captured_runner.close()
                raise
            finally:
                CodexPolicyRunner._sandbox_command = original
        self.runner = self.client.runner
        if self.runner.settings.get('model') != 'gpt-6.1-sol':
            self.close()
            raise RuntimeError('Pinned gpt-6.1-sol required')
        (output/'wrapper_profile.json').write_text(json.dumps({
            'profile':profile,'effort':self.runner.settings['effort'],
            'auth':'chatgpt subscription','auth_copy':False,
            'isolated_home':profile=='minimal',
            'auth_mount_read_only':profile=='minimal',
            'external_sandbox_unchanged':True,
            'minimal_flags':MINIMAL_CONFIG if profile=='minimal' else None,
            'unsupported_cli_flag':'--ignore-user-config; isolated empty home used instead',
        },indent=2))

    def act(self,prompt,images,directory):
        started=time.perf_counter()
        answer,meta=self.client.act(prompt,images,directory)
        meta['act_total_seconds']=time.perf_counter()-started
        meta['wrapper_profile']=self.profile
        return answer,meta

    def close(self):
        self.client.close()
