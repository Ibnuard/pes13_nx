/* LGPL-2.1-or-later. Present scaling must not read the frame back to the CPU.
 * Preserve the submitted commands/semaphores and propagate submit failures:
 * otherwise Present could wait for a blit semaphore never signaled. */
static VkResult __attribute__((noinline)) nx_submit_scaled(
    struct vulkan_queue *queue, VkSubmitInfo *submit_info)
{
    uint64_t begin = wine_nx_fex_frame_tick();
    VkResult result = queue->device->p_vkQueueSubmit(queue->host.queue, 1, submit_info, VK_NULL_HANDLE);
    wine_nx_fex_pipeline_note(1, begin, result);
    return result;
}
