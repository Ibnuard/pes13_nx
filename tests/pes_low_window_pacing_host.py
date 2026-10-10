"""Sanitize the actual preset transaction, bounded readers, and report gates."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();checks=[]
    with tempfile.TemporaryDirectory(prefix='pes-lw2-') as temp:
        work=Path(temp);fixture=work/'root'
        shutil.copytree(ROOT/'config/fextendo/presets',fixture/'launcher/presets')
        for name in ('fextendo_preset_failures','fex_game_timing_native','pes_low_window_diagnostics',
                     'pes_live_settings','pes_vk_work'):
            exe=work/name
            subprocess.run(['gcc','-std=c11','-D_POSIX_C_SOURCE=200809L','-O1','-g',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                str(ROOT/'tests'/f'{name}.c'),'-pthread','-o',str(exe)],check=True)
            args=[str(exe)]+([str(fixture)] if name=='fextendo_preset_failures' else [])
            result=subprocess.run(args,check=True,capture_output=True,text=True,timeout=90)
            checks.append(result.stdout.strip());print(result.stdout.strip(),flush=True)
    sources=('src/runtime/fextendo_presets.h','src/runtime/pes_low_window_diagnostics.h',
             'src/runtime/fex_game_timing.h','src/runtime/fex_game_timing_runtime.h',
             'tests/fextendo_preset_failures.c','tests/pes_low_window_diagnostics.c',
             'tests/fex_game_timing_native.c','tests/pes_low_window_pacing_host.py',
             'src/runtime/pes_live_settings.h','src/runtime/pes_vk_work.h',
             'tests/pes_live_settings.c','tests/pes_vk_work.c')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(passed=True,hardware_tested=False,checks=checks,
        sanitizers=['address','undefined'],sources={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}),indent=2)+'\n')

if __name__=='__main__':main()
