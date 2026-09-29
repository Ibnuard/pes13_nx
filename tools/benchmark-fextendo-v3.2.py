"""Compare CPU render cost with the exact v3.1 package. Host numbers are not Switch FPS."""
from pathlib import Path
import argparse,hashlib,json,platform,statistics,subprocess,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]
BASE_SHA='3fd0cab7f63c0733045e322e56cd39b302ea21e5bb53d16f66ac08555f88d6f3'
CODE=r'''
#include <time.h>
#include <assert.h>
#include "fextendo_presets.h"
#include "fextendo_renderers.h"
#include "fextendo_ui.h"
static double clock_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1000.0+t.tv_nsec/1000000.0;}
int main(int argc,char **argv){
 assert(argc==2);struct fx_art art;double start=clock_ms();assert(fx_art_load(&art,argv[1]));
 printf("{\"prepare_ms\":%.4f,\"scenes\":[",clock_ms()-start);
 uint32_t *p=calloc(FX_W*FX_H,4);assert(p);struct fx_canvas c={p,FX_W,&art};struct fx_view v={.sound=1,.battery=82};
 for(int scene=0;scene<4;scene++){
  v.screen=scene==2?FX_SETTINGS:scene==3?FX_LOADING:FX_HOME;v.tile=scene==1;v.tile_mix=v.tile;
  start=clock_ms();
  for(int f=0;f<180;f++){
   v.frame=f;if(scene==2){v.row=(f/30)%6;fx_motion_step(&v,33);}
   else if(scene<2){v.tile=(f/30)%2;fx_motion_step(&v,33);}
   fx_render(&c,&v);
  }
  printf("%s%.4f",scene?",":"",(clock_ms()-start)/180);
 }
 puts("]}");fx_art_free(&art);free(p);
}
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);a=ap.parse_args();work=a.work.resolve()
    base=ROOT/'dist/pes13-fextendo-v3.1.zip';assert sha(base)==BASE_SHA
    receipt=json.loads((work/'runtime/runtime-build.json').read_text())
    header=ROOT/'src/runtime/fextendo_ui.h';assert receipt['patch_sources']['src/runtime/fextendo_ui.h']==sha(header)
    results={}
    with tempfile.TemporaryDirectory(prefix='fextendo-bench-') as d:
        tmp=Path(d)
        for mode in ('v3.1','v3.2'):
            path=tmp/mode;path.mkdir()
            for name in ('fextendo_ui.h','fextendo_presets.h'):
                if mode=='v3.1':
                    with zipfile.ZipFile(base) as z:data=z.read('source/src/runtime/'+name)
                else:data=(ROOT/'src/runtime'/name).read_bytes()
                (path/name).write_bytes(data)
            (path/'fextendo_renderers.h').write_bytes((ROOT/'src/runtime/fextendo_renderers.h').read_bytes())
            (path/'bench.c').write_text(CODE)
            subprocess.run(['clang','-O3','-std=c11','-D_POSIX_C_SOURCE=200809L',str(path/'bench.c'),'-o',str(path/'bench')],check=True)
        # Alternate versions to avoid measuring only one under a warm/cold host.
        samples={k:[] for k in ('v3.1','v3.2')}
        for _ in range(3):
            for mode in samples:
                samples[mode].append(json.loads(subprocess.check_output([str(tmp/mode/'bench'),str(work/'package/switch/pes13-fex')],text=True)))
        names=('home_start_pes','home_start_settings','settings_scroll','loading')
        for mode,rows in samples.items():
            results[mode]={'prepare_ms_median':statistics.median(r['prepare_ms'] for r in rows),
                'render_ms_median':{name:statistics.median(r['scenes'][i] for r in rows) for i,name in enumerate(names)},'samples':rows}
    speedup={name:round(results['v3.1']['render_ms_median'][name]/results['v3.2']['render_ms_median'][name],2) for name in names}
    report={'passed':True,'hardware_tested':False,'scope':'Host CPU renderer only; no Switch display/GPU timing',
        'host':platform.platform(),'compiler':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
        'baseline_zip_sha256':BASE_SHA,'native_elf_sha256':receipt['native_elf_sha256'],'results':results,'speedup':speedup,
        'cache_bytes':6*1280*720*4+3*sum(w*w*4 for w in range(212,261)),
        'baseline_cache_bytes':4*1280*720*4+sum(w*w*4 for w in range(212,261)),
        'source_hashes':{n:sha(ROOT/n) for n in ('tools/benchmark-fextendo-v3.2.py','src/runtime/fextendo_ui.h','src/runtime/fextendo_presets.h')}}
    (work/'ui-benchmark.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
