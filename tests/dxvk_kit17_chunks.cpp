// Real allocateChunkInPool and real page/pool allocator; only Vulkan allocation
// and mapping are modeled. Includes deterministic fragmentation and live reuse.
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <set>
#include <vector>
#include "dxvk_allocator.h"
namespace dxvk {
using VkDeviceSize=uint64_t;
using VkMemoryPropertyFlags=uint32_t;
using high_resolution_clock=std::chrono::steady_clock;
struct DxvkDeviceMemory { uint64_t memory=0, size=0; };
struct DxvkMemoryChunk {
  DxvkDeviceMemory memory;
  high_resolution_clock::time_point unusedTime;
  bool canMove=false;
};
/* ACTUAL_POOL */
struct DxvkMemoryType { struct { uint64_t memoryAllocated=0; } stats; };
class DxvkMemoryAllocator {
public:
  uint64_t largest=0, nextHandle=0;
  unsigned maps=0;
  std::vector<uint64_t> attempts;
  DxvkDeviceMemory allocateDeviceMemory(DxvkMemoryType& t,uint64_t size,const void* next) {
    assert(!next && size && size%65536==0); attempts.push_back(size);
    if(size>largest) return {};
    t.stats.memoryAllocated+=size;
    return {++nextHandle,size};
  }
  void mapDeviceMemory(DxvkDeviceMemory& c,VkMemoryPropertyFlags flags) {
    assert(c.memory && flags==3); ++maps;
  }
  bool allocateChunkInPool(DxvkMemoryType&,DxvkMemoryPool&,VkMemoryPropertyFlags,VkDeviceSize,VkDeviceSize);
};
/* ACTUAL_CHUNK */
}
using namespace dxvk;
constexpr uint64_t P=65536, M=1024*1024;
void use(DxvkMemoryPool& p,uint64_t size) {
  auto addr=p.alloc(size,P); assert(addr>=0);
  uint64_t n=uint64_t(addr)>>DxvkPageAllocator::ChunkAddressBits;
  assert((uint64_t(addr)&DxvkPageAllocator::ChunkAddressMask)+size<=p.chunks[n].memory.size);
  assert(p.free(addr,size)); assert(!p.pageAllocator.pagesUsed(n));
  p.pageAllocator.removeChunk(n);
}
int main() {
  { DxvkMemoryAllocator a; DxvkMemoryType t; DxvkMemoryPool p;
    a.largest=26*P;
    bool ok=a.allocateChunkInPool(t,p,3,1661632,128*M);
#ifdef BASELINE
    assert(!ok && !a.maps && p.chunks.empty() && a.attempts.back()==4*M);
#else
    assert(ok && a.maps==1 && p.chunks[0].memory.size==26*P);
    assert(p.nextChunkSize==2*M);use(p,1661632);
#endif
  }
  { DxvkMemoryAllocator a; DxvkMemoryType t; DxvkMemoryPool p;
    a.largest=128*M;
    assert(a.allocateChunkInPool(t,p,3,P,128*M));
#ifdef BASELINE
    assert(p.chunks[0].memory.size==128*M);
#else
    assert(p.chunks[0].memory.size==8*M);
#endif
    use(p,P);
  }
#ifndef BASELINE
  unsigned cases=0;
  // Sweep every page count in 0..12 MiB, both aligned and unaligned requests.
  for(uint64_t pages=1;pages<=192;pages++) for(uint64_t slack:{0ull,137ull}) {
    uint64_t need=pages*P-slack, exact=pages*P;
    DxvkMemoryAllocator a;DxvkMemoryType t;DxvkMemoryPool p;
    a.largest=exact;
    assert(a.allocateChunkInPool(t,p,3,need,128*M));
    assert(a.attempts.back()==exact && a.maps==1 && t.stats.memoryAllocated==exact);
    assert(p.pageAllocator.pageCount(0)==pages);
    assert(p.nextChunkSize && !(p.nextChunkSize&(p.nextChunkSize-1)) && p.nextChunkSize<=8*M);
    assert(a.attempts.size()<=9);
    for(size_t i=0;i<a.attempts.size();i++) {
      assert(a.attempts[i]>=need);
      if(i) assert(a.attempts[i]<a.attempts[i-1]);
    }
    use(p,need);++cases;
    DxvkMemoryAllocator fail;DxvkMemoryType ft;DxvkMemoryPool fp;
    fail.largest=exact-1;
    assert(!fail.allocateChunkInPool(ft,fp,3,need,128*M));
    assert(!fail.maps && fp.chunks.empty() && !ft.stats.memoryAllocated);
    assert(fail.attempts.back()==exact && fail.attempts.size()<=9);++cases;
  }
  // Concurrent live chunks exercise real offset, free/reuse and page metadata.
  { DxvkMemoryAllocator a;DxvkMemoryType t;DxvkMemoryPool p;
    a.largest=26*P;std::vector<uint64_t> live;
    for(unsigned i=0;i<80;i++) {
      assert(a.allocateChunkInPool(t,p,3,1661632,128*M));
      auto addr=p.alloc(1661632,P); assert(addr>=0);
      assert(std::find(live.begin(),live.end(),addr)==live.end());live.push_back(addr);
    }
    for(auto addr:live) {
      assert(p.free(addr,1661632));
      p.pageAllocator.removeChunk(addr>>DxvkPageAllocator::ChunkAddressBits);
    }
    assert(t.stats.memoryAllocated==80*26*P);
  }
  std::cout<<"PASS Kit17: "<<cases<<" pressure/recovery cases, 80 live chunks, real page allocator, 8 MiB healthy cap\n";
#else
  std::cout<<"PASS baseline reproducer: 128 MiB healthy allocation; small request rejected with usable 26-page hole\n";
#endif
}
