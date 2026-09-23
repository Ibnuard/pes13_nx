#ifndef PES13_PERF25_POLICY_H
#define PES13_PERF25_POLICY_H
#include <stdint.h>
#include <string.h>
/* Full 35-byte decoded guest routine captured identically in PERF21–24. */
static const unsigned char pes25_copy_guest[] = {
    0x53,0x8b,0xd9,0x56,0x8b,0x74,0x24,0x0c,0x57,0x8d,0x43,0x28,
    0x8b,0xf8,0xb9,0xee,0x00,0x00,0x00,0xf3,0xa5,0x8b,0x8b,0x84,
    0x07,0x00,0x00,0x8b,0x11,0x50,0x8b,0x42,0x10,0xff,0xd0
};
static inline int pes25_copy_match(uintptr_t ip, const void *code, size_t size,
                                   int enabled, int identity, unsigned post_present_env)
{
    return enabled && identity==1 && post_present_env && ip==0x93df43 &&
        size==sizeof(pes25_copy_guest) && !memcmp(code,pes25_copy_guest,size);
}
#endif
