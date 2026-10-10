/* LGPL-2.1-or-later. Debug-only, read-only observation of the game's loaded
 * WECF settings. Kitserver 13 names SCREEN_WIDTH at +0x10 for 1.03/1.04.
 * A candidate is never trusted without checking the in-memory WECF header.
 * No guest patch, frame cap, time scaling, or raw pointer dereference. */
#ifndef PES_LIVE_SETTINGS_H
#define PES_LIVE_SETTINGS_H
#include <stdint.h>
#include <string.h>

struct pes_live_settings {
    unsigned layout, crc_valid;
    uint32_t address, width, height, aspect, quality;
    uint16_t flags;
};
static const struct {uint32_t base;const char *name;} pes_live_layouts[] = {
    {0x019bc818,"1.00"}, {0x019db710,"1.03"}, {0x019e7a68,"1.04"}
};
static uint32_t pes_live_u32(const unsigned char *p)
{
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static unsigned pes_live_crc(const unsigned char *p)
{
    unsigned crc=0;
    for(unsigned i=0;i<852;i++){
        crc^=(unsigned)((i==12||i==13)?0:p[i])<<8;
        for(unsigned j=0;j<8;j++)crc=((crc<<1)^((crc&0x8000)?0x1021:0))&65535;
    }
    return (~crc)&65535;
}
/* Non-CRC-valid snapshots can reflect game writes or a concurrent read. They
 * remain explicitly labelled and must not be used to enforce settings. */
static int pes_live_settings_read(int (*read)(uint32_t,void *,size_t),unsigned index,
                                  struct pes_live_settings *out)
{
    unsigned char data[852],header[12];
    struct pes_live_settings s={0};
    if(index>=sizeof(pes_live_layouts)/sizeof(pes_live_layouts[0]))return -1;
    s.address=pes_live_layouts[index].base;s.layout=index;
    if(!read(s.address,data,sizeof(data)))return 0;
    if(pes_live_u32(data)!=0x46434557||pes_live_u32(data+4)!=2||pes_live_u32(data+8)!=852)return -1;
    s.width=pes_live_u32(data+16);s.height=pes_live_u32(data+20);
    s.aspect=pes_live_u32(data+24);s.quality=pes_live_u32(data+28);
    if(s.width<320||s.width>16384||s.height<200||s.height>16384||s.aspect>1||s.quality>2)return -2;
    if(!read(s.address,header,sizeof(header))||memcmp(data,header,sizeof(header)))return -3;
    s.flags=(unsigned)data[14]|(unsigned)data[15]<<8;
    s.crc_valid=((unsigned)data[12]|(unsigned)data[13]<<8)==pes_live_crc(data);
    *out=s;return 1;
}

#ifndef PES_LIVE_NO_REPORT
/* QPF call sites for 1.03/1.04 are documented by Kitserver's speeder module.
 * The adjacent QPC site is only a candidate until its opcode is checked.
 * Expose hook targets, without calling them or changing their return values. */
static void pes_live_clock_site(unsigned layout)
{
    static const uint32_t sites[3]={0x01119a79,0x01138199,0x0113b7f9};
    for(unsigned i=0;i<2;i++){
        unsigned char code[6],pointer[4];uint32_t site=sites[layout]+(i?29:0),target=0;
        const char *kind="unknown";
        if(!wine_nx_fex_timing_read(site,code,sizeof(code))){
            fx_launch_debug_log("[LW3-CLOCKSITE] layout=%s site=%08x readable=0",pes_live_layouts[layout].name,site);
            continue;
        }
        if(code[0]==0xff&&code[1]==0x15){
            kind="indirect";
            if(wine_nx_fex_timing_read(pes_live_u32(code+2),pointer,4))target=pes_live_u32(pointer);
        }else if(code[0]==0xe8){
            kind="direct";target=site+5+pes_live_u32(code+1);
        }
        fx_launch_debug_log("[LW3-CLOCKSITE] layout=%s role=%s site=%08x opcode=%02x%02x%02x%02x%02x%02x kind=%s target=%08x; observational, no clock-rate inference",
            pes_live_layouts[layout].name,i?"QPC-candidate":"QPF",site,
            code[0],code[1],code[2],code[3],code[4],code[5],kind,target);
    }
}
static void pes_live_settings_report(void)
{
    static unsigned reports[3];
    struct pes_live_settings s;
    int result[3];
    unsigned found=0;
    for(unsigned i=0;i<3;i++){
        result[i]=pes_live_settings_read(wine_nx_fex_timing_read,i,&s);
        if(result[i]!=1)continue;
        found++;
        fx_launch_debug_log("[LW3-LIVESET] layout=%s address=%08x flags=%04x vsync=%u frame_skip=%u xinput_ui=%u xinput_runtime=%u crc_valid=%u width=%u height=%u quality=%u; read-only",
            pes_live_layouts[i].name,s.address,s.flags,s.flags&1,(s.flags>>1)&1,
            (s.flags>>3)&1,(s.flags>>9)&1,s.crc_valid,s.width,s.height,s.quality);
        if(reports[i]++%6==0)pes_live_clock_site(i);
    }
    /* Repeat even an unsupported result: a single dropped startup line must
     * not leave a whole run with no evidence, as happened with the old probe. */
    if(!found)fx_launch_debug_log("[LW3-LIVESET] unavailable status_v100=%d status_v103=%d status_v104=%d; 0=unmapped -1=header -2=fields -3=changed; no setting inferred",
                                 result[0],result[1],result[2]);
}
#endif
#endif
