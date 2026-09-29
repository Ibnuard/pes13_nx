"""Pack Fextendo stadium art, user controller sprites and OFL Inter glyphs."""
from pathlib import Path
import argparse, hashlib, json, struct, io, importlib.util
import cairosvg
from PIL import Image, ImageOps, ImageFont, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]

def build(out):
    out.mkdir(parents=True, exist_ok=True)
    # Asset conversion only; menus, cards, focus and dialogs are rendered in C.
    bg = ImageOps.fit(Image.open(ROOT/'assets/fextendo-v2/stadium.png').convert('RGBA'), (1280,720))
    (out/'background.rgba').write_bytes(bg.tobytes())
    (out/'blur.rgba').write_bytes(bg.filter(ImageFilter.GaussianBlur(18)).tobytes())
    logo = Image.open(ROOT/'assets/logo.png').convert('RGBA').resize((480,158), Image.Resampling.LANCZOS)
    (out/'logo.rgba').write_bytes(logo.tobytes())
    icon=Image.open(ROOT/'assets/icon.png').convert('RGBA').resize((256,256),Image.Resampling.LANCZOS)
    (out/'icon.rgba').write_bytes(icon.tobytes())
    for name in ('settings','credits'):
        im=Image.open(ROOT/f'assets/fextendo-v3.2/{name}-flat.png').convert('RGBA')
        (out/(name+'-icon.rgba')).write_bytes(ImageOps.fit(im,(256,256),method=Image.Resampling.LANCZOS).tobytes())
    for name,filename,size in (('gamepad','gamepad-flat.png',(128,96)),('wordmark','wordmark.png',(600,128))):
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
            svg=ROOT/f'assets/Solid Duo/Dark theme/{name}.svg'
            im=Image.open(io.BytesIO(cairosvg.svg2png(url=str(svg),output_width=320,output_height=320))).convert('RGBA')
            f.write(im.resize((80,80),Image.Resampling.LANCZOS).tobytes())
    for size, weight in ((20,400), (26,600), (40,600), (14,400)):
        font = ImageFont.truetype(str(ROOT/'assets/fonts/Inter/Inter.ttf'),size*4)
        font.set_variation_by_axes([max(14,min(32,size)),weight])
        for c in range(32,127):
            hx,hy,hr,hb = font.getbbox(chr(c),anchor='ls')
            x,y=hx//4,hy//4;r,b=(hr+3)//4,(hb+3)//4;w,h=r-x,b-y
            tile=Image.new('L',(max(1,w*4),max(1,h*4)))
            ImageDraw.Draw(tile).text((-x*4,-y*4),chr(c),font=font,fill=255,anchor='ls')
            records.append(struct.pack('<IhhhhHH',len(pixels),x,y,w,h,round(font.getlength(chr(c))/4),0))
            pixels.extend(tile.resize((w,h),Image.Resampling.LANCZOS).tobytes() if w*h else b'')
    (out/'font.bin').write_bytes(b'FXF2'+struct.pack('<I',len(pixels))+b''.join(records)+pixels)
    Image.open(ROOT/'assets/icon.png').convert('RGB').save(out/'nro-icon.jpg',quality=97,subsampling=0)
    # Small grayscale glyph atlas owned only by the optional in-game overlay.
    tf=ImageFont.truetype(str(ROOT/'assets/fonts/Inter/Inter.ttf'),72)
    tf.set_variation_by_axes([18,600]);glyphs=bytearray()
    for ch in '0123456789:.T+':
        tile=Image.new('L',(56,112));ImageDraw.Draw(tile).text((28,76),ch,font=tf,fill=255,anchor='ms')
        glyphs.extend(tile.resize((14,28),Image.Resampling.LANCZOS).tobytes())
    (out/'timestamp-font.bin').write_bytes(bytes(glyphs))
    spec=importlib.util.spec_from_file_location('fextendo_audio',ROOT/'tools/build-fextendo-audio.py')
    audio=importlib.util.module_from_spec(spec);spec.loader.exec_module(audio);audio.build(out)
    inputs=['assets/fextendo-v3.2/settings-flat.png','assets/fextendo-v3.2/credits-flat.png','tools/build-fextendo-audio.py','assets/fextendo-v2/stadium.png','assets/fextendo-v2/gamepad-flat.png','assets/fextendo-v2/wordmark.png',
            'assets/logo.png','assets/icon.png','assets/fonts/Inter/Inter.ttf','assets/fonts/Inter/OFL.txt']
    inputs += [f'assets/Solid Duo/Dark theme/{n}.svg' for n in buttons]
    manifest={'format':4,'font':'Inter','font_source':'https://github.com/google/fonts/tree/main/ofl/inter','buttons':buttons,
              'inputs':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in inputs},
              'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.suffix in ('.rgba','.bin','.jpg')}}
    (out/'assets.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);build(p.parse_args().output)
