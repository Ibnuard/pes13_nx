"""Render orbiting light, focus transitions and scrolling with production C code."""
from pathlib import Path
import argparse,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('assets',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    ffmpeg=shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
    movie=a.output.with_suffix('.mp4')
    code='''#include <assert.h>
#include "src/runtime/fextendo_presets.h"
#include "src/runtime/fextendo_ui.h"
int main(int argc,char **argv) {
    assert(argc==2);struct fx_art art;assert(fx_art_load(&art,argv[1]));
    uint32_t *pixels=calloc(FX_W*FX_H,4);assert(pixels);
    unsigned char *rgb=malloc(FX_W*FX_H*3);assert(rgb);
    struct fx_canvas c={pixels,FX_W,&art};
    struct fx_view v={.screen=FX_HOME,.sound=1,.timestamp=1,.battery=82,.wall_time=1800000000,.last_played=1799992800};
    for(unsigned frame=0;frame<570;frame++){
        v.frame=frame;v.splash_ms=frame<24?800-frame*1000/30:0;v.tile=(frame>=115&&frame<180)||frame>=245;
        if(frame>=290&&frame<470){v.screen=FX_SETTINGS;v.row=(frame-290)/30;}
        else if(frame>=470){v.screen=FX_LOADING;}
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
            '-video_size','1280x720','-framerate','30','-i','pipe:0','-an','-c:v','libx264',
            '-preset','medium','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)],stdin=renderer.stdout)
        renderer.stdout.close()
        if encoder.wait() or renderer.wait():raise RuntimeError('Preview rendering failed')
    if a.output.suffix=='.gif':
        subprocess.run([ffmpeg,'-v','error','-y','-i',str(movie),'-filter_complex',
            '[0:v]fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse=dither=bayer:bayer_scale=4',
            '-loop','0',str(a.output)],check=True)
    print(movie)
    if a.output.suffix=='.gif':print(a.output)
if __name__=='__main__':main()
