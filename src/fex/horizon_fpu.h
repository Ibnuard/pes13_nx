// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>
#include <cstring>

// Context serialization is a bit conversion, not guest arithmetic. In
// particular it must not quiet an sNaN or depend on the host FPCR/FTZ mode.
namespace pes13_fex_fp {
struct Extended { uint64_t significand, exponent; };

inline Extended expand(uint64_t bits) {
    const uint64_t sign = (bits >> 48) & 0x8000;
    const unsigned exponent = (bits >> 52) & 0x7ff;
    const uint64_t fraction = bits & 0xfffffffffffffULL;
    if (exponent == 0x7ff) return {(1ULL << 63) | (fraction << 11), sign | 0x7fff};
    if (exponent) return {(1ULL << 63) | (fraction << 11), sign | (exponent + 15360)};
    if (!fraction) return {0, sign};
    const unsigned shift = __builtin_clzll(fraction);
    return {fraction << shift, sign | (15372 - shift)};
}

inline uint64_t rounded(uint64_t value, unsigned shift, unsigned mode, bool negative) {
    uint64_t result = shift < 64 ? value >> shift : 0;
    const uint64_t remainder = shift < 64 ? value & ((1ULL << shift) - 1) : value;
    if (!remainder) return result;
    bool up = (mode == 1 && negative) || (mode == 2 && !negative);
    if (mode == 0 && shift <= 64) {
        const uint64_t half = 1ULL << (shift - 1);
        up = remainder > half || (remainder == half && (result & 1));
    }
    return result + up;
}

inline uint64_t narrow(Extended value, uint16_t fcw) {
    const uint64_t sign = (value.exponent & 0x8000) << 48;
    const unsigned exponent = value.exponent & 0x7fff;
    const unsigned mode = (fcw >> 10) & 3;
    uint64_t significand = value.significand;
    if (exponent && !(significand >> 63)) return 0xfff8000000000000ULL; // x87 unsupported
    if (exponent == 0x7fff) {
        uint64_t fraction = (significand & 0x7fffffffffffffffULL) >> 11;
        if (!fraction && (significand & 0x7fffffffffffffffULL)) fraction = 1;
        return sign | 0x7ff0000000000000ULL | fraction;
    }
    if (!significand) return sign;
    int power = int(exponent ? exponent : 1) - 16383;
    const unsigned normalize = __builtin_clzll(significand);
    significand <<= normalize;
    power -= normalize;
    auto overflow = [&] {
        const bool infinity = mode == 0 || (mode == 1 && sign) || (mode == 2 && !sign);
        return sign | (infinity ? 0x7ff0000000000000ULL : 0x7fefffffffffffffULL);
    };
    if (power > 1023) return overflow();
    if (power < -1022) return sign | rounded(significand, unsigned(-1011 - power), mode, sign != 0);
    uint64_t mantissa = rounded(significand, 11, mode, sign != 0);
    if (mantissa == (1ULL << 53)) { mantissa >>= 1; ++power; }
    if (power > 1023) return overflow();
    return sign | (uint64_t(power + 1023) << 52) | (mantissa & 0xfffffffffffffULL);
}
}

extern "C" void PES13FexImportX87(void *internal, const void *external,
                                  uint16_t status, uint16_t control, bool reduced);
extern "C" void PES13FexExportX87(void *external, const void *internal,
                                  uint16_t status, bool reduced);
