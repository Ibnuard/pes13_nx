#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#define PES_LIVE_NO_REPORT
#include "../src/runtime/pes_live_settings.h"
static unsigned char blob[852];
static unsigned selected,reads,short_read,changed;
static int read_guest(uint32_t a,void *out,size_t n){
    ++reads;
    if(a!=pes_live_layouts[selected].base||short_read)return 0;
    assert(n==852||n==12);memcpy(out,blob,n);
    if(changed&&n==12)((unsigned char*)out)[0]^=1;
    return 1;
}
static void put(unsigned at,uint32_t n){for(unsigned i=0;i<4;i++)blob[at+i]=n>>(8*i);}
static void init(void){
    memset(blob,0,sizeof(blob));put(0,0x46434557);put(4,2);put(8,852);
    blob[14]=0x89;blob[15]=2;put(16,1280);put(20,720);put(24,1);put(28,1);
    unsigned crc=pes_live_crc(blob);blob[12]=crc;blob[13]=crc>>8;
}
int main(void){
    struct pes_live_settings out,before;
    memset(&out,0x55,sizeof(out));before=out;
    assert(pes_live_settings_read(read_guest,3,&out)==-1&&!reads);
    for(selected=0;selected<3;selected++){
        init();unsigned char copy[852];memcpy(copy,blob,sizeof(blob));
        assert(pes_live_settings_read(read_guest,selected,&out)==1);
        assert(out.crc_valid&&out.flags==0x289&&out.width==1280&&out.height==720&&out.quality==1);
        assert(!memcmp(copy,blob,sizeof(blob)));
        /* A live ON bit is reported even though its stale CRC no longer
         * matches the file. Observers must never force it off themselves. */
        blob[14]|=2;assert(pes_live_settings_read(read_guest,selected,&out)==1);
        assert(!out.crc_valid&&out.flags==0x28b&&blob[14]==0x8b);
        before=out;short_read=1;
        assert(!pes_live_settings_read(read_guest,selected,&out)&&!memcmp(&before,&out,sizeof(out)));
        short_read=0;changed=1;
        assert(pes_live_settings_read(read_guest,selected,&out)==-3&&!memcmp(&before,&out,sizeof(out)));
        changed=0;blob[0]=0;
        assert(pes_live_settings_read(read_guest,selected,&out)==-1);
        init();put(16,0);assert(pes_live_settings_read(read_guest,selected,&out)==-2);
    }
    puts("PASS: WECF reads for 1.00/1.03/1.04; live OFF/ON and stale CRC distinguished; bad headers, fields, short/changed reads rejected; no guest writes.");
}
