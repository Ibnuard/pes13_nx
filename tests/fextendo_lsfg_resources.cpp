// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the actual pinned DLL reader; never load/execute proprietary code.
#include "extraction/dll_reader.hpp"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    try {
        auto resources = lsfgvk::backend::extractResourcesFromDLL(argv[1]);
        unsigned checked = 0;
        auto check = [&](uint32_t id) {
            const auto &data = resources.at(id);
            if (data.size() < 20 || data.size() % 4) throw std::runtime_error("truncated SPIR-V");
            auto word = [&](size_t index) { uint32_t value; std::memcpy(&value, data.data() + index * 4, 4); return value; };
            if (word(0) != 0x07230203 || word(3) == 0 || word(4) != 0) throw std::runtime_error("invalid SPIR-V header");
            for (size_t i = 5; i < data.size()/4;) {
                const unsigned count = word(i) >> 16;
                if (!count || i + count > data.size()/4) throw std::runtime_error("invalid SPIR-V instruction");
                i += count;
            }
            ++checked;
        };
        check(49 + 49 + 256); // shared FP32 generate shader
        for (unsigned perf = 0; perf < 2; ++perf)
            for (uint32_t id = 257; id <= 278; ++id) check(49 + 49 + perf * 23 + id);
        std::cout << "{\"resource_count\":" << resources.size() << ",\"required_fp32_shaders\":" << checked << ",\"ok\":true}\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
