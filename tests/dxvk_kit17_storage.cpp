// Execute actual image/buffer storage assignment and upstream Rc/small_vector.
// Vulkan resource objects are modeled; this does not draw or execute a GPU.
#include <cassert>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vulkan/vulkan_core.h>
#include "util/util_likely.h"
#include "util/rc/util_rc_ptr.h"
#include "util/util_small_vector.h"
namespace dxvk {
using DxvkError=std::runtime_error;
enum class DxvkResourceResidency { Resident, Evicted };
struct Info { uint64_t handle=0; };
struct DxvkResourceAllocation {
  unsigned refs=0; uint64_t handle=0;
  static inline int live=0;
  DxvkResourceAllocation(uint64_t n):handle(n){++live;}
  ~DxvkResourceAllocation(){--live;}
  unsigned incRef(){return ++refs;} unsigned decRef(){return --refs;}
  Info getImageInfo(){return {handle};} Info getBufferInfo(){return {handle};}
  VkMemoryPropertyFlags getMemoryProperties(){return VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT;}
};
struct DxvkImageUsageInfo {
  VkImageCreateFlags flags=0; VkImageUsageFlags usage=0;
  VkPipelineStageFlags stages=0; VkAccessFlags access=0;
  VkColorSpaceKHR colorSpace=VK_COLOR_SPACE_MAX_ENUM_KHR;
  uint32_t viewFormatCount=0; const VkFormat* viewFormats=nullptr;
  VkImageLayout layout=VK_IMAGE_LAYOUT_UNDEFINED; bool stableGpuAddress=false;
};
struct DxvkImage {
  Rc<DxvkResourceAllocation> m_storage;
  Info m_imageInfo;
  struct : DxvkImageUsageInfo { const char* debugName=nullptr; } m_info;
  small_vector<VkFormat,4> m_viewFormats;
  bool m_unifiedLayoutEnabled=false,m_unifiedLayoutAvailable=false,m_stableAddress=false;
  uint32_t m_version=0,m_properties=VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT;
  int debug=0;DxvkResourceResidency residency=DxvkResourceResidency::Evicted;
  void updateDebugName(){++debug;}
  void updateResidencyStatus(DxvkResourceResidency r){residency=r;}
  bool isViewCompatible(VkFormat v){for(auto x:m_viewFormats)if(x==v)return true;return false;}
  Rc<DxvkResourceAllocation> assignStorageWithUsage(Rc<DxvkResourceAllocation>&&,const DxvkImageUsageInfo&);
};
/* ACTUAL_IMAGE */
struct DxvkBuffer {
  Rc<DxvkResourceAllocation> m_storage; Info m_bufferInfo;
  struct { const char* debugName=nullptr; } m_info;
  uint32_t m_properties=VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,m_version=0;
  int debug=0;DxvkResourceResidency residency=DxvkResourceResidency::Evicted;
  void updateDebugName(){++debug;}
  void updateResidencyStatus(DxvkResourceResidency r){residency=r;}
  /* ACTUAL_BUFFER */
};
}
using namespace dxvk;
int main(int argc,char** argv) {
  { DxvkImage image; DxvkBuffer buffer;
    if(argc>1) {
      // Baseline UBSan must identify its real null member access here.
      if(std::strcmp(argv[1],"image")==0)image.assignStorageWithUsage(nullptr,{});
      else buffer.assignStorage(nullptr);
      return 3;
    }
    for(unsigned i=0;i<100;i++) {
      auto old=image.assignStorageWithUsage(new DxvkResourceAllocation(i+1),{});
      assert(image.m_imageInfo.handle==i+1 && image.m_version==i+1);
      assert(image.residency==DxvkResourceResidency::Resident);
      auto previous=buffer.assignStorage(new DxvkResourceAllocation(i+1001));
      assert(buffer.m_bufferInfo.handle==i+1001 && buffer.m_version==i+1);
      assert(buffer.residency==DxvkResourceResidency::Resident);
    }
    // Same-storage update still supports property/format changes.
    auto version=image.m_version;
    VkFormat formats[2]={VK_FORMAT_R8_UNORM,VK_FORMAT_R8G8_UNORM};
    DxvkImageUsageInfo usage;usage.viewFormatCount=2;usage.viewFormats=formats;
    usage.access=VK_ACCESS_SHADER_READ_BIT;usage.stableGpuAddress=true;
    auto old=image.assignStorageWithUsage(Rc<DxvkResourceAllocation>(image.m_storage),usage);
    assert(old==image.m_storage && image.m_version==version+1);
    assert(image.m_stableAddress && image.m_viewFormats.size()==2);
#ifndef BASELINE
    for(unsigned n=0;n<100;n++) {
      auto storage=image.m_storage; auto info=image.m_imageInfo.handle;
      auto v=image.m_version; auto refs=storage->refs;
      try {image.assignStorageWithUsage(nullptr,usage);assert(false);}catch(const DxvkError&){}
      assert(storage==image.m_storage && image.m_imageInfo.handle==info);
      assert(image.m_version==v && storage->refs==refs && image.m_viewFormats.size()==2);
      auto b=buffer.m_storage;auto bv=buffer.m_version;
      try {buffer.assignStorage(nullptr);assert(false);}catch(const DxvkError&){}
      assert(b==buffer.m_storage && buffer.m_version==bv);
    }
    // First construction has no old allocation; it must also throw safely.
    DxvkImage empty;DxvkBuffer emptyBuffer;
    try {empty.assignStorageWithUsage(nullptr,{});assert(false);}catch(const DxvkError&){}
    try {emptyBuffer.assignStorage(nullptr);assert(false);}catch(const DxvkError&){}
    assert(!empty.m_storage && !emptyBuffer.m_storage);
#endif
  }
  assert(DxvkResourceAllocation::live==0);
  std::cout<<"PASS storage: successful replacement and same-storage property update; all references released\n";
}
