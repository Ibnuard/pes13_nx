"""Opt-in 500-instruction JIT cap, with same-build 5000 control in the INI."""
from fex_cache_patches import _ENVIRONMENT, _ENTRY


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    match = _ENVIRONMENT.search(read(name))
    if not match:
        raise ValueError('JIT latency: missing environment')
    entries = _ENTRY.findall(match.group())
    if any(e.startswith('FEX_MAXINST=') for e in entries):
        raise ValueError('JIT latency: refusing duplicate config')

    def environment(symbol, value):
        items = sorted(entries + [rf'FEX_MAXINST={value}\0'], key=lambda e: e.split('=')[0].lower())
        return 'static const char ' + symbol + '[] =\n' + '\n'.join('    "' + e + '"' for e in items) + ';\n'

    replace(name, match.group(), environment('runtime_environment', 500) + '\n' +
            environment('fex_jit_large_environment', 5000) + '\n' +
            environment('fex_jit_small_environment', 128))
    replace(name, '        environment_bytes = sizeof(runtime_environment);',
            '        environment_bytes = sizeof(runtime_environment);\n'
            '        if (wine_nx_config_file_bool(RUNTIME_DIR "/fex_jit_large", 0)) {\n'
            '            environment = fex_jit_large_environment;\n'
            '            environment_bytes = sizeof(fex_jit_large_environment);\n'
            '        } else if (wine_nx_config_file_bool(RUNTIME_DIR \"/fex_jit_small\", 0)) {\n'
            '            environment = fex_jit_small_environment;\n'
            '            environment_bytes = sizeof(fex_jit_small_environment);\n'
            '        }\n'
            '        log_line("[FEX3-JIT-LAUNCH] maxinst=%u; small=128 baseline=500 large=5000",\n'
            '                 environment == fex_jit_large_environment ? 5000u : environment == fex_jit_small_environment ? 128u : 500u);')
    replace(name, '        "[FEX3-RESUME] waits="',
            '        "[FEX3-RESUME] waits=", "[FEX3-JIT] phase="')
    replace(name, '"pes13-fex3-warm-audit"', '"pes13-fex3-jit-latency"')
