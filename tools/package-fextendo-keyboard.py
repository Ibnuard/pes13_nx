"""Package a locally tested keyboard preview without changing release inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'local/fex3/keyboard-v4')
    p.add_argument('--output',type=Path,default=ROOT/'dist/pes13-fextendo-keyboard-preview-v4.zip')
    a=p.parse_args();work=a.build.resolve();out=a.output.resolve()
    report=json.loads((work/'build-report.json').read_text())
    assert report['passed'] and report['native_keyboard_preview'] and not report['hardware_tested']
    assert sha((work/'native-build/wine-nx-runtime.elf').read_bytes())==report['native_elf_sha256']
    nro=(work/'pes13-fex.nro').read_bytes();assert sha(nro)==report['nro_sha256']
    for name,digest in report['feature_sources'].items():assert sha((ROOT/name).read_bytes())==digest,name
    files={'switch/pes13-fex/pes13-fex.nro':nro,
           'evidence/build-report.json':(work/'build-report.json').read_bytes(),
           'source/generated-runtime-changes.patch':(work/'generated-controller-changes.patch').read_bytes()}
    overlay=report.get('live_keyboard_overlay',False)
    tests=['keyboard','host-keyboard','focus','overlay' if overlay else 'delivery','controllers','hid-startup','silent','startup','maintenance']
    if overlay:tests.append('render')
    test_paths=set()
    for name in tests:
        data=(work/(name+'-test.json')).read_bytes();test=json.loads(data)
        assert test['passed'] and test['native_elf_sha256']==report['native_elf_sha256'],name
        for path,digest in test.get('test_sources',{}).items():
            assert sha((ROOT/path).read_bytes())==digest,path;test_paths.add(path)
        for path,digest in test.get('screenshots',{}).items():
            assert sha((work/path).read_bytes())==digest,path
            files['evidence/'+path]=(work/path).read_bytes()
        files['evidence/'+name+'-test.json']=data
    paths=set(report['feature_sources'])|test_paths|{
        'tests/fextendo_keyboard.c','tests/fextendo_keyboard.py','tests/fextendo_keyboard_binary.py',
        'tests/fextendo_keyboard_focus.py','tests/fextendo_keyboard_delivery.py',
        'tests/fextendo_gamepad_binary.py','tests/fextendo_gamepad_startup.py',
        'docs/FEXTENDO-NATIVE-KEYBOARD.md','tools/package-fextendo-keyboard.py','assets/README.md'}
    for name in sorted(paths):files['source/'+name]=(ROOT/name).read_bytes()
    files['README.txt']='''PES13 FEXTendo - Native keyboard preview v3

Fixes text stopping after its first character: Wine's hardware-input API
returns zero for success; the bridge now interprets this status correctly.
Manual input also survives transient caret/IME changes in the same window.
The v2 keyboard-confirmation fix is retained.

Back up your working NRO. Copy the switch folder to the SD root, replacing
switch/pes13-fex/pes13-fex.nro. Keep the existing FEX DLL, NSP, launcher assets,
game files, saves and configuration. Only the NRO is supplied here.

Retest: Master League -> Nama Manager in PES13.
If the native keyboard does not appear automatically, hold L1 + R1 (L + R)
then click L3 once. Horizontal single Joy-Con: hold SL + SR, click its stick
once. There is no stick hold timer. Either player can open the keyboard.
Release all controls. Enter Hallo, accept and wait for the whole word.
Also try hallo and HaLLo to check lowercase, Shift and repeated letters.
Confirm the name within PES. The keyboard does not automatically press Enter.
Cancel leaves text unchanged. Standard Edit fields are prefilled/replaced;
custom PES fields receive inserted text, so clear an old name in PES first.

Automatic detection and PES text acceptance REQUIRE A SWITCH TEST.
Report separately: automatic opening, shortcut opening, and text insertion.
Two-controller reconnect and the approved production baseline are retained.
Runtime logging remains disabled. This is not a published production release.

Detailed instructions and limitations: source/docs/FEXTENDO-NATIVE-KEYBOARD.md
The source and evidence folders do not need to be copied to the SD card.
'''.encode()
    if overlay:
        files['README.txt']='''PES13 FEXTendo - Live keyboard preview v4

Back up your working NRO. Copy the switch folder to the SD root, replacing
switch/pes13-fex/pes13-fex.nro. Keep the existing FEX DLL, NSP, launcher assets,
game files, saves and configuration. Only the NRO is supplied here. Controller
helper sprites are embedded in the NRO; no new asset files are required.

Test in Master League -> Manager Name. Activate the name field, hold L1 + R1
(L + R), then click L3 once. Horizontal single Joy-Con: hold SL + SR and click
its stick once. Either player can open it; that player controls the keyboard.
Release all buttons/sticks after opening. The game stays visible and running.

Stick/D-pad: select a key. A: type/select. B: Backspace. X: one-shot Shift.
Y: move keyboard between the top and bottom half. L/R (SL/SR on a single
Joy-Con): move the text cursor. Plus: Enter; left single Joy-Con uses Minus.
Full controllers: Minus closes. Every controller can select the Close key.
Touchscreen typing is available in handheld mode.

To replace Nunu with Bejo, place the game cursor after Nunu, press Backspace
four times, then type Bejo. Try changing a letter in the middle with Left,
Right and Delete. Close keeps edits already made and finishes queued input;
it does NOT undo edits or implicitly press Enter. Enter is a separate action.
This keyboard edits the game field directly; it does not read the old text
into a separate field or automatically select/delete it.

Standard Windows Edit fields retain the native Switch keyboard with prefill,
replace and Cancel. Custom game fields use this live overlay. Auto-opening
still requires a detectable text-entry signal; use the shortcut otherwise.

Retest with P1/P2, full pads, paired and horizontal Joy-Con, focus changes and
disconnect/reconnect. Reconnect cancels pending keys and retains FEXTendo's
pause-until-Continue behavior. The production-v1/launch-fix baseline and silent
runtime remain. The preview UI is English and uses existing controller sprites.

Host/sanitizer and linked ARM64 checks passed. PES13 acceptance, Switch VI
presentation and frame-time impact still REQUIRE A SWITCH TEST. This is not
a published production release. Keep preview v3 available for rollback.

Design reference: autorunhq/autorun, commit c889e4e. This implementation uses
FEXTendo's controller normalization, UI/font and independent VI layer.
Details: source/docs/FEXTENDO-NATIVE-KEYBOARD.md
The source and evidence folders do not need to be copied to the SD card.
'''.encode()
    files['manifest.json']=(json.dumps({'preview':True,'hardware_tested':False,
        'files':{name:sha(data) for name,data in files.items()}},indent=2)+'\n').encode()
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert {n for n in z.namelist() if n.startswith('switch/')}=={'switch/pes13-fex/pes13-fex.nro'}
        for name,digest in json.loads(z.read('manifest.json'))['files'].items():assert sha(z.read(name))==digest,name
    target=out.with_suffix('.nro');shutil.copy2(work/'pes13-fex.nro',target)
    out.with_suffix('.sha256').write_text(f'{sha(out.read_bytes())}  {out.name}\n{sha(nro)}  {target.name}\n')
    print(json.dumps({'zip':str(out),'bytes':out.stat().st_size,'nro_sha256':sha(nro)},indent=2))

if __name__=='__main__':main()
