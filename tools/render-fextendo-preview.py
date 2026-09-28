"""Render a five-second glossy UI loop using the production C renderer."""
from pathlib import Path
import argparse,subprocess,tempfile
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('assets',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args()
    code='''#include <assert.h>
#include "src/runtime/fextendo_presets.h"
#include "src/runtime/fextendo_ui.h"
int main(int argc,char **argv) {
    assert(argc==2);struct fx_art art;assert(fx_art_load(&art,argv[1]));
    uint32_t *pixels=calloc(FX_W*FX_H,4);assert(pixels);
    unsigned char *rgb=malloc(FX_W*FX_H*3);assert(rgb);
    struct fx_canvas c={pixels,FX_W,&art};struct fx_view v={.screen=FX_HOME};
    for(unsigned frame=0;frame<150;frame+=5){
        v.frame=frame;fx_render(&c,&v);
        for(unsigned p=0;p<FX_W*FX_H;p++){rgb[p*3]=pixels[p];rgb[p*3+1]=pixels[p]>>8;rgb[p*3+2]=pixels[p]>>16;}
        assert(fwrite(rgb,1,FX_W*FX_H*3,stdout)==FX_W*FX_H*3);
    }
    free(rgb);free(pixels);fx_art_free(&art);
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'preview.c';exe=Path(tmp)/'preview';src.write_text(code)
        subprocess.run(['clang','-O2','-std=c11','-D_POSIX_C_SOURCE=200809L','-I',str(ROOT),str(src),'-o',str(exe)],check=True)
        raw=subprocess.check_output([str(exe),str(a.assets.resolve())])
    size=1280*720*3;assert len(raw)==size*30
    first=Image.frombytes('RGB',(1280,720),raw[:size]);palette=first.quantize(colors=256)
    frames=[Image.frombytes('RGB',(1280,720),raw[i*size:(i+1)*size]).quantize(palette=palette) for i in range(30)]
    frames[0].save(a.output,save_all=True,append_images=frames[1:],duration=[170,170,160]*10,loop=0,optimize=True)
    print(a.output)
if __name__=='__main__':main()
