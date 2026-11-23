#!/usr/bin/env python3
"""render_preview.py — 把 result.json 的填充状态渲染为真实预览产物。

产物：preview.svg（字符串模板生成，ET 校验 well-formed 后才落盘）；
preview.png（stdlib zlib+struct 手写 PNG 编码器栅格化同一面板，5x7 ASCII
点阵字体，不渲染 CJK，非 ASCII 以 '?' 代替）；preview_record.json（各产物
sha256、尺寸、渲染器信息）。若存在 rsvg-convert/inkscape/magick 之一，额外
渲染 SVG->PNG 高清版并记录尺寸对比；全缺则 preview_note 记明降级。
确定性：无时间戳/随机数，重跑字节一致；绝不因畸形输入崩溃；仅用标准库。
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib
from xml.sax.saxutils import escape

# ---------------------------------------------------------------- 5x7 点阵字体
FONT = {
 "A":("01110","10001","10001","11111","10001","10001","10001"),
 "B":("11110","10001","10001","11110","10001","10001","11110"),
 "C":("01110","10001","10000","10000","10000","10001","01110"),
 "D":("11110","10001","10001","10001","10001","10001","11110"),
 "E":("11111","10000","10000","11110","10000","10000","11111"),
 "F":("11111","10000","10000","11110","10000","10000","10000"),
 "G":("01110","10001","10000","10111","10001","10001","01111"),
 "H":("10001","10001","10001","11111","10001","10001","10001"),
 "I":("01110","00100","00100","00100","00100","00100","01110"),
 "J":("00111","00010","00010","00010","00010","10010","01100"),
 "K":("10001","10010","10100","11000","10100","10010","10001"),
 "L":("10000","10000","10000","10000","10000","10000","11111"),
 "M":("10001","11011","10101","10101","10001","10001","10001"),
 "N":("10001","11001","10101","10011","10001","10001","10001"),
 "O":("01110","10001","10001","10001","10001","10001","01110"),
 "P":("11110","10001","10001","11110","10000","10000","10000"),
 "Q":("01110","10001","10001","10001","10101","10010","01101"),
 "R":("11110","10001","10001","11110","10100","10010","10001"),
 "S":("01111","10000","10000","01110","00001","00001","11110"),
 "T":("11111","00100","00100","00100","00100","00100","00100"),
 "U":("10001","10001","10001","10001","10001","10001","01110"),
 "V":("10001","10001","10001","10001","10001","01010","00100"),
 "W":("10001","10001","10001","10101","10101","10101","01010"),
 "X":("10001","10001","01010","00100","01010","10001","10001"),
 "Y":("10001","10001","01010","00100","00100","00100","00100"),
 "Z":("11111","00001","00010","00100","01000","10000","11111"),
 "0":("01110","10001","10011","10101","11001","10001","01110"),
 "1":("00100","01100","00100","00100","00100","00100","01110"),
 "2":("01110","10001","00001","00110","01000","10000","11111"),
 "3":("11110","00001","00001","01110","00001","00001","11110"),
 "4":("00010","00110","01010","10010","11111","00010","00010"),
 "5":("11111","10000","11110","00001","00001","10001","01110"),
 "6":("01110","10000","10000","11110","10001","10001","01110"),
 "7":("11111","00001","00010","00100","01000","01000","01000"),
 "8":("01110","10001","10001","01110","10001","10001","01110"),
 "9":("01110","10001","10001","01111","00001","00001","01110"),
 " ":("00000","00000","00000","00000","00000","00000","00000"),
 ":":("00000","00100","00100","00000","00100","00100","00000"),
 ".":("00000","00000","00000","00000","00000","00110","00110"),
 "_":("00000","00000","00000","00000","00000","00000","11111"),
 "-":("00000","00000","00000","01110","00000","00000","00000"),
 "/":("00001","00010","00010","00100","01000","01000","10000"),
 "=":("00000","00000","11111","00000","11111","00000","00000"),
 "%":("11001","11010","00010","00100","01000","01011","10011"),
 "(" :("00010","00100","01000","01000","01000","00100","00010"),
 ")" :("01000","00100","00010","00010","00010","00100","01000"),
 "?":("01110","10001","00001","00110","00100","00000","00100"),
 "+":("00000","00100","00100","11111","00100","00100","00000"),
 "#":("01010","11111","01010","01010","11111","01010","01010"),
 "[":("01110","01000","01000","01000","01000","01000","01110"),
 "]":("01110","00010","00010","00010","00010","00010","01110"),
}
C_BG = (255, 255, 255)
C_HEAD = (31, 58, 95)
C_GREEN = (46, 160, 67)
C_RED = (200, 60, 60)
C_GRAY = (150, 150, 150)
C_TEXT = (30, 30, 30)
C_BAR = (40, 110, 200)
C_AMBER = (210, 140, 30)
C_WHITE = (245, 245, 245)

W = 760
LINE_H = 24
HEADER_H = 40


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def atomic_write_bytes(path, data):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json_safe(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, type(default)) else default
    except Exception:
        return default


def ascii_safe(s):
    return str(s).encode("ascii", "replace").decode("ascii")


# ------------------------------------------------------------------ 面板数据
def collect_panel(contract, result):
    fields = []
    for f in contract.get("fields", []):
        name = str(f.get("name", "?"))
        fields.append({"name": name,
                       "required": bool(f.get("required", True)),
                       "filled": result.get(name) is not None})
    items, evmap = [], {}
    for f in contract.get("fields", []):
        v = result.get(str(f.get("name", "")))
        if isinstance(v, dict) and "evidence" in str(f.get("name", "")).lower():
            evmap = v
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            items = v
    rows = []
    for i, it in enumerate(items[:12]):
        iid = (it.get("item_id") or it.get("id") or it.get("question_id")
               or "item_%d" % (i + 1))
        diff = it.get("difficulty") or it.get("难度") or "?"
        ev = evmap.get(str(iid), it.get("evidence_anchors") or []) \
            if isinstance(evmap, dict) else (it.get("evidence_anchors") or [])
        rows.append({"id": str(iid), "diff": str(diff),
                     "ev": len(ev) if isinstance(ev, list) else 0})
    return fields, rows


def build_lines(contract, result):
    """生成两种渲染器共用的行描述：文本行 / 字段行 / 条形行。"""
    fields, rows = collect_panel(contract, result)
    req = [f for f in fields if f["required"]]
    filled_req = [f for f in req if f["filled"]]
    lines = [{"kind": "text",
              "s": "CASE: %s  STATUS: %s"
                  % (ascii_safe(contract.get("case_id", "?")),
                     ascii_safe(result.get("status", "?")))},
             {"kind": "text",
              "s": "FIELDS: REQUIRED FILLED %d/%d"
                  % (len(filled_req), len(req))}]
    for f in fields:
        mark = "FILLED" if f["filled"] else (
            "NULL(REQUIRED)" if f["required"] else "NULL(OPTIONAL)")
        lines.append({"kind": "field", "filled": f["filled"],
                      "required": f["required"],
                      "s": "%s : %s" % (ascii_safe(f["name"]), mark)})
    if rows:
        lines.append({"kind": "text", "s": "ITEMS (EVIDENCE ANCHOR COUNT):"})
        for r in rows:
            lines.append({"kind": "bar", "ev": r["ev"],
                          "s": "%s DIFF=%s EV=%d"
                              % (ascii_safe(r["id"]),
                                 ascii_safe(r["diff"]).upper(), r["ev"])})
    else:
        lines.append({"kind": "text", "s": "ITEMS: NONE"})
    return lines


# ------------------------------------------------------------------ SVG 渲染
def render_svg(lines):
    h = HEADER_H + LINE_H * len(lines) + 20
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d">' % (W, h, W, h),
        '<rect x="0" y="0" width="%d" height="%d" fill="rgb%s"/>'
        % (W, h, C_BG),
        '<rect x="0" y="0" width="%d" height="%d" fill="rgb%s"/>'
        % (W, HEADER_H, C_HEAD),
        '<text x="12" y="26" font-family="monospace" font-size="16" '
        'fill="rgb%s">CONTRACT-RENDER-GATE PREVIEW</text>' % (C_WHITE,),
    ]
    y = HEADER_H + 8
    for ln in lines:
        ty = y + 16
        if ln["kind"] == "field":
            color = C_GREEN if ln["filled"] else (
                C_RED if ln["required"] else C_GRAY)
            parts.append('<rect x="12" y="%d" width="14" height="14" '
                         'fill="rgb%s"/>' % (y + 3, color))
            parts.append('<text x="34" y="%d" font-family="monospace" '
                         'font-size="14" fill="rgb%s">%s</text>'
                         % (ty, C_TEXT, escape(ln["s"])))
        elif ln["kind"] == "bar":
            parts.append('<text x="34" y="%d" font-family="monospace" '
                         'font-size="14" fill="rgb%s">%s</text>'
                         % (ty, C_TEXT, escape(ln["s"])))
            bw = min(int(ln["ev"]) * 30, 300)
            parts.append('<rect x="430" y="%d" width="%d" height="12" '
                         'fill="rgb%s"/>' % (y + 5, bw, C_BAR))
        else:
            parts.append('<text x="12" y="%d" font-family="monospace" '
                         'font-size="14" fill="rgb%s">%s</text>'
                         % (ty, C_AMBER if ln["s"].startswith(("CASE", "FIELDS"))
                            else C_TEXT, escape(ln["s"])))
        y += LINE_H
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    ET.fromstring(svg)  # well-formed 校验，失败即抛异常（视为内部缺陷）
    return svg


# ------------------------------------------------------------------ PNG 渲染
def draw_rect(cv, x, y, w, h, color):
    for yy in range(max(0, y), min(len(cv), y + h)):
        row = cv[yy]
        for xx in range(max(0, x), min(len(row), x + w)):
            row[xx] = list(color)


def draw_text(cv, x, y, text, color, scale=2):
    cx = x
    for ch in text:
        g = FONT.get(ch, FONT.get("?"))
        for r, rowbits in enumerate(g):
            for c, bit in enumerate(rowbits):
                if bit == "1":
                    draw_rect(cv, cx + c * scale, y + r * scale, scale, scale,
                              color)
        cx += 6 * scale


def render_png(lines):
    h = HEADER_H + LINE_H * len(lines) + 20
    cv = [[list(C_BG) for _ in range(W)] for _ in range(h)]
    draw_rect(cv, 0, 0, W, HEADER_H, C_HEAD)
    draw_text(cv, 12, 12, "CONTRACT-RENDER-GATE PREVIEW", C_WHITE)
    y = HEADER_H + 8
    for ln in lines:
        ty = y + 4
        if ln["kind"] == "field":
            color = C_GREEN if ln["filled"] else (
                C_RED if ln["required"] else C_GRAY)
            draw_rect(cv, 12, y + 4, 14, 14, color)
            draw_text(cv, 34, ty, ascii_safe(ln["s"]).upper(), C_TEXT)
        elif ln["kind"] == "bar":
            draw_text(cv, 34, ty, ascii_safe(ln["s"]).upper(), C_TEXT)
            bw = min(int(ln["ev"]) * 30, 300)
            if bw > 0:
                draw_rect(cv, 430, y + 5, bw, 12, C_BAR)
        else:
            color = C_AMBER if ln["s"].startswith(("CASE", "FIELDS")) else C_TEXT
            draw_text(cv, 12, ty, ascii_safe(ln["s"]).upper(), color)
        y += LINE_H
    return encode_png(W, h, cv)


def encode_png(w, h, cv):
    """stdlib 手写 PNG 编码器：8bit RGB、filter 0、zlib 压缩。"""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(b for px in row for b in px) for row in cv)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# -------------------------------------------------------------- 外部渲染器
def png_dims(path):
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
    except Exception:
        pass
    return None


def try_external(svg_path, out_png):
    """探测顺序 rsvg-convert -> inkscape -> magick，返回所用工具名或 None。"""
    for tool in ("rsvg-convert", "inkscape", "magick"):
        exe = shutil.which(tool)
        if not exe:
            continue
        try:
            if tool == "rsvg-convert":
                cmd = [exe, "-o", out_png, svg_path]
            elif tool == "inkscape":
                cmd = [exe, svg_path, "-o", out_png]
            else:
                cmd = [exe, svg_path, out_png]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            if os.path.isfile(out_png) and os.path.getsize(out_png) > 0:
                return tool
        except Exception:
            continue
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="渲染 result.json 状态面板：SVG + 内置 PNG (+ 可选外部高清 PNG)")
    ap.add_argument("--contract", default="/app/work/contract.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out-dir", default="/app/output")
    args = ap.parse_args(argv)

    contract = load_json_safe(args.contract,
                              {"case_id": "UNKNOWN_CASE_ID", "fields": []})
    result = load_json_safe(args.result, {"case_id": "UNKNOWN_CASE_ID"})
    lines = build_lines(contract, result)

    svg_path = os.path.join(args.out_dir, "preview.svg")
    png_path = os.path.join(args.out_dir, "preview.png")
    hd_path = os.path.join(args.out_dir, "preview_hd.png")
    rec_path = os.path.join(args.out_dir, "preview_record.json")

    svg = render_svg(lines)
    atomic_write_bytes(svg_path, svg.encode("utf-8"))
    png = render_png(lines)
    atomic_write_bytes(png_path, png)

    renderer = try_external(svg_path, hd_path)
    hd_dims = png_dims(hd_path) if renderer else None
    if renderer:
        note = ("外部渲染器 %s 生成 preview_hd.png；内置 PNG %dx%d，"
                "高清版 %s" % (renderer, W, HEADER_H + LINE_H * len(lines) + 20,
                               "%dx%d" % hd_dims if hd_dims else "尺寸未知"))
    else:
        note = "外部渲染器缺失，使用内置 PNG 编码器（stdlib zlib+struct）"
    rec = {
        "case_id": contract.get("case_id", "UNKNOWN_CASE_ID"),
        "height": HEADER_H + LINE_H * len(lines) + 20,
        "png_sha256": sha256_bytes(png),
        "preview_hd_png": os.path.abspath(hd_path) if renderer else None,
        "preview_note": note,
        "preview_png": os.path.abspath(png_path),
        "preview_svg": os.path.abspath(svg_path),
        "renderer": renderer or "internal",
        "svg_sha256": sha256_bytes(svg.encode("utf-8")),
        "width": W,
    }
    if renderer:
        rec["hd_sha256"] = sha256_file(hd_path)
        rec["hd_dims"] = list(hd_dims) if hd_dims else None
    atomic_write_bytes(rec_path, (json.dumps(rec, ensure_ascii=False,
                                             indent=2, sort_keys=True)
                                  + "\n").encode("utf-8"))
    print("render_preview: svg=%s png=%s renderer=%s"
          % (svg_path, png_path, rec["renderer"]))
    print("  sha256 svg=%s" % rec["svg_sha256"])
    print("  sha256 png=%s" % rec["png_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
