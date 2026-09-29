"""Pinned native LSFG presentation integration; disabled until runtime configure()."""


def apply(read, replace, project):
    name = 'dlls/win32u/vulkan.c'
    anchor = 'WINE_DEFAULT_DEBUG_CHANNEL(vulkan);'
    replace(name, anchor, '#ifdef WINE_NX_LSFG\n#include "' + str(project / 'src/runtime/fextendo_lsfg.h') + '"\n#endif\n\n' + anchor)
    # Use the existing presentation serialization for both external acquires and
    # LSFG's internal present/reacquire/restore sequence. Do not hold it over an
    # external acquire: a waiting acquire must not block the present that frees VI.
    replace(name, 'struct swapchain\n{', 'static pthread_mutex_t present_lock = PTHREAD_MUTEX_INITIALIZER;\n\nstruct swapchain\n{')
    replace(name, '    VkExtent2D extents;\n\n    /* fs hack data below */', '''    VkExtent2D extents;
#ifdef WINE_NX_LSFG
    struct wine_nx_lsfg *lsfg;
    unsigned int lsfg_acquires;
#endif

    /* fs hack data below */''')
    replace(name, '''            create_info->pEnabledFeatures = &features;
        }
}''', '''            create_info->pEnabledFeatures = &features;
        }
#ifdef WINE_NX_LSFG
        wine_nx_lsfg_device_features( instance->host.instance, physical_device->host.physical_device,
                                     features2 ? &features2->features : &features );
#endif
}''')
    anchor = '    VkSwapchainKHR host_swapchain;'
    replace(name, anchor, anchor + '\n#ifdef WINE_NX_LSFG\n    int lsfg = 0;\n#endif')
    anchor = '    if ((res = device->p_vkCreateSwapchainKHR( device->host.device, &create_info_host, NULL, &host_swapchain )))'
    replace(name, anchor, '''#ifdef WINE_NX_LSFG
    lsfg = wine_nx_lsfg_prepare_swapchain( instance->host.instance, physical_device->host.physical_device,
                                          &create_info_host );
#endif
''' + anchor)
    anchor = '    *ret = swapchain->obj.client.swapchain;'
    replace(name, anchor, '''#ifdef WINE_NX_LSFG
    if (lsfg)
        swapchain->lsfg = wine_nx_lsfg_create( instance->host.instance, physical_device->host.physical_device,
                                             device->host.device, host_swapchain, &create_info_host );
#endif
''' + anchor)
    anchor = '    if (!swapchain) return;'
    replace(name, anchor, anchor + '''
#ifdef WINE_NX_LSFG
    wine_nx_lsfg_destroy( swapchain->lsfg );
#endif''')
    before = '''#ifdef WINE_NX_LSFG
    if (swapchain->lsfg)
    {
        pthread_mutex_lock( &present_lock );
        ++swapchain->lsfg_acquires;
        pthread_mutex_unlock( &present_lock );
    }
#endif
'''
    after = '''
#ifdef WINE_NX_LSFG
    if (swapchain->lsfg)
    {
        pthread_mutex_lock( &present_lock );
        --swapchain->lsfg_acquires;
        pthread_mutex_unlock( &present_lock );
    }
#endif'''
    for anchor in (
        '    res = device->p_vkAcquireNextImage2KHR( device->host.device, &acquire_info_host, image_index );',
        '''    res = device->p_vkAcquireNextImageKHR( device->host.device, swapchain->obj.host.swapchain, timeout,
                                              semaphore ? semaphore->host.semaphore : 0, fence ? fence->host.fence : 0,
                                              image_index );'''):
        replace(name, anchor, before + anchor + after)
    replace(name, '    static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;\n\n    VkPresentInfoKHR', '    VkPresentInfoKHR')
    replace(name, '    pthread_mutex_lock( &lock );', '    pthread_mutex_lock( &present_lock );')
    replace(name, '    pthread_mutex_unlock( &lock );', '    pthread_mutex_unlock( &present_lock );')
    anchor = '    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );'
    replace(name, anchor, '''#ifdef WINE_NX_LSFG
    if (!present_info->swapchainCount ||
        !wine_nx_lsfg_present( swapchain_from_handle( client_swapchains[0] )->lsfg,
                               queue->host.queue, queue->info.queueFamilyIndex,
                               !swapchain_from_handle( client_swapchains[0] )->lsfg_acquires, present_info, &res ))
#endif
''' + anchor)

    name = 'wine-nx-probe/CMakeLists.txt'
    anchor = 'set_target_properties(wine-nx-runtime PROPERTIES SUFFIX ".elf")'
    replace(name, anchor, anchor + '''

# FEXTendo: pinned native backend, never execute the proprietary DLL.
set(PES13_LSFG_PREFIX "" CACHE PATH "Private installation from build-fextendo-lsfg.py")
if(NOT EXISTS "${PES13_LSFG_PREFIX}/lib/liblsfg-vk.a" OR
   NOT EXISTS "${PES13_LSFG_PREFIX}/share/licenses/lsfg-vk/LICENSE.md")
    message(FATAL_ERROR "Build the pinned native LSFG backend and set PES13_LSFG_PREFIX")
endif()
add_library(wine-nx-lsfg STATIC "''' + str(project / 'src/runtime/fextendo_lsfg.cpp') + '''")
set_target_properties(wine-nx-lsfg PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(wine-nx-lsfg PRIVATE
    "${PES13_LSFG_PREFIX}/include" "${WINE_NX_MESA_SWITCH_DIR}/../include")
target_compile_options(wine-nx-lsfg PRIVATE -ffixed-x18 -Wall -Wextra -Wno-missing-field-initializers)
target_link_libraries(wine-nx-lsfg PRIVATE "${PES13_LSFG_PREFIX}/lib/liblsfg-vk.a")
target_compile_definitions(wine-nx-runtime PRIVATE WINE_NX_LSFG)
target_compile_definitions(wine-win32u-real PRIVATE WINE_NX_LSFG)
target_link_libraries(wine-nx-runtime PRIVATE wine-nx-lsfg)
configure_file("${PES13_LSFG_PREFIX}/share/licenses/lsfg-vk/LICENSE.md"
    "${CMAKE_CURRENT_BINARY_DIR}/licenses/LSFG-VK-GPL-3.0.txt" COPYONLY)
''')
