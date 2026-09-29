"""Render the v3.2 UI from production C, with the original BGM for auditioning."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,tempfile,wave
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('assets',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args();a.output=a.output.resolve();a.output.parent.mkdir(parents=True,exist_ok=True)
    ffmpeg=shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
    movie=a.output.with_suffix('.mp4');music=a.output.parent/'background-music.wav'
    payload=(a.assets/'launcher/background-music.bin').read_bytes()
    assert payload[:4]==b'FXM1'
    with wave.open(str(music),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(payload[12:])
    code='''#include <assert.h>
#include "src/runtime/fextendo_presets.h"
#include "src/runtime/fextendo_renderers.h"
#include "src/runtime/fextendo_ui.h"
int main(int argc,char **argv) {
    assert(argc==2);struct fx_art art;assert(fx_art_load(&art,argv[1]));
    uint32_t *pixels=calloc(FX_W*FX_H,4);assert(pixels);
    unsigned char *rgb=malloc(FX_W*FX_H*3);assert(rgb);
    struct fx_canvas c={pixels,FX_W,&art};
    struct fx_view v={.screen=FX_HOME,.sound=1,.music=1,.timestamp=1,.battery=82,.wall_time=1800000000,.last_played=1799992800};
    for(unsigned frame=0;frame<780;frame++){
        v.frame=frame;v.splash_ms=frame<72?2400-frame*1000/30:0;
        v.screen=FX_HOME;
        if(frame<162)v.tile=0;
        else if(frame<237)v.tile=1;
        else if(frame<312)v.tile=2;
        else if(frame<492){v.screen=FX_SETTINGS;v.row=(frame-312)/25;if(v.row>6)v.row=6;}
        else if(frame<642){v.screen=FX_CREDITS;v.credit_page=frame>=567;}
        else if(frame<690)v.tile=0;
        else v.screen=FX_LOADING;
        fx_motion_step(&v,1000.f/30);fx_render(&c,&v);
        for(unsigned p=0;p<FX_W*FX_H;p++){rgb[p*3]=pixels[p];rgb[p*3+1]=pixels[p]>>8;rgb[p*3+2]=pixels[p]>>16;}
        assert(fwrite(rgb,1,FX_W*FX_H*3,stdout)==FX_W*FX_H*3);
    }
    free(rgb);free(pixels);fx_art_free(&art);
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'preview.c';exe=Path(tmp)/'preview';src.write_text(code)
        subprocess.run(['clang','-O2','-std=c11','-D_POSIX_C_SOURCE=200809L','-I',str(ROOT),str(src),'-o',str(exe)],check=True)
        renderer=subprocess.Popen([str(exe),str(a.assets.resolve())],stdout=subprocess.PIPE)
        encoder=subprocess.Popen([ffmpeg,'-v','error','-y','-f','rawvideo','-pixel_format','rgb24',
            '-video_size','1280x720','-framerate','30','-i','pipe:0','-stream_loop','-1','-i',str(music),
            '-af','volume=0.65,afade=t=in:d=0.12,afade=t=out:st=22.7:d=0.3',
            '-c:a','aac','-b:a','128k','-shortest','-c:v','libx264',
            '-preset','medium','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)],stdin=renderer.stdout)
        renderer.stdout.close()
        if encoder.wait() or renderer.wait():raise RuntimeError('Preview rendering failed')
    outputs=[movie,music]
    if a.output.suffix=='.gif':
        subprocess.run([ffmpeg,'-v','error','-y','-i',str(movie),'-filter_complex',
            '[0:v]fps=10,scale=768:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse=dither=bayer:bayer_scale=4',
            '-loop','0',str(a.output)],check=True);outputs.append(a.output)
    # Re-encode current sanitizer screenshots, never a stale generated mockup.
    for ppm in sorted(a.output.parent.glob('*.ppm')):
        png=ppm.with_suffix('.png');Image.open(ppm).save(png);outputs.append(png)
    for name,second in [('settings-music',15.6),('carousel-settings',7.4),('carousel-credits',9.8)]:
        png=a.output.parent/(name+'.png')
        subprocess.run([ffmpeg,'-v','error','-y','-ss',str(second),'-i',str(movie),'-frames:v','1',str(png)],check=True)
        outputs.append(png)
    sources=['tools/render-fextendo-preview.py','tools/build-fextendo-assets.py','tools/build-fextendo-audio.py',
        'tests/fextendo_ui.c','src/runtime/fextendo_ui.h','src/runtime/fextendo_presets.h']
    receipt={'renderer':'production C on host','hardware_capture':False,'fps':30,'seconds':26,
        'audio':'Original synthesized BGM; movie does not simulate controller SFX or device audio timing.',
        'sample_values':'Battery 82%, last played 2 hours ago are examples.',
        'sources':{n:sha(ROOT/n) for n in sources},'assets_manifest_sha256':sha(a.assets/'launcher/assets.json'),
        'files':{p.name:sha(p) for p in outputs}}
    (a.output.parent/'preview.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(movie)
if __name__=='__main__':main()
