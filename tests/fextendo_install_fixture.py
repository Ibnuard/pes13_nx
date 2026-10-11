"""Synthetic game files with the archive names observed in the reference install."""
import struct

ARCHIVES = ('dt01.img', 'dt02.img', 'dt03.img', 'dt04.img', 'dt06.img', 'dt07.img',
            'dt08.img', 'dt09.img', 'dt0a.img', 'dt0b.img', 'dt0c.img', 'dt0d.img',
            'dt0e.img', 'dt0f.img', 'dt10.img', 'dt11.img', 'dt00_e.img', 'dt05_e.img')

def archive():
    # A real AFS directory may begin with an unused entry of length zero.
    return (b'AFS\0' + struct.pack('<IIIII', 2, 2048, 0, 2048, 16)
            + bytes(2048 - 24) + b'fixture payload!')

def make_game(game):
    (game / 'img').mkdir(parents=True, exist_ok=True)
    exe = bytearray(128)
    exe[:2] = b'MZ'
    struct.pack_into('<I', exe, 60, 64)
    exe[64:68] = b'PE\0\0'
    struct.pack_into('<H', exe, 68, 0x14c)
    struct.pack_into('<H', exe, 88, 0x10b)
    (game / 'pes2013.exe').write_bytes(exe)
    for name in ARCHIVES:
        (game / 'img' / name).write_bytes(archive())
