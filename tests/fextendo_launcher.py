"""Sanitizer UI/IO/lifecycle checks, linked-build binding and real-renderer previews."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    a=p.parse_args();work=a.work.resolve();preview=work/'preview';preview.mkdir(exist_ok=True)
    receipt=json.loads((work/'runtime/runtime-build.json').read_text())
    assert receipt['launcher'] and receipt['gap_audit'] and not receipt['yield_adaptive']
    generated=(a.source/'wine-nx-probe/source/runtime.c').read_text()
    headers=['src/runtime/fextendo_'+n+'.h' for n in ('presets','renderers','ui','launcher','timestamp_pixels','timestamp','overlay_layer','sfx','logs','display')]
    for n in headers:
        assert (ROOT/n).read_text() in generated,n
        assert receipt['patch_sources'][n]==sha(ROOT/n),n
    assert 'if (!fx_handoff()) return NULL;' in generated
    assert 'if (fx_owned()) return NULL; /* suppress intermediate desktop/GDI windows */' in generated
    assert 'else if (!fx_launcher_start()) return 0;' in generated
    assert '--wrap=viOpenDisplay' in (a.source/'wine-nx-probe/CMakeLists.txt').read_text()
    objdump=Path(os.environ.get('DEVKITPRO','/opt/devkitpro'))/'devkitA64/bin/aarch64-none-elf-objdump'
    display_init=subprocess.check_output([str(objdump),'-d','--disassemble=__nx_win_init',
                                         str(work/'runtime/reference/pes13-fex.elf')],text=True)
    assert re.search(r'\bbl\s+[0-9a-f]+ <__wrap_viOpenDisplay>',display_init)
    assert 'run-guest-tests.txt", 0)' in generated
    records=['Linked ELF: libnx default-window initialization calls the display capture wrapper.']
    with tempfile.TemporaryDirectory(prefix='fextendo-check-') as d:
        tmp=Path(d);root=tmp/'root';shutil.copytree(work/'package/switch/pes13-fex/launcher',root/'launcher')
        shutil.copytree(ROOT/'config/fextendo/presets',root/'launcher/presets',dirs_exist_ok=True)
        (root/'launcher/selected.txt').write_text('0\n')
        for name in ('ui','renderers','preset_failures','lifecycle','timestamp','sfx','logs','display'):
            exe=tmp/name
            subprocess.run(['clang','-std=c11','-O1','-D_POSIX_C_SOURCE=200809L','-fsanitize=address,undefined',
                            '-fno-sanitize-recover=all','-g','-Wall','-Wextra',str(ROOT/f'tests/fextendo_{name}.c'),'-o',str(exe)],check=True)
            if name=='ui':commands=[[str(exe),str(root),str(preview)]]
            elif name in ('preset_failures','renderers'):commands=[[str(exe),str(root)]]
            elif name=='logs':
                logdir=tmp/'log-rotation';logdir.mkdir();commands=[[str(exe),str(logdir)]]
            elif name=='display':commands=[[str(exe)]]
            elif name=='sfx':commands=[[str(exe),str(root)]]
            elif name=='timestamp':commands=[[str(exe),str(preview/'timestamp.ppm'),str(root)]]
            else:
                # The corruption test deliberately damaged one template.
                shutil.copytree(ROOT/'config/fextendo/presets',root/'launcher/presets',dirs_exist_ok=True)
                game=tmp/'pes2013.exe';game.write_bytes(b'MZ')
                commands=[[str(exe),str(root),str(game if mode!=2 else tmp/'missing.exe'),str(mode)] for mode in range(12)]
            for command in commands:
                r=subprocess.run(command,check=True,capture_output=True,text=True,timeout=45)
                records.append(r.stdout.strip());print(r.stdout.strip(),flush=True)
    names=headers+['tools/fextendo_launcher_patches.py','tools/build-fextendo-assets.py','tools/make-fextendo-presets.py',
                   'tests/fextendo_launcher.py','tests/fextendo_ui.c','tests/fextendo_preset_failures.c','tests/fextendo_lifecycle.c',
                   'tests/fextendo_renderers.c','tests/fextendo_timestamp.c','tests/fextendo_sfx.c','tests/fextendo_logs.c','tests/fextendo_display.c']
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':receipt['native_elf_sha256'],
            'nro_sha256':receipt['nro_sha256'],'source_hashes':{n:sha(ROOT/n) for n in names},'checks':records,
            'generated_source_sha256':sha(a.source/'wine-nx-probe/source/runtime.c'),
            'screenshots_use_production_renderer':True,'canonical_settings':'C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat'}
    (work/'launcher.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
