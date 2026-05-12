#!/usr/bin/env python3
"""
MegaDL — generate_icons.py
Generates placeholder PNG icons for PWA using pure Python (no Pillow needed).
Creates valid PNG files with the MegaDL logo gradient.
"""

import struct
import zlib
import os
from pathlib import Path

ICONS_DIR = Path(__file__).parent / 'frontend' / 'assets' / 'icons'
ICONS_DIR.mkdir(parents=True, exist_ok=True)

SIZES = [72, 96, 128, 192, 512]

def make_png(size: int) -> bytes:
    """Generate a simple gradient PNG with download arrow icon."""
    w = h = size
    
    # Create RGBA pixel data
    pixels = []
    cx, cy = w // 2, h // 2
    r_outer = min(w, h) // 2
    
    for y in range(h):
        row = []
        for x in range(w):
            # Distance from center for circle
            dx = x - cx
            dy = y - cy
            dist = (dx*dx + dy*dy) ** 0.5
            
            if dist <= r_outer:
                # Gradient: indigo (#6c63ff) to purple (#a855f7)
                t = (x + y) / (w + h)
                r = int(108 + (168 - 108) * t)
                g = int(99  + (85  - 99)  * t)
                b = int(255 + (247 - 255) * t)
                a = 255
                
                # Draw download arrow (white)
                norm_x = (x - cx) / r_outer
                norm_y = (y - cy) / r_outer
                
                # Arrow shaft: vertical line
                shaft_w = 0.06
                if abs(norm_x) < shaft_w and -0.45 < norm_y < 0.25:
                    r, g, b = 255, 255, 255
                
                # Arrow head: V shape
                arrow_tip_y = 0.3
                arrow_w = 0.38
                if abs(norm_y - arrow_tip_y) < 0.12:
                    expected_x = arrow_w * (1 - (norm_y - arrow_tip_y + 0.12) / 0.12)
                    if abs(abs(norm_x) - expected_x) < 0.06:
                        r, g, b = 255, 255, 255
                
                # Bottom bar
                bar_y = 0.55
                bar_w = 0.48
                if abs(norm_y - bar_y) < 0.07 and abs(norm_x) < bar_w:
                    r, g, b = 255, 255, 255
                
                row.extend([r, g, b, a])
            else:
                row.extend([0, 0, 0, 0])  # transparent outside circle
        
        pixels.append(bytes(row))
    
    return _encode_png(w, h, pixels)


def _encode_png(w: int, h: int, rows: list) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    
    # PNG signature
    sig = b'\x89PNG\r\n\x1a\n'
    
    # IHDR: width, height, bit depth=8, color type=6 (RGBA), compression=0, filter=0, interlace=0
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    
    # IDAT: compress pixel data
    raw = b''
    for row in rows:
        raw += b'\x00' + row  # filter type 0 (None) per row
    
    idat = zlib.compress(raw, 9)
    
    # IEND
    return (sig
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', idat)
            + chunk(b'IEND', b''))


if __name__ == '__main__':
    for size in SIZES:
        path = ICONS_DIR / f'icon-{size}.png'
        data = make_png(size)
        path.write_bytes(data)
        print(f'Generated: {path} ({len(data):,} bytes)')
    print(f'\nIcons saved to: {ICONS_DIR}')
