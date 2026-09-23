"""Instrument copies of four native driver sources; never edit the Mesa checkout."""
from pathlib import Path
import re
from perf17_patches import once
from perf27_patches import function_span

def timed(text,call,stage,obj,count):
    pattern=r'(?m)^( +)((?:result|status) = '+re.escape(call)+r'\([\s\S]*?\);)'
    matches=list(re.finditer(pattern,text));assert len(matches)==count,(call,len(matches),count)
    return re.sub(pattern,lambda m:m[1]+f'PES30_TIME({stage}, {obj}, '+m[2][:-1]+');',text)

def patch(name,text,project):
    original=text
    if name=='nvk_queue.c':
        a,b=function_span(text,'nvk_queue_submit_exec');body=text[a:b]
        for call,stage in [('nvk_queue_state_update','PES30_QUEUE_STATE'),
                           ('nvk_upload_queue_flush','PES30_UPLOAD_FLUSH'),
                           ('nvk_queue_submit_cmd_buffers','PES30_COMMANDS'),
                           ('nvkmd_ctx_signal','PES30_SIGNAL')]:
            body=timed(body,call,stage,'queue',1)
        body=timed(body,'nvkmd_ctx_wait','PES30_QUEUE_WAIT','queue',2)
        body=once(body,'PES30_TIME(PES30_QUEUE_WAIT, queue, result = nvkmd_ctx_wait(queue->exec_ctx, &queue->vk.base, 1, &wait));',
            'PES30_TIME(PES30_UPLOAD_WAIT, queue, result = nvkmd_ctx_wait(queue->exec_ctx, &queue->vk.base, 1, &wait));')
        anchor='      uint64_t upload_time_point;'
        body=once(body,anchor,'''      wine_nx_perf30_value(PES30_SLM_WARP, queue->state.slm.bytes_per_warp);
      wine_nx_perf30_value(PES30_SLM_TPC, queue->state.slm.bytes_per_tpc);
      wine_nx_perf30_value(PES30_IMAGE_POOL, queue->state.images.alloc_count);
      wine_nx_perf30_value(PES30_SAMPLER_POOL, queue->state.samplers.alloc_count);
'''+anchor)
        text=text[:a]+body+text[b:]
    elif name=='nvkmd_switch_dev.c':
        text=once(text,'''   const enum nouveau_horizon_status status =
      nouveau_horizon_channel_submit(ctx->channel, mode, &fence);''',
            '''   enum nouveau_horizon_status status;
   PES30_TIME(PES30_CHANNEL_SUBMIT, ctx->channel,
      status = nouveau_horizon_channel_submit(ctx->channel, mode, &fence));''')
        text=timed(text,'vk_sync_wait_many','PES30_HOST_SYNC','ctx',1)
        text=once(text,'''      return vk_sync_wait_many(device, wait_count, waits,
                               0, UINT64_MAX);''',
            '''      VkResult result;
      PES30_TIME(PES30_HOST_SYNC, ctx,
         result = vk_sync_wait_many(device, wait_count, waits, 0, UINT64_MAX));
      return result;''')
    elif name=='nouveau_horizon_channel.c':
        a,b=function_span(text,'nouveau_horizon_channel_submit_locked');body=text[a:b]
        body=once(body,'      simple_mtx_lock(&device->submit_mutex);',
            '      PES30_TIME(PES30_ORDER_LOCK, device, simple_mtx_lock(&device->submit_mutex));')
        for call,stage in [('nouveau_horizon_channel_reserve_entries_locked','PES30_RESERVE'),
                           ('nouveau_horizon_channel_throttle_inflight_locked','PES30_THROTTLE'),
                           ('nouveau_horizon_channel_kickoff_locked','PES30_KICKOFF')]:
            body=timed(body,call,stage,'channel',1)
        text=text[:a]+body+text[b:]
        a,b=function_span(text,'nouveau_horizon_channel_submit');body=text[a:b]
        body=once(body,'   mtx_lock(&channel->mutex);',
            '   PES30_TIME(PES30_CHANNEL_LOCK, channel, mtx_lock(&channel->mutex));')
        text=text[:a]+body+text[b:]
    elif name=='vk_queue.c':
        a,b=function_span(text,'vk_queue_submit_final');body=text[a:b]
        body=once(body,'      simple_mtx_lock(&real_queue->lock);',
            '      PES30_TIME(PES30_QUEUE_LOCK, real_queue, simple_mtx_lock(&real_queue->lock));')
        body=once(body,'      vk_queue_lock(queue);',
            '      PES30_TIME(PES30_QUEUE_LOCK, queue, vk_queue_lock(queue));')
        body=once(body,'      result = real_queue->driver_submit(real_queue, submit);',
            '      PES30_TIME(PES30_QUEUE_DRIVER, real_queue, result = real_queue->driver_submit(real_queue, submit));')
        body=once(body,'      result = queue->driver_submit(queue, submit);',
            '      PES30_TIME(PES30_QUEUE_DRIVER, queue, result = queue->driver_submit(queue, submit));')
        body=timed(body,'vk_sync_wait_unwrap','PES30_HOST_SYNC','queue',1)
        text=text[:a]+body+text[b:]
        text=timed(text,'vk_sync_wait_many','PES30_HOST_SYNC','queue',2)
        text=timed(text,'vk_sync_wait','PES30_HOST_SYNC','queue',3)
        text=once(text,'PES30_TIME(PES30_HOST_SYNC, queue, result = vk_sync_wait(device,',
            'PES30_TIME(PES30_HOST_SYNC, device, result = vk_sync_wait(device,')
    else: raise ValueError(name)
    assert text!=original
    return '#include "'+str(project/'src/runtime/pes13_perf30.h')+'"\n'+text
