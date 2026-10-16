"""Version-checked isolated native envelope; never copies authentication files."""
import json
from pathlib import Path

from .subscription import LEAN_BASE_INSTRUCTIONS

AGGRESSIVE_SETTINGS = {
    'model_instructions_file': '/runtime/system.txt',
    'developer_instructions': '',
    'project_doc_max_bytes': 0,
    'skills.include_instructions': False,
    'include_apps_instructions': False,
    'include_collaboration_mode_instructions': False,
    'include_environment_context': False,
    'include_permissions_instructions': False,
    'memories.use_memories': False,
    'memories.generate_memories': False,
    'features.apps': False,
    'features.plugins': False,
    'features.remote_plugin': False,
    'features.plugin_sharing': False,
    'features.shell_tool': False,
    'features.unified_exec': False,
    'features.shell_snapshot': False,
    'features.view_image': False,
    'features.image_generation': False,
    'features.multi_agent': False,
    'features.skill_search': False,
    'features.skill_mcp_dependency_install': False,
    'features.skip_host_skill_discovery': True,
    'web_search': 'disabled',
    'mcp_servers': {},
    'personality': 'none',
}
VERSION_ADAPTATIONS = {
    '--ignore-user-config': 'Unsupported by tested 0.162.1; isolated empty CODEX_HOME supplies equivalent user-config isolation.',
    'tools.view_image': 'Unsupported configuration field; use registered features.view_image=false instead.',
}


def toml_value(value):
    if isinstance(value, dict):
        if value:
            raise ValueError('Only empty inline tables are supported')
        return '{}'
    return json.dumps(value)


def isolated_command(command, runtime, source_home):
    """Keep the existing bwrap confinement, replacing only its auth/home mount."""
    command = list(command)
    runtime, source_home = Path(runtime), Path(source_home)
    auth = source_home / 'auth.json'
    if not auth.is_file():
        raise RuntimeError('Original native auth.json is missing; no credential copy or API fallback')
    home = runtime / 'codex-home';home.mkdir()
    system = runtime / 'system.txt';system.write_text(LEAN_BASE_INSTRUCTIONS + '\n')
    system.chmod(0o444)
    settings = json.loads(json.dumps(AGGRESSIVE_SETTINGS))
    (home / 'config.toml').write_text('\n'.join(key+' = '+toml_value(value) for key,value in settings.items())+'\n')
    mount = ['--bind', str(source_home), '/home/ubuntu/.codex']
    matches = [i for i in range(len(command)-2) if command[i:i+3] == mount]
    if len(matches) != 1:
        raise RuntimeError('Native home mount layout changed; refusing unverified isolation')
    i = matches[0]
    del command[i:i+3]
    separator=command.index('--')
    # Mount after /runtime, otherwise its later bind would hide auth.json.
    command[separator:separator]=['--ro-bind',str(auth),'/runtime/codex-home/auth.json']
    matches = [i for i in range(len(command)-2) if command[i:i+2] == ['--setenv','CODEX_HOME']]
    if len(matches) != 1:
        raise RuntimeError('Native CODEX_HOME environment layout changed')
    command[matches[0]+2] = '/runtime/codex-home'
    command += ['--strict-config', '-c', 'model_instructions_file="/runtime/system.txt"']
    return command, settings


def effective_subset(config, expected):
    """Whitelist values only: never archive the full config or authentication."""
    result = {}
    for key, value in expected.items():
        actual = config
        for part in key.split('.'):
            if not isinstance(actual, dict) or part not in actual:
                raise RuntimeError('Effective native config missing '+key)
            actual = actual[part]
        if actual != value:
            raise RuntimeError('Effective native config mismatch '+key)
        result[key] = actual
    for key,value in {'model':'gpt-6.1-sol','model_reasoning_effort':'low','model_provider':'openai','forced_login_method':'chatgpt'}.items():
        if config.get(key) != value:
            raise RuntimeError('Effective native model/auth configuration mismatch '+key)
        result[key] = value
    return result
