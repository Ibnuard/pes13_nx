"""Small source-level contract tests for the unified configuration ABI."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
header = (root / 'src/runtime/pes13_config.h').read_text()
patch = (root / 'tools/perf34_patches.py').read_text()
template = (root / 'config/configuration.ini').read_text()
assert 'configuration.ini' in patch
assert 'wine_nx_config_file_bool' in header
assert 'legacy boolean files remain supported' in patch
assert 'perf33_blocks=1' in template
assert 'controller_gamepad=0' in template
for key in ('perf8-turbo.txt', 'perf17-hotblocks.txt', 'perf19-matrix.txt',
            'perf20-fusion.txt', 'perf21-fastmath.txt', 'perf22-floatmath.txt',
            'perf25-paircopy.txt', 'perf32-blocks.txt', 'perf33-blocks.txt'):
    assert key in patch, key
print('PERF34 unified configuration source contract PASS')
