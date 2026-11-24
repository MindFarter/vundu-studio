"""Generates a simple default app icon (PNG) when a project has none, in pure Python."""
import colorsys
import hashlib
import math
import struct
import zlib


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_rrect(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return math.hypot(x - cx, y - cy) <= r


def make_png(seed, size=256):
    hue = int(hashlib.md5(seed.encode()).hexdigest()[:4], 16) / 65535
    c1 = [int(v * 255) for v in colorsys.hsv_to_rgb(hue, 0.60, 0.92)]
    c2 = [int(v * 255) for v in colorsys.hsv_to_rgb((hue + 0.08) % 1, 0.75, 0.55)]
    k = size / 256.0
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            X, Y = x / k, y / k
            if not _in_rrect(X, Y, 8, 8, 248, 248, 52):
                raw += b"\x00\x00\x00\x00"
                continue
            t = (X + Y) / 512
            r, g, b = (int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
            if _in_rrect(X, Y, 58, 70, 198, 186, 14):  # window panel
                r, g, b = (245, 247, 250) if Y > 92 else (214, 220, 230)
                if (min(_seg_dist(X, Y, 86, 112, 112, 130), _seg_dist(X, Y, 112, 130, 86, 148)) < 6
                        or (126 <= X <= 168 and 143 <= Y <= 152)):
                    r, g, b = c2
            raw += bytes((r, g, b, 255))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
