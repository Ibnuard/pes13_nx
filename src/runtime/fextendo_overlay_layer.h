/* LGPL-2.1-or-later. Explicit VI overlay ownership. Do not change the global
 * __nx_vi_layer_id: it belongs to the application's default game surface.
 * Protocol: libnx vi.c (OpenLayer 2020), VI manager AddToLayerStack 6000. */
#include <assert.h>
/* libnx IPC macros use the C11 spelling even in this runtime's GNU99 build. */
#ifndef static_assert
#define static_assert _Static_assert
#define FX_OVERLAY_UNDEF_STATIC_ASSERT
#endif
static int fx_overlay_binder(const unsigned char *raw,size_t capacity,uint64_t size,uint32_t *binder) {
    uint32_t length,offset;
    if(size<16||size>capacity)return 0;
    memcpy(&length,raw,4);memcpy(&offset,raw+4,4);
    if(offset<16||offset>size||length<12||length>size-offset)return 0;
    memcpy(binder,raw+offset+8,4);return 1;
}
static void fx_overlay_layer_close(ViLayer *layer) {
    ViLayer managed={.layer_id=layer->layer_id};
    if(layer->initialized)viCloseLayer(layer);
    if(managed.layer_id)viDestroyManagedLayer(&managed);
    memset(layer,0,sizeof(*layer));
}
static Result fx_overlay_layer_create(const ViDisplay *display,ViLayer *layer) {
    union { uint64_t alignment; unsigned char raw[0x100]; } parcel={0};
    uint64_t size=0;Result rc;
    memset(layer,0,sizeof(*layer));
    if(!serviceIsActive(viGetSession_IManagerDisplayService()))
        return MAKERESULT(Module_Libnx,LibnxError_NotInitialized);
    rc=viCreateManagedLayer(display,(ViLayerFlags)0,0,&layer->layer_id);
    if(R_FAILED(rc))return rc;
    const struct { ViDisplayName name; uint64_t id,aruid; } in={display->display_name,layer->layer_id,0};
    rc=serviceDispatchInOut(viGetSession_IApplicationDisplayService(),2020,in,size,
        .in_send_pid=true,
        .buffer_attrs={SfBufferAttr_Out|SfBufferAttr_HipcMapAlias},
        .buffers={{parcel.raw,sizeof(parcel.raw)}});
    if(R_SUCCEEDED(rc)){
        layer->initialized=true;
        if(!fx_overlay_binder(parcel.raw,sizeof(parcel.raw),size,&layer->igbp_binder_obj_id))
            rc=MAKERESULT(Module_Libnx,LibnxError_BadInput);
    }
    if(R_FAILED(rc))fx_overlay_layer_close(layer);
    return rc;
}
static Result fx_overlay_stack(ViLayer *layer,uint32_t stack) {
    const struct { uint32_t stack,padding; uint64_t id; } in={stack,0,layer->layer_id};
    return serviceDispatchIn(viGetSession_IManagerDisplayService(),6000,in);
}
#ifdef FX_OVERLAY_UNDEF_STATIC_ASSERT
#undef static_assert
#undef FX_OVERLAY_UNDEF_STATIC_ASSERT
#endif
