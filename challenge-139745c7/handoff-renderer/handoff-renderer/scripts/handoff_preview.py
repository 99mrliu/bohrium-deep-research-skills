#!/usr/bin/env python3
"""Render real PNG previews for editable deliverables, dependency-free.

Pure stdlib: zlib + struct write a valid 8-bit grayscale PNG; glyphs come
from an embedded 5x7 bitmap font (ASCII); non-ASCII characters render as a
box glyph (their identity is given by the F-number legend in INDEX.md).

  preview_structure.png  one row per manifest entry (id + sanitized name)
  preview_index.png      first lines of INDEX.md

Also re-reads each produced PNG (signature + IHDR) to prove validity.

Usage: handoff_preview.py OUT_DIR
"""
import json
import os
import struct
import sys
import zlib

FONT = {
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    "_": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    ":": [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00],
    "/": [0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10],
    "(": [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ")": [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
    "#": [0x0A, 0x1F, 0x0A, 0x0A, 0x1F, 0x0A, 0x00],
    " ": [0x00] * 7,
}
BOX = [0x1F, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1F]


def render_png(lines, path, scale=2):
    cell_w, cell_h = 6 * scale, 9 * scale
    width = max(120, max((len(l) for l in lines), default=10) * cell_w + 8)
    height = max(40, len(lines) * cell_h + 8)
    img = bytearray([255]) * (width * height)

    def put_pixel(x, y, v):
        if 0 <= x < width and 0 <= y < height:
            img[y * width + x] = v

    for row, line in enumerate(lines):
        for col, ch in enumerate(line):
            glyph = FONT.get(ch.upper(), BOX)
            for gy, bits in enumerate(glyph):
                for gx in range(5):
                    if bits & (1 << (4 - gx)):
                        for sy in range(scale):
                            for sx in range(scale):
                                put_pixel(4 + col * cell_w + gx * scale + sx,
                                          4 + row * cell_h + gy * scale + sy,
                                          0)
    raw = b"".join(b"\x00" + bytes(img[y * width:(y + 1) * width])
                   for y in range(height))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return width, height


def check_png(path):
    with open(path, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            return None
        f.read(4)
        if f.read(4) != b"IHDR":
            return None
        w, h = struct.unpack(">II", f.read(8))
        return w, h


def sanitize(text, maxlen=44):
    out = []
    for ch in str(text):
        out.append(ch if (ch.isascii() and (ch.isalnum()
                                            or ch in "-_.:/()# ")) else "?")
    return "".join(out)[:maxlen]


def main():
    out_dir = sys.argv[1]
    made = {}
    manifest_p = os.path.join(out_dir, "manifest.json")
    if os.path.exists(manifest_p):
        manifest = json.load(open(manifest_p, encoding="utf-8"))
        lines = ["LIBRARY STRUCTURE PREVIEW", ""]
        for ent in manifest.get("entries", []):
            name = os.path.basename(ent["input_path"])
            lines.append("%s %s" % (ent["id"], sanitize(name)))
        p = os.path.join(out_dir, "preview_structure.png")
        made["preview_structure.png"] = render_png(lines, p)
    index_p = os.path.join(out_dir, "INDEX.md")
    if os.path.exists(index_p):
        with open(index_p, encoding="utf-8") as f:
            src = [l.rstrip() for l in f.read().splitlines() if l.strip()][:24]
        p = os.path.join(out_dir, "preview_index.png")
        made["preview_index.png"] = render_png([sanitize(l, 60) for l in src], p)
    verified = {}
    for name in made:
        dims = check_png(os.path.join(out_dir, name))
        verified[name] = {"rendered": made[name], "readback": dims,
                          "valid": dims is not None}
    with open(os.path.join(out_dir, "preview_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(verified, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v["valid"] for k, v in verified.items()}))


if __name__ == "__main__":
    main()
