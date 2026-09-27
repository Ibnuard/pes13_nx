"""Create checksummed 16:9 benchmark settings, keeping quality status explicit.

0x1c=1 is a Medium candidate inferred from Kitserver's memory layout. Its
retail settings.dat interpretation is NOT verified. Do not expose it as a
verified --quality option on make-settings.py or relabel the original word.
"""
import binascii
import hashlib
import importlib.util
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def preset(original, width, height, *, medium_candidate=False):
    spec = importlib.util.spec_from_file_location('settings', ROOT/'tools/make-settings.py')
    settings = importlib.util.module_from_spec(spec); spec.loader.exec_module(settings)
    settings.validate(original)
    if struct.unpack_from('<HIIIII', original, 14) != (0x288, 960, 540, 1, 0, 1):
        raise ValueError('Expected untouched worker-cores 540p settings')
    if (width, height) not in ((960, 540), (1280, 720)):
        raise ValueError('Benchmark supports only the two 16:9 resolutions')
    data = bytearray(original)
    struct.pack_into('<II', data, 16, width, height)
    if medium_candidate:
        struct.pack_into('<I', data, 0x1c, 1)
    struct.pack_into('<H', data, 12, 0)
    struct.pack_into('<H', data, 12, settings.crc16(data))
    settings.validate(data)
    zeroed = bytearray(data); zeroed[12:14] = b'\0\0'
    if struct.unpack_from('<H', data, 12)[0] != (~binascii.crc_hqx(zeroed, 0) & 0xffff):
        raise ValueError('Independent CRC verification failed')
    permitted = {12, 13, *range(16,24)} | ({28,29,30,31} if medium_candidate else set())
    changes = [i for i, (a, b) in enumerate(zip(original, data)) if a != b]
    if any(i not in permitted for i in changes):
        raise ValueError('Unrelated settings changed')
    if data[24:28] != original[24:28] or data[32:] != original[32:]:
        raise ValueError('Aspect/controller/unrelated data changed')
    return bytes(data), {
        'resolution': [width,height], 'vsync': False, 'frame_skip': False,
        'aspect_word_0x18': 1, 'picture_word_0x1c': 1 if medium_candidate else 0,
        'quality_requested': 'Medium' if medium_candidate else 'original raw preset',
        'quality_verified': False,
        'quality_basis': 'Kitserver demo memory layout; retail disk mapping inferred' if medium_candidate else 'unchanged',
        'changed_byte_offsets': changes, 'sha256': hashlib.sha256(data).hexdigest(),
        'checksum_independently_verified': True,
    }
