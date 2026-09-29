# LSFG-VK's backend for Horizon: the pinned GPL archive revision with
# horizon.patch applied, and the NVK reduction shaders compiled into it.
# Installs liblsfg-vk.a and the lsfg-vk-common and lsfg-vk-backend headers.
cmake_minimum_required(VERSION 3.20)
project(lsfg-vk-horizon CXX)
set(LSFG_SOURCE "" CACHE PATH "lsfg-vk checkout with horizon.patch applied")
set(LSFG_VULKAN_INCLUDE "" CACHE PATH "Directory containing vulkan/vulkan_core.h")
if(NOT EXISTS "${LSFG_VULKAN_INCLUDE}/vulkan/vulkan_core.h")
    message(FATAL_ERROR "Set LSFG_VULKAN_INCLUDE to the runtime's Mesa Vulkan headers")
endif()

find_program(GLSLANG_VALIDATOR glslangValidator REQUIRED)
set(generated "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${generated}")
set(names nvk_mipmap_luma nvk_mipmap_downsample nvk_beta1_finalize_quality nvk_beta1_finalize_performance)
set(symbols kNvkMipmapLumaSpv kNvkMipmapDownsampleSpv kNvkBeta1FinalizeQualitySpv kNvkBeta1FinalizePerformanceSpv)
foreach(index RANGE 0 3)
    list(GET names ${index} name)
    list(GET symbols ${index} symbol)
    add_custom_command(OUTPUT "${generated}/${name}.h"
        COMMAND "${GLSLANG_VALIDATOR}" -V --target-env vulkan1.1 --vn "${symbol}"
            -o "${generated}/${name}.h" "${CMAKE_CURRENT_SOURCE_DIR}/shaders/${name}.comp"
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/shaders/${name}.comp" VERBATIM)
    list(APPEND headers "${generated}/${name}.h")
endforeach()

file(GLOB common "${LSFG_SOURCE}/lsfg-vk-common/src/vulkan/*.cpp")
file(GLOB_RECURSE backend "${LSFG_SOURCE}/lsfg-vk-backend/src/*.cpp")
add_library(lsfg-vk STATIC ${common} ${backend} "${LSFG_SOURCE}/lsfg-vk-common/src/helpers/errors.cpp" ${headers})
set_target_properties(lsfg-vk PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(lsfg-vk PRIVATE
    "${LSFG_VULKAN_INCLUDE}"
    "${LSFG_SOURCE}/lsfg-vk-common/include"
    "${LSFG_SOURCE}/lsfg-vk-backend/include"
    "${LSFG_SOURCE}/lsfg-vk-backend/src"
    "${CMAKE_CURRENT_SOURCE_DIR}" "${generated}")
target_compile_options(lsfg-vk PRIVATE -Wall -Wextra -Wno-missing-field-initializers)

install(TARGETS lsfg-vk ARCHIVE DESTINATION lib)
install(DIRECTORY "${LSFG_SOURCE}/lsfg-vk-common/include/" "${LSFG_SOURCE}/lsfg-vk-backend/include/"
    DESTINATION include)
install(FILES "${LSFG_SOURCE}/LICENSE.md" DESTINATION share/licenses/lsfg-vk)
install(FILES "${LSFG_SOURCE}/lsfg-vk-backend/src/extraction/dll_reader.hpp"
    DESTINATION include/lsfg-vk-backend)
