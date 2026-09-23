"""Build the PERF17 identity fix in a separate WSL output directory."""
from pathlib import Path
import perf17_patches

p = Path(__file__).resolve().parents[1]
previous = perf17_patches.adapt_recipe


def revision(recipe):
    recipe = previous(recipe)
    recipe = recipe.replace('runtime-perf17-hotblocks', 'runtime-perf17b-image-identity')
    recipe = recipe.replace('pes13-nx-0.2.0-perf17-hotblocks', 'pes13-nx-0.2.0-perf17b-image-identity')
    recipe = recipe.replace('PES13-NX PERF17', 'PES13-NX PERF17B')
    recipe = recipe.replace('local/perf17', 'local/perf17b')
    return recipe


perf17_patches.adapt_recipe = revision
path = p / 'tools/build-perf17.py'
exec(compile(path.read_text(), str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
