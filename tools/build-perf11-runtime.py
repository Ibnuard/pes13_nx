"""Build Box64 v0.4.4 on an isolated runtime-perf11-source checkout."""
from pathlib import Path
import sys

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / 'tools'))
driver = (project / 'tools/build-perf10-runtime.py').read_text()
anchor = "exec(compile(recipe, str(recipe_path), 'exec'), {'__file__': str(recipe_path), '__name__': '__main__'})"
assert driver.count(anchor) == 1
driver = driver.replace(anchor, '''
recipe = recipe.replace('runtime-pes13-source', 'runtime-perf11-source')
recipe = recipe.replace('runtime-perf10-resume-gate', 'runtime-perf11-box64-044')
recipe = recipe.replace('pes13-nx-0.2.0-perf10-resume-gate', 'pes13-nx-0.2.0-perf11-box64-044')
recipe = recipe.replace('PES13-NX PERF10', 'PES13-NX PERF11')
recipe = recipe.replace('dist/perf10-runtime', 'dist/perf11-runtime')
recipe = recipe.replace('dist/pes13-perf10-runtime.zip', 'dist/pes13-perf11-runtime.zip')
# This isolated build has already been clean-configured without SAVE_MEM.
# Subsequent attempts use Ninja dependency tracking while integration evolves.
recipe = recipe.replace('if build.exists():', 'if False and build.exists():')
hook = '    cmake_source.write_text(cmake_text)'
assert recipe.count(hook) == 1
recipe = recipe.replace(hook, '    from perf11_adapter import adapt\\n'
    '    cmake_text, dynarec_text, engine_text = adapt(cmake_text, dynarec_text, engine_text)\\n' + hook)
exec(compile(recipe, str(recipe_path), 'exec'), {'__file__': str(recipe_path), '__name__': '__main__'})
''')
exec(compile(driver, str(project / 'tools/build-perf10-runtime.py'), 'exec'),
     {'__file__': str(project / 'tools/build-perf10-runtime.py'), '__name__': '__main__'})
