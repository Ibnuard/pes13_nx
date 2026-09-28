/* LGPL-2.1-or-later. Original, quiet console cues. PCM buffers and audout are
 * owned only by the launcher; close before Wine starts its audio device. */
enum fx_cue { FX_NAV,FX_CONFIRM,FX_BACK,FX_ERROR,FX_CUES };
#define FX_SFX_FRAMES 4800
#define FX_SFX_BYTES 20480
static void fx_sfx_pcm(int16_t *samples,unsigned frames,unsigned channels,enum fx_cue cue) {
    const float tau=6.28318530718f;
    float duration=cue==FX_NAV?.038f:cue==FX_CONFIRM?.095f:cue==FX_BACK?.065f:.085f;
    for(unsigned i=0;i<frames;i++){
        float t=i/48000.f,a=t/duration,signal=0;
        if(a<1){
            float attack=fminf(1,t/.004f),envelope=attack*(1-a)*(1-a);
            float f=cue==FX_NAV?620:cue==FX_CONFIRM?1046:cue==FX_BACK?740:260;
            float sweep=cue==FX_CONFIRM?170:cue==FX_BACK?-180:-110;
            signal=(sinf(tau*(f*t+sweep*t*t/duration*.5f))+.18f*sinf(tau*f*2*t))*envelope*.13f;
        }
        int16_t value=(int16_t)(signal*32767);
        for(unsigned c=0;c<channels;c++)samples[i*channels+c]=value;
    }
}
static AudioOutBuffer fx_sfx_buffers[FX_CUES];
static int fx_sfx_ready;
static void fx_sfx_close(void) {
    if(!fx_sfx_ready)return;
    audoutStopAudioOut();
    /* Closing the session releases service ownership before backing is freed. */
    audoutExit();fx_sfx_ready=0;
    for(unsigned i=0;i<FX_CUES;i++){free(fx_sfx_buffers[i].buffer);memset(&fx_sfx_buffers[i],0,sizeof(AudioOutBuffer));}
}
static void fx_sfx_init(void) {
    if(R_FAILED(audoutInitialize()))return;
    fx_sfx_ready=1;
    unsigned channels=audoutGetChannelCount();
    if(audoutGetSampleRate()!=48000||channels!=2){fx_sfx_close();return;}
    for(unsigned i=0;i<FX_CUES;i++){
        AudioOutBuffer *b=&fx_sfx_buffers[i];
        b->buffer=memalign(4096,FX_SFX_BYTES);
        if(!b->buffer){fx_sfx_close();return;}
        b->buffer_size=FX_SFX_BYTES;b->data_size=FX_SFX_FRAMES*channels*sizeof(int16_t);
        memset(b->buffer,0,FX_SFX_BYTES);fx_sfx_pcm(b->buffer,FX_SFX_FRAMES,channels,(enum fx_cue)i);
        armDCacheFlush(b->buffer,b->data_size);
    }
    if(R_FAILED(audoutStartAudioOut()))fx_sfx_close();
}
static void fx_sfx_play(enum fx_cue cue,int enabled) {
    if(!enabled||!fx_sfx_ready)return;
    AudioOutBuffer *released;u32 count;bool contains=true;
    audoutGetReleasedAudioOutBuffer(&released,&count);
    if(R_SUCCEEDED(audoutContainsAudioOutBuffer(&fx_sfx_buffers[cue],&contains))&&!contains)
        audoutAppendAudioOutBuffer(&fx_sfx_buffers[cue]);
}
