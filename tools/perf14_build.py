"""Recipe changes isolated from earlier test builders and their outputs."""
from perf14_mappings import replace_once

def adapt_recipe(recipe):
    recipe = recipe.replace('runtime-perf11-box64-044', 'runtime-perf14-map-guards')
    recipe = recipe.replace('pes13-nx-0.2.0-perf11-box64-044', 'pes13-nx-0.2.0-perf14-map-guards')
    recipe = recipe.replace('PES13-NX PERF11', 'PES13-NX PERF14')
    recipe = recipe.replace('dist/perf11-runtime', 'local/perf14/payload')
    recipe = replace_once(recipe, '    horizon_source.write_text(horizon_text)',
        '    from perf14_mappings import patch_horizon\n'
        '    horizon_text = patch_horizon(horizon_text)\n'
        '    horizon_source.write_text(horizon_text)')
    # Run old-vs-new host probes before changing source. The fixture uses
    # real transition functions extracted from the same baseline as the build.
    recipe = replace_once(recipe, '\ntry:\n    from perf11_adapter import adapt',
        '\nsubprocess.run([sys.executable, str(project / "tests/perf14_mappings.py"), str(horizon_source)], check=True)\n'
        '\ntry:\n    from perf11_adapter import adapt')
    # Earlier builders copied obsolete test DLLs and settings. PERF14 is
    # NRO-only; the separate packager keeps the installed PERF13 DLL intact.
    recipe = recipe[:recipe.index('# Preserve the known-good compatibility profile')]
    recipe += '''
nro_blob = (dest / "pes13-nx.nro").read_bytes()
assert b"pes13-nx-0.2.0-perf14-map-guards" in nro_blob
from nro_assets import inspect_nro
inspect_nro(nro_blob, (project / "assets/icon.jpg").read_bytes(), expected_title="PES13-NX PERF14")
(project / "local/perf14/build.json").write_text(json.dumps({
    "nro_sha256": hashlib.sha256(nro_blob).hexdigest(),
    "elf": str(build / "wine-nx-runtime.elf"),
    "source_restored": True, "Box64": "0.4.4 -O1 same as PERF11",
    "hardware_tested": False,
}, indent=2))
print("PERF14 NRO built; baseline sources restored", flush=True)
'''
    return recipe
