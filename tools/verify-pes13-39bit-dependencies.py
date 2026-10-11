"""Record the static libraries actually linked against the approved r6 base."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--startup-checks',action='store_true',help='Permit curl for the explicitly requested startup repair feature')
    p.add_argument('--sdk',type=Path,default=Path('/opt/devkitpro'))
    p.add_argument('--mesa',type=Path,default=Path('/home/blekjek/pes13-build/mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'))
    a=p.parse_args();old=json.loads((a.base/'build-report.json').read_text())['native_dependencies']
    files={'mesa/'+p.name:p for p in a.mesa.glob('*.a')}
    files['sdk/libnx/lib/libnx.a']=a.sdk/'libnx/lib/libnx.a'
    files.update({'sdk/'+p.relative_to(a.sdk).as_posix():p for p in (a.sdk/'portlibs/switch/lib').glob('*.a')})
    current={n:sha(p) for n,p in sorted(files.items())}
    drift={n:{'baseline':old[n],'current':current.get(n)} for n in sorted(old) if old[n]!=current.get(n)}
    ninja=a.build/'build.ninja';text=ninja.read_text()
    added={n:h for n,h in current.items() if n not in old}
    added_linked={n:h for n,h in added.items() if str(files[n]) in text}
    permitted={'sdk/portlibs/switch/lib/libcurl.a'} if a.startup_checks else set()
    unapproved=set(added_linked)-permitted
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({'passed':not drift and not unapproved,
        'native_dependencies':current,'differences':drift,'added_libraries_linked':added_linked,
        'permitted_startup_dependencies':sorted(permitted),'added_sdk_libraries_not_linked':{n:h for n,h in added.items() if n not in added_linked},'link_spec_sha256':sha(ninja)},indent=2)+'\n')
    if drift or unapproved:raise SystemExit('Linked dependencies differ from the approved r6 runtime; see receipt')
    print('PASS: '+str(len(old))+' baseline fingerprints match; additions limited to requested startup repair')


if __name__=='__main__':main()
