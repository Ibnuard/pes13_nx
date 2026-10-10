"""Compile the delivered/candidate FEX tracker, with real mprotect and NT mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_includes(text):
    return re.sub(r'^\s*#(?:include|pragma)[^\n]*\n', '', text, flags=re.MULTILINE)


def function(text, signature):
    start=text.index(signature)
    body=text.index('{',start)
    pos, depth=body+1, 1
    while depth:
        depth += (text[pos]=='{')-(text[pos]=='}')
        pos+=1
    return text[start:pos]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    template=root/'tests/fex_protect_roundtrip.cpp'
    interval=args.work/'source/FEXCore/include/FEXCore/Utils/IntervalList.h'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result={}
    inputs={'tests/fex_protect_roundtrip.cpp':sha(template),'tests/fex_protect_roundtrip.py':sha(Path(__file__)),
            'FEXCore/Utils/IntervalList.h':sha(interval)}
    for label,fixed in (('before',0),('source',1)):
        common=args.work/label/'Source/Windows/Common'
        header=common/'InvalidationTracker.h'
        impl=common/'InvalidationTracker.cpp'
        module=args.work/label/'Source/Windows/WOW64/Module.cpp'
        tracker='\n'.join(no_includes(p.read_text()) for p in (interval,header,impl))
        notify=function(module.read_text(),'void BTCpuNotifyMemoryProtect(')
        program=template.read_text().replace('// INSERT_REAL_FEX_HERE',tracker).replace('// INSERT_REAL_NOTIFICATION_HERE',notify)
        generated=args.output.parent/(label+'-protect.cpp')
        generated.write_text(program)
        executable=args.output.parent/(label+'-protect-test')
        subprocess.run(['g++','-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-changes-meaning',
                        '-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie','-pthread',
                        '-DFIXED_BUILD='+str(fixed),str(generated),'-o',str(executable)],check=True)
        output=subprocess.check_output([str(executable)],text=True,timeout=30)
        result[label]=json.loads(output)
        assert result[label]['passed'] and result[label]['fixed']==bool(fixed)
        for p in (header,impl,module): inputs[str(p.relative_to(args.work))]=sha(p)
    report={'passed':True,'baseline_bug_reproduced':True,'candidate':result['source'],'baseline':result['before'],
            'source_hashes':inputs,'checks':['VirtualProtect old-protection round trip on private and image pages',
                'actual OS-protected write fails before and succeeds after recovery',
                'explicit RX and transient RWX text returns to fast nonwritable classification',
                'failure restores traps and preserves syscall error/output values',
                'first-page semantics, invalid inputs, guard/noaccess and query/untrap failures',
                'compiler cannot retrap while the protection syscall is pending'],
            'hardware_tested':False,'scope':'Actual FEX tracker/notification source, NT model and Linux mprotect; not full Switch execution.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
