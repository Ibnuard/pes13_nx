/* LGPL-2.1-or-later. Link wrappers observe failures only; preserve errno and
 * allocation semantics. Guest heap/VA failures may need separate evidence. */
extern void *__real_malloc(size_t);
extern void *__real_calloc(size_t,size_t);
extern void *__real_realloc(void *,size_t);
extern void *__real_memalign(size_t,size_t);
extern void *__real_aligned_alloc(size_t,size_t);
static void fx_tr_alloc_failed(unsigned kind,uint64_t size,uint64_t alignment,uintptr_t caller){
    int saved=errno;wine_nx_transition_event(3,kind,size,alignment);
    wine_nx_transition_alloc_site(kind,size,alignment,caller,(unsigned)saved);errno=saved;
}
void *__wrap_malloc(size_t n){void *p=__real_malloc(n);if(!p&&n)fx_tr_alloc_failed(1,n,0,(uintptr_t)__builtin_return_address(0));return p;}
void *__wrap_calloc(size_t n,size_t s){void *p=__real_calloc(n,s);if(!p&&n&&s)fx_tr_alloc_failed(2,n>SIZE_MAX/s?UINT64_MAX:n*s,0,(uintptr_t)__builtin_return_address(0));return p;}
void *__wrap_realloc(void *old,size_t n){void *p=__real_realloc(old,n);if(!p&&n)fx_tr_alloc_failed(3,n,0,(uintptr_t)__builtin_return_address(0));return p;}
void *__wrap_memalign(size_t a,size_t n){void *p=__real_memalign(a,n);if(!p&&n)fx_tr_alloc_failed(4,n,a,(uintptr_t)__builtin_return_address(0));return p;}
void *__wrap_aligned_alloc(size_t a,size_t n){void *p=__real_aligned_alloc(a,n);if(!p&&n)fx_tr_alloc_failed(5,n,a,(uintptr_t)__builtin_return_address(0));return p;}
