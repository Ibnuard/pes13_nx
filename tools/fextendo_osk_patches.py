"""Backport Autorun's in-frame OSK to the original r6 Vulkan presenter only.

Both shipped renderers (DXVK default and GPL Async) use this presenter.
No Kitserver, timing, FEX or driver upgrade is imported.
"""
from pes_low_window_patches import exact


def apply(source):
    p = source/'dlls/win32u/vulkan.c'
    s = p.read_text()
    s = exact(s, 'struct swapchain\n{', '''#ifdef __SWITCH__
#include "fextendo_osk_frame.h"
struct nx_osk_overlay;
static void nx_osk_free(struct vulkan_device *, struct nx_osk_overlay *);
#endif

struct swapchain
{''')
    s = exact(s, '    /* fs hack data below */', '''#ifdef __SWITCH__
    VkExtent2D nx_extent;
    VkFormat nx_format;
    BOOL nx_osk_usable;
    struct nx_osk_overlay *nx_osk;
#endif
    /* fs hack data below */''')
    s = exact(s, '    if ((res = device->p_vkCreateSwapchainKHR( device->host.device, &create_info_host, NULL, &host_swapchain )))', '''#ifdef __SWITCH__
    swapchain->nx_extent = create_info_host.imageExtent;
    swapchain->nx_format = create_info_host.imageFormat;
    if ((capabilities.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT) &&
        (create_info_host.imageFormat == VK_FORMAT_B8G8R8A8_UNORM ||
         create_info_host.imageFormat == VK_FORMAT_B8G8R8A8_SRGB ||
         create_info_host.imageFormat == VK_FORMAT_R8G8B8A8_UNORM ||
         create_info_host.imageFormat == VK_FORMAT_R8G8B8A8_SRGB))
    {
        create_info_host.imageUsage |= VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        swapchain->nx_osk_usable = TRUE;
    }
#endif
    if ((res = device->p_vkCreateSwapchainKHR( device->host.device, &create_info_host, NULL, &host_swapchain )))''')
    s = exact(s, '    if (!swapchain) return;\n\n    if (swapchain->fshack_dpi)', '''    if (!swapchain) return;
#ifdef __SWITCH__
    if (swapchain->nx_osk)
    {
        /* Resources include presentation wait semaphores, so retire only
         * after the device has finished using the old swapchain. */
        device->p_vkDeviceWaitIdle(device->host.device);
        nx_osk_free(device, swapchain->nx_osk);
    }
#endif

    if (swapchain->fshack_dpi)''')
    s = exact(s, 'static VkResult win32u_vkQueuePresentKHR(', '''#ifdef __SWITCH__
#include "fextendo_osk_vulkan.h"
#endif

static VkResult win32u_vkQueuePresentKHR(''')
    s = exact(s, '    pthread_mutex_lock( &lock );\n    fex_host = wine_nx_fex_frame_tick();', '''    pthread_mutex_lock( &lock );
#ifdef __SWITCH__
    uint64_t osk_session = nx_osk_present(queue, present_info, client_swapchains, &pool);
#endif
    fex_host = wine_nx_fex_frame_tick();''')
    s = exact(s, '    fex_host_end = wine_nx_fex_frame_tick();\n    pthread_mutex_unlock( &lock );', '''    fex_host_end = wine_nx_fex_frame_tick();
#ifdef __SWITCH__
    if (osk_session)
    {
        if (res >= VK_SUCCESS && (!present_info->pResults || present_info->pResults[0] >= VK_SUCCESS))
            fx_osk_frame_presented(osk_session);
        else fx_osk_frame_reject(osk_session);
    }
#endif
    pthread_mutex_unlock( &lock );''')
    p.write_text(s)
