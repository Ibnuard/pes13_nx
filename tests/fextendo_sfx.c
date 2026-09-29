/* Original cues, BGM mixing, real worker shutdown and audout ownership. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
typedef uint32_t u32;typedef int Result;
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
typedef struct AudioOutBuffer {struct AudioOutBuffer *next;void *buffer;uint64_t buffer_size,data_size,data_offset;} AudioOutBuffer;
static int session,started,fail_init,fail_start,fail_alloc,allocations,frees,appends,flushes,released_slot;
static unsigned channels=2,rate=48000;
static AudioOutBuffer *owned[3];
static int audoutInitialize(void){if(fail_init)return 1;assert(!session);session=1;return 0;}
static void audoutExit(void){assert(session);session=0;memset(owned,0,sizeof(owned));}
static int audoutStartAudioOut(void){assert(session);if(fail_start)return 1;started=1;return 0;}
static void audoutStopAudioOut(void){assert(session);started=0;}
static unsigned audoutGetChannelCount(void){return channels;}
static unsigned audoutGetSampleRate(void){return rate;}
static int audoutGetReleasedAudioOutBuffer(AudioOutBuffer **b,u32 *n){
    *b=owned[released_slot];*n=*b!=NULL;owned[released_slot]=NULL;released_slot=(released_slot+1)%3;return 0;
}
static int audoutContainsAudioOutBuffer(AudioOutBuffer *b,bool *found){*found=false;for(int i=0;i<3;i++)*found|=owned[i]==b;return 0;}
static int audoutAppendAudioOutBuffer(AudioOutBuffer *b){
    assert(session&&started&&b->data_size<=b->buffer_size&&!b->data_offset);
    for(int i=0;i<3;i++)assert(owned[i]!=b);
    for(int i=0;i<3;i++)if(!owned[i]){owned[i]=b;appends++;return 0;}
    assert(0);return 1;
}
static void *test_alloc(size_t align,size_t bytes){
    allocations++;if(fail_alloc&&allocations==fail_alloc)return NULL;
    void *p=NULL;assert(!posix_memalign(&p,align,bytes));assert(!((uintptr_t)p%4096));return p;
}
static void test_free(void *p){if(p){assert(!session);frees++;free(p);}}
static void armDCacheFlush(void *p,size_t bytes){assert(p&&bytes==4096);flushes++;}
static void svcSleepThread(uint64_t ns){struct timespec t={ns/1000000000,ns%1000000000};nanosleep(&t,NULL);}
#define memalign test_alloc
#define free test_free
#include "../src/runtime/fextendo_sfx.h"
#undef free
static void reset(void){assert(!session&&!fx_sfx_ready&&!fx_audio_created);fail_init=fail_start=fail_alloc=allocations=frees=appends=flushes=0;rate=48000;channels=2;}
int main(int argc,char **argv){
    assert(argc==2);
    reset();fail_init=1;fx_sfx_init(argv[1]);fx_sfx_play(FX_NAV,1);fx_sfx_close();assert(!appends&&!allocations);
    reset();channels=1;fx_sfx_init(argv[1]);assert(!session&&!allocations);
    reset();rate=44100;fx_sfx_init(argv[1]);assert(!session&&!allocations);
    for(int fail=1;fail<=3;fail++){reset();fail_alloc=fail;fx_sfx_init(argv[1]);assert(!session&&!fx_audio_created&&frees>=fail-1);}
    reset();fail_start=1;fx_sfx_init(argv[1]);assert(!session&&frees>=3);
    for(int cue=0;cue<FX_CUES;cue++){
        int16_t pcm[FX_SFX_FRAMES*2];fx_sfx_pcm(pcm,FX_SFX_FRAMES,2,cue);int peak=0;
        for(int i=0;i<FX_SFX_FRAMES;i++){assert(pcm[i*2]==pcm[i*2+1]);if(abs(pcm[i*2])>peak)peak=abs(pcm[i*2]);}
        assert(peak>1000&&peak<6000&&pcm[0]==0&&pcm[9598]==0);
    }
    /* Repeated sessions release every buffer after the real worker is joined. */
    for(int session_no=0;session_no<3;session_no++){
        reset();fx_music_set(1);fx_sfx_init(argv[1]);assert(fx_sfx_ready&&fx_audio_created&&fx_music_frames>0);
        fx_sfx_play(FX_CONFIRM,1);svcSleepThread(80000000);fx_music_set(0);fx_sfx_play(FX_BACK,1);
        svcSleepThread(80000000);fx_sfx_close();fx_sfx_close();assert(appends>=3&&flushes==appends&&frees>=4&&!fx_audio_created);
    }
    /* Gain ramps, wraparound, clipping and independent cue mute without service. */
    fx_music_data=calloc(1,20);assert(fx_music_data);fx_music_frames=4;fx_music_cursor=3;
    for(int i=0;i<4;i++){fx_music_data[12+i*2]=0xff;fx_music_data[13+i*2]=0x7f;}
    int16_t out[2048];fx_music_set(1);fx_audio_mix(out,1024);assert(fx_music_cursor==3&&out[2046]>1000);
    fx_music_set(0);for(int i=0;i<25;i++)fx_audio_mix(out,1024);assert(abs(out[2046])<=1);
    fx_pending_cue=-1;fx_sfx_play(FX_NAV,0);assert(fx_pending_cue==-1);
    fx_pending_cue=FX_CONFIRM;fx_audio_mix(out,1024);assert(fx_cue_cursor==1024);
    for(int i=0;i<1024;i++)assert(out[i*2]==out[i*2+1]&&abs(out[i*2])<8000);
    free(fx_music_data);fx_music_data=NULL;fx_music_frames=0;
    puts("Original SFX/BGM: bounded PCM, independent mute, fade/loop mixing, aligned buffers, real worker join, repeated close, init failures and release-before-free passed.");
}
