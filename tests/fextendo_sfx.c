/* Exercise the production PCM generator and audout buffer ownership. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
typedef uint32_t u32;
typedef int Result;
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
typedef struct AudioOutBuffer {struct AudioOutBuffer *next;void *buffer;uint64_t buffer_size,data_size,data_offset;} AudioOutBuffer;
static int session,started,fail_init,fail_start,fail_alloc,allocations,frees,appends,flushes;
static unsigned channels=2,rate=48000;
static AudioOutBuffer *owned[4];
static int audoutInitialize(void){if(fail_init)return 1;assert(!session);session=1;return 0;}
static void audoutExit(void){assert(session);session=0;memset(owned,0,sizeof(owned));}
static int audoutStartAudioOut(void){assert(session);if(fail_start)return 1;started=1;return 0;}
static void audoutStopAudioOut(void){assert(session);started=0;}
static unsigned audoutGetChannelCount(void){return channels;}
static unsigned audoutGetSampleRate(void){return rate;}
static int audoutGetReleasedAudioOutBuffer(AudioOutBuffer **b,u32 *n){*b=NULL;*n=0;return 0;}
static int audoutContainsAudioOutBuffer(AudioOutBuffer *b,bool *found){*found=false;for(int i=0;i<4;i++)*found|=owned[i]==b;return 0;}
static int audoutAppendAudioOutBuffer(AudioOutBuffer *b){
    assert(session&&started&&b->data_size<=b->buffer_size&&!b->data_offset);
    for(int i=0;i<4;i++)assert(owned[i]!=b);
    for(int i=0;i<4;i++)if(!owned[i]){owned[i]=b;appends++;return 0;}
    assert(0);return 1;
}
static void *test_alloc(size_t align,size_t bytes){
    allocations++;if(fail_alloc&&allocations==fail_alloc)return NULL;
    void *p=NULL;assert(!posix_memalign(&p,align,bytes));assert(!((uintptr_t)p%4096));return p;
}
static void test_free(void *p){if(p){assert(!session);frees++;free(p);}}
static void armDCacheFlush(void *p,size_t bytes){assert(p&&bytes==19200);flushes++;}
#define memalign test_alloc
#define free test_free
#include "../src/runtime/fextendo_sfx.h"
#undef free
static void reset(void){assert(!session&&!fx_sfx_ready);fail_init=fail_start=fail_alloc=allocations=frees=appends=flushes=0;rate=48000;channels=2;}
int main(void){
    reset();fail_init=1;fx_sfx_init();fx_sfx_play(FX_NAV,1);fx_sfx_close();assert(!appends&&!allocations);
    reset();channels=1;fx_sfx_init();assert(!session&&!allocations);
    reset();rate=44100;fx_sfx_init();assert(!session&&!allocations);
    for(int fail=1;fail<=4;fail++){reset();fail_alloc=fail;fx_sfx_init();assert(!session&&frees==fail-1);}
    reset();fail_start=1;fx_sfx_init();assert(!session&&frees==4&&flushes==4);
    reset();fx_sfx_init();assert(fx_sfx_ready&&flushes==4);
    for(int cue=0;cue<FX_CUES;cue++){
        AudioOutBuffer *b=&fx_sfx_buffers[cue];int16_t *pcm=b->buffer;int peak=0;
        for(int i=0;i<FX_SFX_FRAMES;i++){
            assert(pcm[i*2]==pcm[i*2+1]);int v=abs(pcm[i*2]);if(v>peak)peak=v;
        }
        assert(peak>1000&&peak<6000&&pcm[0]==0&&pcm[9598]==0);
        for(unsigned i=b->data_size;i<b->buffer_size;i++)assert(!((unsigned char*)b->buffer)[i]);
        fx_sfx_play(cue,0);assert(appends==cue);
        fx_sfx_play(cue,1);fx_sfx_play(cue,1);assert(appends==cue+1);
    }
    owned[0]=NULL;fx_sfx_play(FX_NAV,1);assert(appends==5);
    fx_sfx_close();fx_sfx_close();assert(!session&&frees==4);
    fx_sfx_play(FX_NAV,1);assert(appends==5);
    puts("Menu SFX: bounded stereo PCM, aligned/flushed buffers, mute, busy-buffer reuse, partial setup failure and release-before-free passed.");
}
