/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Role-based graphics offload adapted from Autorun/Wine-NX contributors,
 * commit c2268252a28abb5977fec8ea385b43f0e9519a5f, thread_profile.c/h.
 * FEXTendo trial: dxvk-cs only, separate slot metadata (existing registry ABI),
 * capability/readback diagnostics and conservative rollback/failure tracking.
 * Included after the registry declarations. All slot access holds its mutex.
 */
struct fex_dxvk_slot {
    char name[64];
    int active;
    s32 saved_core, saved_priority;
    u64 saved_mask;
};
static struct fex_dxvk_slot fex_dxvk_slots[NX_PROF_MAX_THREADS];
static int fex_dxvk_enabled;

void wine_nx_fex_dxvk_configure(int requested, int automatic_core3)
{
    u64 cores=0,priorities=0;
    Result a=svcGetInfo(&cores,InfoType_CoreMask,CUR_PROCESS_HANDLE,0);
    Result b=svcGetInfo(&priorities,InfoType_PriorityMask,CUR_PROCESS_HANDLE,0);
    fex_dxvk_enabled=requested && !automatic_core3 && R_SUCCEEDED(a) && R_SUCCEEDED(b) &&
        (cores&8) && (priorities&(UINT64_C(1)<<63));
    char line[320];
    snprintf(line,sizeof(line),"[FEX3-DXVKCORE] v1 requested=%d enabled=%d cores=%llx priorities=%llx core_rc=%x priority_rc=%x auto_core3=%d; exact dxvk-cs only, core=3 priority=63",
        requested,fex_dxvk_enabled,(unsigned long long)cores,(unsigned long long)priorities,(unsigned)a,(unsigned)b,automatic_core3);
    wine_nx_runtime_trace(line);
}

/* Recover original placement before priority: never run the old, potentially
 * higher priority on reserved core 3. Failure keeps active set, excluding the
 * slot from ordinary balancing until a later rename/affinity request retries. */
static Result fex_dxvk_restore_locked(unsigned i, s32 core, u64 mask)
{
    struct nx_prof_thread *thread=&registry[i];
    struct fex_dxvk_slot *s=&fex_dxvk_slots[i];
    if(!s->active)return 0;
    Result rc=svcSetThreadCoreMask(thread->handle,core,(u32)mask);
    if(R_FAILED(rc))return rc;
    rc=svcSetThreadPriority(thread->handle,s->saved_priority);
    if(R_FAILED(rc))return rc;
    s->active=0;
    return 0;
}

void wine_nx_fex_dxvk_name(unsigned tid,const char *name)
{
    char line[384]="";
    pthread_mutex_lock(&registry_mutex);
    for(unsigned i=0;i<NX_PROF_MAX_THREADS;i++){
        struct nx_prof_thread *thread=&registry[i];
        struct fex_dxvk_slot *s=&fex_dxvk_slots[i];
        if(!thread->handle||thread->kind!='w'||thread->tid!=tid)continue;
        Result rc=0,rollback=0;int tried=0;
        snprintf(s->name,sizeof(s->name),"%s",name);
        if(strcmp(name,"dxvk-cs")){
            if(s->active)rc=fex_dxvk_restore_locked(i,s->saved_core,s->saved_mask);
        }else if(fex_dxvk_enabled&&!thread->fixed&&!s->active){
            tried=1;
            rc=svcGetThreadCoreMask(&s->saved_core,&s->saved_mask,thread->handle);
            if(R_SUCCEEDED(rc))rc=svcGetThreadPriority(&s->saved_priority,thread->handle);
            if(R_SUCCEEDED(rc)){
                /* Lower first; a failed priority change cannot leave a helper
                 * at an application priority on core 3. */
                rc=svcSetThreadPriority(thread->handle,63);
                if(R_SUCCEEDED(rc)){
                    s->active=1;
                    rc=svcSetThreadCoreMask(thread->handle,3,8);
                    if(R_FAILED(rc))rollback=fex_dxvk_restore_locked(i,s->saved_core,s->saved_mask);
                }
            }
        }
        s32 actual_core=-1,priority=-1;u64 actual_mask=0;
        Result cm=svcGetThreadCoreMask(&actual_core,&actual_mask,thread->handle);
        Result pr=svcGetThreadPriority(&priority,thread->handle);
        snprintf(line,sizeof(line),"[FEX3-DXVKCORE] tid=%u handle=%u name=%s fixed=%d tried=%d active=%d core=%d mask=%llx priority=%d rc=%x rollback_rc=%x read_core_rc=%x read_priority_rc=%x tick=%llu",
            tid,thread->handle,s->name,thread->fixed,tried,s->active,(int)actual_core,(unsigned long long)actual_mask,(int)priority,
            (unsigned)rc,(unsigned)rollback,(unsigned)cm,(unsigned)pr,(unsigned long long)armGetSystemTick());
        break;
    }
    pthread_mutex_unlock(&registry_mutex);
    if(line[0])wine_nx_runtime_trace(line);
}

/* Called only after Wine accepts an explicit affinity. OFF/non-helper paths
 * return unhandled, retaining the existing current-thread pinning path. */
int wine_nx_fex_dxvk_affinity(unsigned tid,u64 mask)
{
    int handled=0;char line[192]="";
    pthread_mutex_lock(&registry_mutex);
    for(unsigned i=0;i<NX_PROF_MAX_THREADS;i++){
        struct nx_prof_thread *thread=&registry[i];
        if(!thread->handle||thread->kind!='w'||thread->tid!=tid)continue;
        if(fex_dxvk_slots[i].active){
            Result rc=fex_dxvk_restore_locked(i,__builtin_ctzll(mask),mask);
            thread->fixed=1;
            /* Do not run the original pinning a second time on partial failure.
             * A subsequent explicit request can retry the saved priority. */
            handled=1;
            if(R_SUCCEEDED(rc)&&thread->teb&&horizon_follow_thread_cores)
                horizon_follow_thread_cores((void*)(uintptr_t)thread->teb,(unsigned)mask);
            snprintf(line,sizeof(line),"[FEX3-DXVKCORE] explicit tid=%u mask=%llx restore_rc=%x active=%d tick=%llu",tid,
                (unsigned long long)mask,(unsigned)rc,fex_dxvk_slots[i].active,(unsigned long long)armGetSystemTick());
        }
        break;
    }
    pthread_mutex_unlock(&registry_mutex);
    if(line[0])wine_nx_runtime_trace(line);
    return handled;
}
