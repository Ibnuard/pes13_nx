"""Read-only compiler provenance checks for resumable FEX build trees."""
from pathlib import Path
import re
import shlex
import shutil


MODULE_COMPILERS = {'C': 'aarch64-w64-mingw32-clang',
                    'CXX': 'aarch64-w64-mingw32-clang++',
                    'ASM': 'aarch64-w64-mingw32-clang'}


def refuse(build, reason):
    raise SystemExit(f'Toolchain provenance: {build}: {reason}; '
                     'use a separate --build-root (changing --output-dir does not isolate caches). '
                     'Existing files were not reset.')


def compiler_path(path):
    # LLVM-MinGW wrappers dispatch on argv[0]; keep the invocation basename.
    path = Path(path)
    return str(path.parent.resolve() / path.name)


def cmake_provenance(build, toolchain, names=MODULE_COMPILERS, *, required=False):
    expected = {language: compiler_path(toolchain / 'bin' / name)
                for language, name in names.items()}
    files = list((build / 'CMakeFiles').glob('*/CMake*Compiler.cmake'))
    cache = build / 'CMakeCache.txt'
    if cache.is_file():
        files.append(cache)
    if not files:
        if required or (build.exists() and any(build.iterdir())):
            refuse(build, 'missing CMake compiler metadata; legacy cache is ambiguous')
        return None
    found = {language: set() for language in names}
    for file in files:
        text = file.read_text()
        for language in names:
            patterns = [rf'^CMAKE_{language}_COMPILER:[^=\n]+=(.+)$',
                        rf'^set\(CMAKE_{language}_COMPILER "([^"]+)"\)$']
            for pattern in patterns:
                found[language].update(re.findall(pattern, text, re.MULTILINE))
    for language, paths in found.items():
        if not paths:
            refuse(build, f'missing CMAKE_{language}_COMPILER; legacy cache is ambiguous')
        for path in paths:
            if not Path(path).is_absolute() or compiler_path(path) != expected[language]:
                refuse(build, f'CMAKE_{language}_COMPILER={path}, selected {expected[language]}')
    return {'toolchain_path': str(toolchain.resolve()), 'compilers': expected}


def wine_provenance(build, toolchain, env, *, required=False):
    makefile = build / 'Makefile'
    if not makefile.is_file():
        if required or (build.exists() and any(build.iterdir())):
            refuse(build, 'missing Wine Makefile; legacy cache is ambiguous')
        return None
    log = build / 'config.log'
    text = makefile.read_text()
    configured = re.findall(r'^configure:\d+: found (/.+)$', log.read_text(), re.MULTILINE) if log.is_file() else []
    compilers = {}
    for arch in ('aarch64', 'i386'):
        values = re.findall(rf'^{arch}_CC\s*=\s*(.+)$', text, re.MULTILINE)
        if len(values) != 1:
            refuse(build, f'missing or ambiguous {arch}_CC')
        argv = shlex.split(values[0])
        if not argv or '$' in values[0]:
            refuse(build, f'unsupported {arch}_CC={values[0]}')
        command = Path(argv[0])
        expected = compiler_path(toolchain / 'bin' / command.name)
        if command.is_absolute():
            historical = {compiler_path(command)}
        else:
            historical = {compiler_path(path) for path in configured if Path(path).name == command.name}
        if historical != {expected}:
            refuse(build, f'{arch}_CC historical compiler {sorted(historical)}, selected {expected}; '
                         'missing/conflicting configure evidence is unsafe')
        effective = shutil.which(str(command), path=env['PATH'])
        if effective is None or compiler_path(effective) != expected:
            refuse(build, f'{arch}_CC resolves to {effective}, selected {expected}')
        compilers[arch] = expected
    return {'toolchain_path': str(toolchain.resolve()), 'compilers': compilers}
