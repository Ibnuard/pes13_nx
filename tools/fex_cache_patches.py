"""Isolated DXVK shader-cache path patch; preserves graphics/profile settings.

Parent calls apply(read, replace, project) after fex_frame_patches.apply.
Only wine-nx-probe/source/runtime.c is changed.
"""
import re


_RUNTIME = 'wine-nx-probe/source/runtime.c'
_ENVIRONMENT = re.compile(
    r'static const char runtime_environment\[\] =\n'
    r'(?:    "(?:[^"\\\n]|\\.)*"(?:\n|;\n))+')
_ENTRY = re.compile(r'    "((?:[^"\\\n]|\\.)*)"')
_CACHE_ENTRY = r'DXVK_SHADER_CACHE_PATH=C:\\dxvk-cache\0'


def apply(read, replace, project):
    source = read(_RUNTIME)
    block = _ENVIRONMENT.search(source)
    if block is None:
        raise RuntimeError('FEX cache: runtime_environment anchor missing')
    entries = _ENTRY.findall(block.group())
    if any(entry.split('=', 1)[0].lower() == 'dxvk_shader_cache_path' for entry in entries):
        raise RuntimeError('FEX cache: DXVK_SHADER_CACHE_PATH already present; refusing override')
    entries.append(_CACHE_ENTRY)
    entries.sort(key=lambda entry: entry.split('=', 1)[0].lower())
    environment = 'static const char runtime_environment[] =\n'
    environment += '\n'.join('    "' + entry + '"' for entry in entries) + ';\n'
    helper = (project / 'src/runtime/fex_cache_runtime.h').read_text()
    replace(_RUNTIME, block.group(), helper + '\n' + environment)
    anchor = '    wine_nx_runtime_platform_init();'
    replace(_RUNTIME, anchor, '    fex_cache_prepare_directory();\n' + anchor)
