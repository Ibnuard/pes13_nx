"""Pack Fextendo stadium art, user controller sprites and OFL Inter glyphs."""
from pathlib import Path
import argparse, hashlib, json, struct
from PIL import Image, ImageOps, ImageFont, ImageDraw

ROOT = Path(__file__).resolve().parents[1]

def build(out):
    out.mkdir(parents=True, exist_ok=True)
    # Asset conversion only; menus, cards, focus and dialogs are rendered in C.
    bg = ImageOps.fit(Image.open(ROOT/'assets/fextendo-v2/stadium.png').convert('RGBA'), (1280,720))
    (out/'background.rgba').write_bytes(bg.tobytes())
    logo = Image.open(ROOT/'assets/logo.png').convert('RGBA').resize((480,158), Image.Resampling.LANCZOS)
    (out/'logo.rgba').write_bytes(logo.tobytes())
    icon=Image.open(ROOT/'assets/icon.png').convert('RGBA').resize((238,238),Image.Resampling.LANCZOS)
    (out/'icon.rgba').write_bytes(icon.tobytes())
    for name,filename,size in (('gamepad','gamepad-flat.png',(64,48)),('wordmark','wordmark.png',(300,64))):
        im=Image.open(ROOT/'assets/fextendo-v2'/filename).convert('RGBA')
        im=im.crop(im.getbbox())
        fitted=ImageOps.contain(im,size,Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',size)
        canvas.paste(fitted,((size[0]-fitted.width)//2,(size[1]-fitted.height)//2))
        (out/(name+'.rgba')).write_bytes(canvas.tobytes())
    records, pixels = [], bytearray()
    buttons=['A_Button','B_Button','L_Button','R_Button','Plus_Button','Home_Button','Y_Button']
    with (out/'buttons.rgba').open('wb') as f:
        for name in buttons:
            im=Image.open(ROOT/f'assets/Solid Duo/Dark theme/{name}.png').convert('RGBA')
            f.write(im.resize((40,40),Image.Resampling.LANCZOS).tobytes())
    for size, weight in ((20,400), (26,600), (40,600)):
        font = ImageFont.truetype(str(ROOT/'assets/fonts/Inter/Inter.ttf'),size)
        font.set_variation_by_axes([max(14,min(32,size)),weight])
        for c in range(32,127):
            x,y,r,b = font.getbbox(chr(c),anchor='ls');w,h=r-x,b-y
            tile=Image.new('L',(max(1,w),max(1,h)))
            ImageDraw.Draw(tile).text((-x,-y),chr(c),font=font,fill=255,anchor='ls')
            records.append(struct.pack('<IhhhhHH',len(pixels),x,y,w,h,round(font.getlength(chr(c))),0))
            pixels.extend(tile.tobytes() if w*h else b'')
    (out/'font.bin').write_bytes(b'FXF1'+struct.pack('<I',len(pixels))+b''.join(records)+pixels)
    inputs=['assets/fextendo-v2/stadium.png','assets/fextendo-v2/gamepad-flat.png','assets/fextendo-v2/wordmark.png',
            'assets/logo.png','assets/icon.png','assets/fonts/Inter/Inter.ttf','assets/fonts/Inter/OFL.txt']
    inputs += [f'assets/Solid Duo/Dark theme/{n}.png' for n in buttons]
    manifest={'format':2,'font':'Inter','font_source':'https://github.com/google/fonts/tree/main/ofl/inter','buttons':buttons,
              'inputs':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in inputs},
              'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.suffix in ('.rgba','.bin')}}
    (out/'assets.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);build(p.parse_args().output)
