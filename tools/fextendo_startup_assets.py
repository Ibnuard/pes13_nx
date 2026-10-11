"""Embed the existing launcher wordmark and font; the checker needs no SD art."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=('font.dat','wordmark.rgba')

def generate(output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    chunks=['/* Generated from assets/startup; see tools/fextendo_startup_assets.py. */\n#include <stdint.h>\n']
    for filename,symbol in zip(FILES,('font','wordmark')):
        data=(ROOT/'assets/startup'/filename).read_bytes()
        if symbol=='font':assert data[:4]==b'FXF2' and len(data)<1024*1024
        else:assert len(data)==600*128*4
        chunks.append('const unsigned char fx_boot_'+symbol+'[] = {\n')
        chunks.extend(','.join(str(n) for n in data[i:i+24])+',\n' for i in range(0,len(data),24))
        chunks.append('};\nconst unsigned fx_boot_'+symbol+'_size = '+str(len(data))+';\n')
    output.write_text(''.join(chunks))
    return {str((ROOT/'assets/startup'/n).relative_to(ROOT)):hashlib.sha256((ROOT/'assets/startup'/n).read_bytes()).hexdigest() for n in FILES}
