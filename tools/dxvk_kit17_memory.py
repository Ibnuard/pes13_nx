"""Pinned DXVK 3.1.1: compact real Vulkan allocations and atomic storage failure.

The chunk strategy also references F1's dxvk_compact_chunks work in this
workspace. This implementation has one bounded retry loop and no synthesized
Vulkan handles, eviction, clock, shader or graphics-quality changes.
"""
from pathlib import Path
import hashlib

COMMIT = 'b1a1c99ab52b687cf950d62c88bc2fa316b41663'
MEMORY_SHA = '0e0c0322d981e70f1f53af8c7d7b4890d9c6de7ec7e7673297efe89042676ba2'


def once(text, old, new):
    assert text.count(old) == 1, (old[:160], text.count(old))
    return text.replace(old, new)


def apply(source: Path):
    changed = {}

    def edit(name, change):
        p = source / name
        old = p.read_text()
        new = change(old)
        assert old != new, name
        p.write_text(new)
        changed[name] = {'before': hashlib.sha256(old.encode()).hexdigest(),
                         'after': hashlib.sha256(new.encode()).hexdigest()}

    def memory(s):
        assert hashlib.sha256(s.encode()).hexdigest() == MEMORY_SHA
        start = s.index('    // Try to allocate device memory. If the allocation fails, retry with',
                        s.index('  bool DxvkMemoryAllocator::allocateChunkInPool('))
        end = s.index('    // Add the newly created chunk to the pool', start)
        s = s[:start] + '''    // Horizon shares one finite heap with Wine, FEX and the game. Avoid
    // reserving 128 MiB for a small resource, but never undersize a resource.
    constexpr VkDeviceSize chunkCap = 8u << 20;
    constexpr VkDeviceSize pageSize = DxvkPageAllocator::PageSize;
    VkDeviceSize requiredPages = align(std::max(requiredSize, pageSize), pageSize);
    desiredSize = std::max(requiredPages,
      std::min(desiredSize, std::max(requiredPages, chunkCap)));
    DxvkDeviceMemory chunk = { };
    bool recovered = false;

    for (;;) {
      chunk = allocateDeviceMemory(type, desiredSize, nullptr);
      if (chunk.memory)
        break;
      if (desiredSize == requiredPages)
        return false;
      // Include the exact aligned floor, even when halving would skip it.
      desiredSize = std::max(requiredPages, (desiredSize / 2u) & ~(pageSize - 1u));
      recovered = true;
    }

    mapDeviceMemory(chunk, properties);

    // Keep the next-size power-of-two invariant for page-count-sized chunks.
    // A request larger than the normal cap can still get its full storage.
    if (recovered) {
      VkDeviceSize next = pageSize;
      while (next < chunk.size && next < chunkCap)
        next *= 2u;
      pool.nextChunkSize = std::min(next, pool.maxChunkSize);
    } else if (pool.nextChunkSize < pool.maxChunkSize
            && pool.nextChunkSize <= type.stats.memoryAllocated / 2u) {
      pool.nextChunkSize = std::min(pool.nextChunkSize * 2u,
        std::min(pool.maxChunkSize, chunkCap));
    }

''' + s[end:]
        return once(s, '    return std::max(size, DxvkMemoryPool::MinChunkSize);',
                    '    return std::min(VkDeviceSize(8u << 20), std::max(size, DxvkMemoryPool::MinChunkSize));')

    def image(s):
        # A constructor that throws never runs ~DxvkImage: publish only after
        # successful storage assignment to avoid a dangling resource-map entry.
        assert s.count('    m_allocator->registerResource(this);\n') == 2
        s = s.replace('    m_allocator->registerResource(this);\n', '')
        for call in ('assignStorage(allocateStorage());',
                     'assignStorage(m_allocator->importImageResource(imageInfo, allocationInfo, imageHandle));'):
            s = once(s, '    ' + call, '    ' + call + '\n    m_allocator->registerResource(this);')
        return once(s, '    Rc<DxvkResourceAllocation> old = std::move(m_storage);',
                    '''    // Allocation failure must leave the old image and its views intact.
    // In particular, a failed constructor has neither old nor new storage.
    if (unlikely(!resource))
      throw DxvkError("PES13 Kit17: image storage allocation failed");

    Rc<DxvkResourceAllocation> old = std::move(m_storage);''')

    def buffer(s):
        assert s.count('    m_allocator->registerResource(this);\n') == 2
        s = s.replace('    m_allocator->registerResource(this);\n', '')
        for call in ('assignStorage(allocateStorage());',
                     'assignStorage(allocator.importBufferResource(info, allocationInfo, importInfo));'):
            s = once(s, '    ' + call, '    ' + call + '\n    m_allocator->registerResource(this);')
        return s

    edit('src/dxvk/dxvk_memory.cpp', memory)
    edit('src/dxvk/dxvk_image.cpp', image)
    edit('src/dxvk/dxvk_buffer.cpp', buffer)
    edit('src/dxvk/dxvk_buffer.h', lambda s: once(s,
         '      Rc<DxvkResourceAllocation> result = std::move(m_storage);',
         '''      if (unlikely(!slice))
        throw DxvkError("PES13 Kit17: buffer storage allocation failed");
      Rc<DxvkResourceAllocation> result = std::move(m_storage);'''))
    edit('version.h.in', lambda s: once(s, '@VCS_TAG@', '@VCS_TAG@-pes13-kit17'))
    return changed
