"""Measure the full submit path and bound optional nonblocking error scans."""
import re
from perf17_patches import once
import perf30_mesa

def span(text,name):
    m=re.search(r'(?m)^'+re.escape(name)+r'\([^;]*?\)\n\{',text);assert m,name
    a=m.start();start=m.end()-1;i=start+1;depth=1
    while depth:
        depth+=(text[i]=='{')-(text[i]=='}');i+=1
    return a,i,start

def body_timing(text,name,stage,obj,void=False):
    a,b,start=span(text,name);body=text[start+1:b-1]
    if void:
        assert not re.search(r'\breturn\b',body)
        body+='\n   wine_nx_perf31_leave(pes31_scope);\n'
    else:
        body,n=re.subn(r'\breturn ([^;]+);',lambda m:
            'do { __auto_type pes31_result = ('+m[1]+'); wine_nx_perf31_leave(pes31_scope); return pes31_result; } while (0);',body)
        assert n,name
    body='\n   struct pes31_token pes31_scope = wine_nx_perf31_enter('+stage+', (uintptr_t)('+obj+'));'+body
    return text[:start+1]+body+text[b-1:]

def patch(name,text,project):
    if name in ('nvk_queue.c','nvkmd_switch_dev.c','nouveau_horizon_channel.c','vk_queue.c'):
        text=perf30_mesa.patch(name,text,project).replace('perf30','perf31').replace('PES30','PES31')
    else:text='#include "'+str(project/'src/runtime/pes13_perf31.h')+'"\n'+text
    if name=='vk_queue.c':
        for function,stage,obj,void in (
            ('vk_common_QueueSubmit2','PES31_SUBMIT_API','_queue',False),
            ('vk_queue_submit_create','PES31_SUBMIT_CREATE','queue',False),
            ('vk_queue_submit_destroy','PES31_SUBMIT_DESTROY','queue',True)):
            text=body_timing(text,function,stage,obj,void)
        text=once(text,'''      result = vk_sync_signal_unwrap(queue->base.device,
                                     &submit->signals[i], &signal_point);''',
            '''      PES31_TIME(PES31_SIGNAL_UNWRAP, queue, result = vk_sync_signal_unwrap(queue->base.device,
                                     &submit->signals[i], &signal_point));''')
        text=once(text,'''         vk_sync_timeline_point_install(queue->base.device,
                                        submit->_signal_points[i]);''',
            '''         PES31_TIME(PES31_TIMELINE_INSTALL, queue, vk_sync_timeline_point_install(queue->base.device,
                                        submit->_signal_points[i]));''')
    elif name=='vk_sync_timeline.c':
        text=body_timing(text,'vk_sync_timeline_gc_locked','PES31_TIMELINE_GC','state')
    elif name=='nouveau_horizon_channel.c':
        text='#include "'+str(project/'src/runtime/pes13_perf31_poll.h')+'"\n'+text
        a,b,_=span(text,'nouveau_horizon_fence_wait_impl');body=text[a:b]
        anchor='''      status = nouveau_horizon_device_scan_channel_errors(
         device, fence->id, locked_channel);'''
        new='''      /* Completion was queried above. A zero-time miss is ordinary queue
       * progress, not itself an error. Bound optional notifier IPC to the
       * existing 50ms error-poll cadence per caller/device; blocking waits
       * and latched errors retain their original behavior. */
      if (nouveau_horizon_device_is_lost(device))
         return NOUVEAU_HORIZON_ERROR_DEVICE_LOST;
      static _Thread_local struct pes31_poll_gate error_poll;
      const int deferred = pes31_defer_error_scan(&error_poll, (uintptr_t)device,
         fence->id, timeout_ns, os_time_get_nano(), wine_nx_perf31_poll_mode());
      wine_nx_perf31_poll_count(deferred);
      if (deferred)
         return NOUVEAU_HORIZON_ERROR_TIMEOUT;
      PES31_TIME(PES31_ERROR_SCAN, device, status = nouveau_horizon_device_scan_channel_errors(
         device, fence->id, locked_channel));'''
        body=once(body,anchor,new)
        body=once(body,'''      if (status != NOUVEAU_HORIZON_SUCCESS)
         return status;''', '''      if (status != NOUVEAU_HORIZON_SUCCESS) {
         error_poll.valid = 0; /* Never defer the retry of a failed error scan. */
         return status;
      }''')
        text=text[:a]+body+text[b:]
        text=body_timing(text,'nouveau_horizon_fence_wait_impl',
            'timeout_ns == 0 ? PES31_FENCE_QUERY : PES31_FENCE_WAIT','device')
    return text
