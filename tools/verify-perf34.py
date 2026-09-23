"""Verify the PERF34 runtime ABI and retained PERF33 build components."""
from pathlib import Path
import hashlib,json,os,subprocess

p=Path(__file__).resolve().parents[1];w=p/'local/perf34'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
report=json.loads((w/'verification.json').read_text())
source=root/'runtime-perf11-source'
for rel,digest in json.loads((w/'source-baseline.json').read_text()).items():
    assert sha(source/rel)==digest,rel
build=root/'runtime-perf34-config'
symbols=subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',str(build/'wine-nx-runtime.elf')],text=True)
assert any(line.endswith(' wine_nx_config_file_bool') for line in symbols.splitlines())
nro=(w/'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf34-config' in nro
assert b'configuration.ini' in nro
assert b'legacy boolean fallback enabled' in nro
assert hashlib.sha256(nro).hexdigest()==json.loads((w/'build.json').read_text())['nro_sha256']
assert 'wine_nx_config_file_bool' in (p/'src/runtime/pes13_config.h').read_text()
report.update(dict(unified_configuration=True,legacy_fallback=True,configuration_parser_linked=True,
                   source_restored=True,hardware_tested=False,
                   changed_sources_sha256={str(f.relative_to(p)):sha(f) for f in [
                       p/'tools/build-perf34.py',p/'tools/run-perf34-build.py',p/'tools/verify-perf34.py',
                       p/'tools/package-perf34.py',p/'tools/perf34_patches.py',
                       p/'src/runtime/pes13_config.h',p/'tests/perf34_config.py',
                       p/'config/configuration.ini']}))
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF34 unified configuration parser, legacy fallback, and restored source PASS',flush=True)
