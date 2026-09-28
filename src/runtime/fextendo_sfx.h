/* LGPL-2.1-or-later. Original soft mallet/click cues and an original ambient
 * loop. One launcher-only mixer owns audout; no decoding or SD reads in play. */
#include <pthread.h>
enum fx_cue { FX_NAV,FX_CONFIRM,FX_BACK,FX_ERROR,FX_CUES };
#define FX_SFX_FRAMES 4800
#define FX_AUDIO_FRAMES 1024
#define FX_AUDIO_BUFFERS 3
#define FX_AUDIO_BYTES 4096
static void fx_sfx_pcm(int16_t *samples,unsigned frames,unsigned channels,enum fx_cue cue) {
    const float tau=6.28318530718f;
    for(unsigned i=0;i<frames;i++){
        float t=i/48000.f,signal=0;
        float duration=cue==FX_NAV?.027f:cue==FX_CONFIRM?.098f:cue==FX_BACK?.065f:.09f;
        if(t<duration){
            float env=fminf(1,t/.0015f)*expf(-t/(duration*.22f));
            env*=fminf(1,(duration-t)/.007f);
            float f=cue==FX_NAV?1480:cue==FX_CONFIRM?880:cue==FX_BACK?554:196;
            /* Inharmonic mallet partials replace the old swept UI chirps. */
            signal=(sinf(tau*f*t)+.23f*sinf(tau*f*2.73f*t))*env*.105f;
            if(cue==FX_CONFIRM&&t>.034f){float u=t-.034f;
                signal+=sinf(tau*1320*u)*fminf(1,u/.002f)*expf(-u/.013f)*fminf(1,(duration-t)/.007f)*.072f;}
        }
        int16_t value=(int16_t)(signal*32767);
        for(unsigned c=0;c<channels;c++)samples[i*channels+c]=value;
    }
}
static AudioOutBuffer fx_audio_buffers[FX_AUDIO_BUFFERS];
static int16_t fx_cues[FX_CUES][FX_SFX_FRAMES];
static unsigned char *fx_music_data;
static unsigned fx_music_frames,fx_music_cursor,fx_cue_cursor=FX_SFX_FRAMES;
static int fx_sfx_ready,fx_audio_created,fx_audio_stop,fx_music_enabled,fx_pending_cue=-1,fx_active_cue;
static float fx_music_gain;
static pthread_t fx_audio_thread;
static void fx_audio_mix(int16_t *out,unsigned frames) {
    int cue=__atomic_exchange_n(&fx_pending_cue,-1,__ATOMIC_ACQ_REL);
    if(cue>=0&&cue<FX_CUES){fx_active_cue=cue;fx_cue_cursor=0;}
    float target=__atomic_load_n(&fx_music_enabled,__ATOMIC_ACQUIRE)?1.f:0.f;
    for(unsigned i=0;i<frames;i++){
        fx_music_gain+=(target-fx_music_gain)*.0007f;
        int value=0;
        if(fx_music_frames){
            unsigned char *p=fx_music_data+12+2*fx_music_cursor;
            int16_t sample=(int16_t)(p[0]|p[1]<<8);
            value=(int)(sample*fx_music_gain*.65f);
            fx_music_cursor=(fx_music_cursor+1)%fx_music_frames;
        }
        if(fx_cue_cursor<FX_SFX_FRAMES)value+=fx_cues[fx_active_cue][fx_cue_cursor++];
        if(value>32767)value=32767;if(value<-32768)value=-32768;
        out[i*2]=out[i*2+1]=(int16_t)value;
    }
}
static void *fx_audio_main(void *unused) {
    (void)unused;
    while(!__atomic_load_n(&fx_audio_stop,__ATOMIC_ACQUIRE)){
        AudioOutBuffer *released;u32 count;
        if(R_FAILED(audoutGetReleasedAudioOutBuffer(&released,&count)))break;
        for(unsigned i=0;i<FX_AUDIO_BUFFERS;i++){
            bool busy=true;AudioOutBuffer *b=&fx_audio_buffers[i];
            if(R_FAILED(audoutContainsAudioOutBuffer(b,&busy)))continue;
            if(busy)continue;
            fx_audio_mix(b->buffer,FX_AUDIO_FRAMES);armDCacheFlush(b->buffer,b->data_size);
            if(R_FAILED(audoutAppendAudioOutBuffer(b)))goto done;
        }
        svcSleepThread(10000000);
    }
done:return NULL;
}
static void fx_sfx_close(void) {
    if(!fx_sfx_ready)return;
    __atomic_store_n(&fx_audio_stop,1,__ATOMIC_RELEASE);
    if(fx_audio_created){pthread_join(fx_audio_thread,NULL);fx_audio_created=0;}
    audoutStopAudioOut();audoutExit();fx_sfx_ready=0;
    for(unsigned i=0;i<FX_AUDIO_BUFFERS;i++){free(fx_audio_buffers[i].buffer);memset(&fx_audio_buffers[i],0,sizeof(AudioOutBuffer));}
    free(fx_music_data);fx_music_data=NULL;fx_music_frames=fx_music_cursor=0;
    fx_music_gain=0;fx_cue_cursor=FX_SFX_FRAMES;
    __atomic_store_n(&fx_pending_cue,-1,__ATOMIC_RELEASE);
}
static void fx_sfx_init(const char *root) {
    if(R_FAILED(audoutInitialize()))return;
    fx_sfx_ready=1;
    if(audoutGetSampleRate()!=48000||audoutGetChannelCount()!=2){fx_sfx_close();return;}
    char path[768];struct stat st;snprintf(path,sizeof(path),"%s/launcher/background-music.bin",root);
    if(!stat(path,&st)&&st.st_size>=12&&st.st_size<=12+48000*30*2){
        fx_music_data=malloc((size_t)st.st_size);
        if(fx_music_data&&fx_read(path,fx_music_data,(size_t)st.st_size)==(size_t)st.st_size&&
           !memcmp(fx_music_data,"FXM1",4)&&fx_u32(fx_music_data+4)==48000&&
           fx_u32(fx_music_data+8)>0&&fx_u32(fx_music_data+8)==(st.st_size-12)/2&&!(st.st_size%2))
            fx_music_frames=fx_u32(fx_music_data+8);
        else{free(fx_music_data);fx_music_data=NULL;}
    }
    for(unsigned i=0;i<FX_CUES;i++)fx_sfx_pcm(fx_cues[i],FX_SFX_FRAMES,1,(enum fx_cue)i);
    for(unsigned i=0;i<FX_AUDIO_BUFFERS;i++){
        AudioOutBuffer *b=&fx_audio_buffers[i];b->buffer=memalign(4096,FX_AUDIO_BYTES);
        if(!b->buffer){fx_sfx_close();return;}
        b->buffer_size=FX_AUDIO_BYTES;b->data_size=FX_AUDIO_FRAMES*4;memset(b->buffer,0,FX_AUDIO_BYTES);
    }
    if(R_FAILED(audoutStartAudioOut())){fx_sfx_close();return;}
    pthread_attr_t attr;if(pthread_attr_init(&attr)){fx_sfx_close();return;}
    int rc=pthread_attr_setstacksize(&attr,64*1024);
    __atomic_store_n(&fx_audio_stop,0,__ATOMIC_RELEASE);
    if(!rc)rc=pthread_create(&fx_audio_thread,&attr,fx_audio_main,NULL);
    pthread_attr_destroy(&attr);
    if(rc){fx_sfx_close();return;}fx_audio_created=1;
}
static void fx_music_set(int enabled){__atomic_store_n(&fx_music_enabled,enabled!=0,__ATOMIC_RELEASE);}
static void fx_sfx_play(enum fx_cue cue,int enabled) {
    if(enabled&&fx_sfx_ready&&cue>=0&&cue<FX_CUES)__atomic_store_n(&fx_pending_cue,(int)cue,__ATOMIC_RELEASE);
}
