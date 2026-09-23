"""Build PERF8's validated policy plus conditional ResumeThread gate wakeups.

Reuses the PERF8 recipe with checked substitutions instead of maintaining a
second copy of its compiler and compatibility fixes. Source restoration stays
owned by that recipe's finally block. Run under WSL with PES_BUILD_ROOT set.
"""
from pathlib import Path
import os
import subprocess

project = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', str(Path.home() / '.cache/pes13-nx')))
recipe_path = project / 'tools/build-perf8-test.py'
recipe = recipe_path.read_text()

def once(old, new):
    global recipe
    assert recipe.count(old) == 1, old
    recipe = recipe.replace(old, new)

once('runtime_source = source / "source/runtime.c"',
     'runtime_source = source / "source/runtime.c"\nhorizon_source = wine_source / "dlls/ntdll/unix/horizon.c"')
once('vulkan_source, runtime_source,', 'vulkan_source, runtime_source, horizon_source,')
once('perf3 = project / "dist/perf3/switch/pes13-nx"',
     'perf3 = project / "dist/pes13-perf8-overlay/switch/pes13-nx"')
recipe = recipe.replace('runtime-perf8-block-profile', 'runtime-perf10-resume-gate')
recipe = recipe.replace('pes13-nx-0.2.0-perf8-block-profile', 'pes13-nx-0.2.0-perf10-resume-gate')
recipe = recipe.replace('PES13-NX PERF8', 'PES13-NX PERF10')
recipe = recipe.replace('dist/perf8', 'dist/perf10-runtime')
recipe = recipe.replace('dist/pes13-perf8-overlay.zip', 'dist/pes13-perf10-runtime.zip')
once('    runtime_source.write_text(runtime_text)', '''    runtime_source.write_text(runtime_text)
    horizon_text = replace_once(originals[horizon_source].decode(),
        "    horizon_server_signal_changed_locked();  /* the start gate */",
        "    /* PERF10: only a successful 1 -> 0 transition opens the start gate. */\\n"
        "    if (!status && reply.count == 1) horizon_server_signal_changed_locked();")
    horizon_source.write_text(horizon_text)
    subprocess.run([sys.executable, str(project / "tests/perf10_resume.py"), str(wine_source)], check=True)''')
exec(compile(recipe, str(recipe_path), 'exec'), {'__file__': str(recipe_path), '__name__': '__main__'})
