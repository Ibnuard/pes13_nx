"""Real filesystem validation plus startup failure/repair routing; no real game required."""
import argparse,hashlib,json,struct,subprocess,tempfile
from pathlib import Path
from fextendo_install_fixture import make_game,archive
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--game-dir',type=Path,help='Read-only validation of a real reference game folder');a=p.parse_args()
    cases=[];reference=None
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);binary=tmp/'check';root=tmp/'pes13-fex';game=root/'drive_c/PES13'
        make_game(game);img=game/'img'
        subprocess.run(['gcc','-std=gnu11','-O1','-g','-include','stdlib.h','-fsanitize=undefined',
                        str(ROOT/'tests/fextendo_startup_check.c'),'-o',str(binary)],check=True)
        def run(kind,label,target=root,error=None):
            before={n:n.read_bytes() for n in root.rglob('*') if n.is_file()}
            r=subprocess.run([str(binary),str(target),str(kind),*([error] if error else [])],capture_output=True,text=True,timeout=30)
            assert r.returncode==0 and 'runtime error:' not in r.stderr,(label,r.stdout,r.stderr)
            assert all(n.read_bytes()==v for n,v in before.items()),'Checker modified a game file'
            cases.append(label)
        for kind,label in [(0,'healthy offline launch is read-only'),(1,'missing runtime auto-repaired then rechecked'),
                           (2,'network failure blocks launch and recovers transaction'),(3,'unreadable runtime blocks launch'),
                           (5,'failed post-repair verification blocks launch'),(6,'damaged journal blocks launch')]:run(kind,label)
        run(4,'wrong root',tmp/'missing')
        data=(game/'pes2013.exe').read_bytes();(game/'pes2013.exe').write_bytes(b'MZ');run(4,'truncated exe')
        (game/'pes2013.exe').write_bytes(data)
        assert not (img/'dt00.img').exists()
        run(0,'actual localized dt00_e layout accepted without dt00.img')
        (img/'dt00_e.img').rename(img/'DT00_f.IMG');(img/'dt05_e.img').rename(img/'dt05_g.img')
        run(0,'different commentary and menu languages; mixed filename case')
        (img/'DT00_f.IMG').rename(img/'dt00_e.img');(img/'dt05_g.img').rename(img/'dt05_e.img')
        (img/'dt00_e.img').rename(img/'dt00_e.img.bak')
        run(4,'commentary backup is not game data',error='dt00_')
        (img/'dt00_e.img.bak').rename(img/'dt00.img')
        run(4,'bare dt00.img does not replace localized commentary',error='dt00_')
        (img/'dt00.img').rename(img/'dt00_e.img')
        (img/'dt05_e.img').unlink();run(4,'missing menu language',error='dt05_')
        (img/'dt05_e.img').write_bytes(archive())
        (img/'dt00_e.img').write_bytes(archive()[:-1])
        run(4,'truncated commentary names the affected file',error='dt00_e.img')
        (img/'dt00_e.img').write_bytes(archive())
        (img/'dt05_e.img').unlink();(img/'dt05_e.img').mkdir()
        run(4,'language archive is a directory',error='dt05_e.img')
        (img/'dt05_e.img').rmdir();(img/'dt05_e.img').write_bytes(archive())
        for name in ('dt07.img','dt11.img'):
            (img/name).unlink();run(4,'missing shared '+name,error=name);(img/name).write_bytes(archive())
        (img/'dt05_a.img').write_bytes(b'broken optional language')
        run(0,'usable menu language accepted alongside an unused broken locale')
        (img/'dt05_a.img').unlink()
        damaged=[('empty archive',b''),('unrelated data',b'not an archive'),
                 ('truncated entry table',b'AFS\0'+struct.pack('<I',100)),
                 ('oversized entry count',b'AFS\0'+struct.pack('<I',0xffffffff)),
                 ('truncated payload',archive()[:-1])]
        bad=bytearray(archive());struct.pack_into('<II',bad,16,0xfffffff0,64)
        damaged.append(('entry end does not wrap at 4 GiB',bad))
        bad=bytearray(archive());struct.pack_into('<I',bad,16,8)
        damaged.append(('entry cannot overlap archive directory',bad))
        for label,content in damaged:
            (img/'dt06.img').write_bytes(content);run(4,label,error='dt06.img')
        (img/'dt06.img').write_bytes(archive())
        # Cross the 512-entry read boundary and retain an unused sentinel entry.
        large=b'AFS\0'+struct.pack('<I',513)+struct.pack('<II',0xffffffff,0)*512+struct.pack('<II',8192,16)
        large=large.ljust(8192,b'\0')+b'fixture payload!'
        (img/'dt06.img').write_bytes(large);run(0,'AFS directory spans multiple reads with empty sentinel entries')
        (img/'dt06.img').write_bytes(large[:-1]);run(4,'last directory batch detects truncated payload',error='dt06.img')
        (img/'dt06.img').write_bytes(archive())
        img.rename(game/'saved-img');img.symlink_to(game/'saved-img',target_is_directory=True)
        run(4,'img directory link rejected',error='img');img.unlink();(game/'saved-img').rename(img)
        (root/'launcher').write_text('wrong');run(4,'runtime directory is a file');(root/'launcher').unlink()
        (root/'launcher').symlink_to(tmp,target_is_directory=True);run(4,'symlink directory');(root/'launcher').unlink()
        data=bytearray(data);struct.pack_into('<H',data,68,0x8664);(game/'pes2013.exe').write_bytes(data)
        run(4,'64-bit executable rejected')
        if a.game_dir:
            files=[a.game_dir/'pes2013.exe',*sorted((a.game_dir/'img').glob('*.img'))]
            before={n:(n.stat().st_size,n.stat().st_mtime_ns) for n in files}
            r=subprocess.run([str(binary),str(a.game_dir),'7'],capture_output=True,text=True,timeout=30)
            assert r.returncode==0 and 'runtime error:' not in r.stderr,(r.stdout,r.stderr)
            assert before=={n:(n.stat().st_size,n.stat().st_mtime_ns) for n in files}
            reference={'passed':True,'path':str(a.game_dir),'archives':[n.name for n in files[1:]],'read_only':True}
            print(r.stdout.strip(),flush=True)
    names=['src/runtime/fextendo_startup_check.h','src/runtime/fextendo_install_check.h',
           'tests/fextendo_startup_checks.py','tests/fextendo_startup_check.c','tests/fextendo_install_fixture.py']
    report={'passed':True,'hardware_tested':False,'cases':cases,'high_requires_active_patch':True,
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},'reference_game':reference}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: '+str(len(cases))+' installation/repair/admission scenarios and High policy')
if __name__=='__main__':main()
