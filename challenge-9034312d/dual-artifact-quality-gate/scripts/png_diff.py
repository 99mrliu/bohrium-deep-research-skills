#!/usr/bin/env python3
"""Compare actual 8-bit non-interlaced PNG pixels using Python stdlib only."""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chunk(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", binascii.crc32(name + payload) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, rgba: bytes | bytearray) -> None:
    if width <= 0 or height <= 0 or len(rgba) != width * height * 4:
        raise ValueError("Invalid RGBA buffer dimensions")
    raw = bytearray()
    stride = width * 4
    for row in range(height):
        raw.append(0)
        raw.extend(rgba[row * stride:(row + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_png(path: Path) -> tuple[int, int, bytearray, dict[str, Any]]:
    data = path.read_bytes()
    if not data.startswith(SIGNATURE):
        raise ValueError("Not a PNG file")
    offset = len(SIGNATURE)
    width = height = depth = color = interlace = None
    idat = bytearray()
    palette: list[tuple[int, int, int]] = []
    transparency: bytes = b""
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        name = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        expected = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if len(payload) != length or expected != (binascii.crc32(name + payload) & 0xFFFFFFFF):
            raise ValueError("Truncated PNG or CRC mismatch")
        if name == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif name == b"IDAT":
            idat.extend(payload)
        elif name == b"PLTE":
            palette = [tuple(payload[i:i + 3]) for i in range(0, len(payload), 3)]
        elif name == b"tRNS":
            transparency = payload
        elif name == b"IEND":
            break
        offset += length + 12
    if width is None or height is None or width <= 0 or height <= 0:
        raise ValueError("Missing/invalid IHDR")
    if depth != 8 or interlace != 0:
        raise ValueError("Only 8-bit non-interlaced PNG is supported")
    channels_by_color = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color not in channels_by_color:
        raise ValueError(f"Unsupported PNG color type {color}")
    channels = channels_by_color[color]
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    if len(raw) != height * (stride + 1):
        raise ValueError("Unexpected decompressed PNG size")
    unfiltered = bytearray(height * stride)
    previous = bytearray(stride)
    cursor = 0
    for row in range(height):
        filter_type = raw[cursor]
        cursor += 1
        source = raw[cursor:cursor + stride]
        cursor += stride
        target = bytearray(stride)
        for i, byte in enumerate(source):
            left = target[i - channels] if i >= channels else 0
            up = previous[i]
            upper_left = previous[i - channels] if i >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                predictor = paeth(left, up, upper_left)
            else:
                raise ValueError(f"Unsupported PNG filter {filter_type}")
            target[i] = (byte + predictor) & 255
        unfiltered[row * stride:(row + 1) * stride] = target
        previous = target
    rgba = bytearray(width * height * 4)
    for index in range(width * height):
        source = index * channels
        dest = index * 4
        if color == 6:
            rgba[dest:dest + 4] = unfiltered[source:source + 4]
        elif color == 2:
            rgba[dest:dest + 3] = unfiltered[source:source + 3]
            rgba[dest + 3] = 255
        elif color == 0:
            gray = unfiltered[source]
            rgba[dest:dest + 4] = bytes((gray, gray, gray, 255))
        elif color == 4:
            gray, alpha = unfiltered[source:source + 2]
            rgba[dest:dest + 4] = bytes((gray, gray, gray, alpha))
        elif color == 3:
            palette_index = unfiltered[source]
            if palette_index >= len(palette):
                raise ValueError("PNG palette index out of range")
            rgb = palette[palette_index]
            alpha = transparency[palette_index] if palette_index < len(transparency) else 255
            rgba[dest:dest + 4] = bytes((*rgb, alpha))
    return width, height, rgba, {"bit_depth": depth, "color_type": color, "interlace": interlace}


def build_diff(before: Path, after: Path, diff: Path | None = None,
               before_review: Path | None = None, after_review: Path | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "dual-artifact-quality-gate/visual-diff-v1",
        "before": {"path": before.name, "sha256": sha256(before)},
        "after": {"path": after.name, "sha256": sha256(after)},
        "difference_meaning": "pixel change only; improvement requires source-backed agent/human review",
        "errors": [],
    }
    try:
        bw, bh, bp, bmeta = read_png(before)
        aw, ah, ap, ameta = read_png(after)
        report["before"].update({"width": bw, "height": bh, "encoding": bmeta})
        report["after"].update({"width": aw, "height": ah, "encoding": ameta})
        if (bw, bh) != (aw, ah):
            report["errors"].append({"code": "VISUAL_DIFF_DIMENSION_MISMATCH", "message": f"{bw}x{bh} versus {aw}x{ah}"})
        else:
            changed = 0
            min_x, min_y, max_x, max_y = bw, bh, -1, -1
            diff_pixels = bytearray(aw * ah * 4)
            total_changed_channels = 0
            for index in range(aw * ah):
                pos = index * 4
                different = bp[pos:pos + 4] != ap[pos:pos + 4]
                if different:
                    changed += 1
                    total_changed_channels += sum(bp[pos + c] != ap[pos + c] for c in range(4))
                    x, y = index % aw, index // aw
                    min_x, min_y, max_x, max_y = min(min_x, x), min(min_y, y), max(max_x, x), max(max_y, y)
                    diff_pixels[pos:pos + 4] = b"\xff\x00\x91\xff"
                else:
                    # Dim after-image context while retaining its RGB variation.
                    diff_pixels[pos] = int(ap[pos] * 0.25 + 191)
                    diff_pixels[pos + 1] = int(ap[pos + 1] * 0.25 + 191)
                    diff_pixels[pos + 2] = int(ap[pos + 2] * 0.25 + 191)
                    diff_pixels[pos + 3] = 255
            report.update({
                "width": aw, "height": ah, "total_pixels": aw * ah,
                "differing_pixels": changed,
                "differing_ratio": changed / (aw * ah),
                "differing_channels": total_changed_channels,
                "difference_detected": changed > 0,
                "changed_bounding_box": None if not changed else [min_x, min_y, max_x, max_y],
            })
            if diff:
                write_png(diff, aw, ah, diff_pixels)
                report["diff_image"] = {"path": diff.name, "sha256": sha256(diff), "changed_pixel_color": "#ff0091"}
    except (OSError, ValueError, zlib.error, struct.error) as exc:
        report["errors"].append({"code": "VISUAL_DIFF_DECODE_ERROR", "message": str(exc)})
    for key, review in (("before_review", before_review), ("after_review", after_review)):
        if review:
            try:
                report[key] = {"path": review.name, "sha256": sha256(review)}
            except OSError as exc:
                report["errors"].append({"code": "VISUAL_REVIEW_MISSING", "message": str(exc)})
    report["status"] = "pass" if not report["errors"] else "fail"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--diff", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--before-review", type=Path)
    parser.add_argument("--after-review", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_diff(args.before, args.after, args.diff, args.before_review, args.after_review)
    except OSError as exc:
        report = {"schema": "dual-artifact-quality-gate/visual-diff-v1", "status": "fail",
                  "errors": [{"code": "VISUAL_DIFF_INPUT_ERROR", "message": str(exc)}]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
