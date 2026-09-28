// SPDX-License-Identifier: MIT
#include "horizon_fpu.h"

extern "C" void PES13FexImportX87(void *internal, const void *external,
                                  uint16_t status, uint16_t control, bool reduced) {
    auto *destination = static_cast<uint64_t (*)[2]>(internal);
    const auto *source = static_cast<const unsigned char *>(external);
    const unsigned top = (status >> 11) & 7;
    for (unsigned i = 0; i < 8; ++i) {
        pes13_fex_fp::Extended value;
        std::memcpy(&value, source + i * 16, sizeof(value));
        const unsigned physical = (top + i) & 7;
        destination[physical][0] = reduced ? pes13_fex_fp::narrow(value, control) : value.significand;
        destination[physical][1] = reduced ? 0 : value.exponent & 0xffff;
    }
}

extern "C" void PES13FexExportX87(void *external, const void *internal,
                                  uint16_t status, bool reduced) {
    auto *destination = static_cast<unsigned char *>(external);
    const auto *source = static_cast<const uint64_t (*)[2]>(internal);
    const unsigned top = (status >> 11) & 7;
    for (unsigned i = 0; i < 8; ++i) {
        const unsigned physical = (top + i) & 7;
        const auto value = reduced ? pes13_fex_fp::expand(source[physical][0])
            : pes13_fex_fp::Extended{source[physical][0], source[physical][1] & 0xffff};
        std::memcpy(destination + i * 16, &value, sizeof(value));
    }
}
