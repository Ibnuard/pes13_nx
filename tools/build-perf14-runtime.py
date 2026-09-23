"""Reuse the validated PERF11 runtime recipe with mapping handoff guards."""
from pathlib import Path
import sys

p = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(p/'tools'))
driver = (p/'tools/build-perf11-runtime.py').read_text()
anchor = "\nexec(compile(recipe, str(recipe_path), 'exec'), {'__file__': str(recipe_path), '__name__': '__main__'})"
assert driver.count(anchor) == 1
driver = driver.replace(anchor, '\nfrom perf14_build import adapt_recipe\nrecipe = adapt_recipe(recipe)\n'+anchor)
exec(compile(driver, str(p/'tools/build-perf11-runtime.py'), 'exec'),
     {'__file__': str(p/'tools/build-perf11-runtime.py'), '__name__': '__main__'})
