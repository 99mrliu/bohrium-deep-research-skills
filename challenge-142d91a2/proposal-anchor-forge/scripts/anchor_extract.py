#!/usr/bin/env python3
"""anchor_extract.py -- 材料锚定抽取器（开题论断保真管线的第 1 环）。

把材料目录（评测时为 /input）下的全部材料抽成带稳定锚点的段落库：
  - case.json          解析为 JSON 后按顶层键逐条落成段落（derived 渲染，offsets 对渲染文本有效）；
  - task.md / .md / .txt / .tex / .markdown / .csv   直接按 UTF-8 文本读取；
  - .pdf               调用真实文件 pdftotext -layout 抽取，失败如实记 manifest，绝不猜测内容。

产物（OUT_DIR）：
  anchor_map.jsonl   每行 {"anchor","material","file","para","char_start","char_end","text"}
  manifest.json      抽取 QC 清单：逐材料段落数/字节数/乱码率/截断迹象，外加
                     unreadable（不可读文件）与 empty_files（空文件或全空白）两张名单。

设计红线：只搬运真实读到的字节；读不出来的材料进 manifest.unreadable，
由调用方在 result.json 的 uncertainty 中点名，禁止用模型印象补写。
"""
import argparse
import json
import os
import re
import subprocess
import sys

PLAIN_TEXT_EXT = {".md", ".txt", ".markdown", ".tex", ".csv"}
GARBLE_LIMIT = 0.01  # 乱码率阈值：非空白字符中替换符/控制符/私用区占比超过 1% 即标记
TAIL_WINDOW = 160    # 截断判定只看文末最后 160 字符
TAIL_CLOSED = re.compile(
    r"[.。!！?？:：;；)\]】》」』\"']\s*$|参考文献|references\s*$", re.IGNORECASE)


def measure_garble(text):
    """乱码率 = 可疑字符数 / 非空白字符数。

    可疑字符：U+FFFD 替换符、除 TAB 外的 C0 控制符、Unicode 私用区
    （BMP 私用区与两个增补私用平面）。只统计，不修改原文。
    """
    seen = 0
    dirty = 0
    for ch in text:
        if ch.isspace():
            continue
        seen += 1
        code = ord(ch)
        if (ch == "�" or (code < 32 and ch != "\t")
                or 0xE000 <= code <= 0xF8FF
                or 0xF0000 <= code <= 0xFFFFD
                or 0x100000 <= code <= 0x10FFFD):
            dirty += 1
    return (dirty / seen) if seen else 0.0


def paragraph_spans(text):
    """按空行切段，返回 [(char_start, paragraph)]；段内换行保留，首尾换行剥除。"""
    spans = []
    buf = []
    buf_start = None
    pos = 0

    def flush():
        nonlocal buf, buf_start
        if buf:
            raw = "".join(buf)
            lead = len(raw) - len(raw.lstrip("\n"))
            piece = raw.strip("\n")
            if piece.strip():
                spans.append((buf_start + lead, piece))
        buf = []
        buf_start = None

    for line in text.splitlines(keepends=True):
        if line.strip():
            if buf_start is None:
                buf_start = pos
            buf.append(line)
        else:
            flush()
        pos += len(line)
    flush()
    return spans


def render_case_json(raw):
    """case.json 渲染为「顶层键: JSON值」的段落文本；解析失败则退回原文。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, False
    if not isinstance(data, dict):
        return raw, False
    blocks = ["%s: %s" % (key, json.dumps(data[key], ensure_ascii=False, sort_keys=True))
              for key in sorted(data)]
    return "\n\n".join(blocks), True


def read_plain(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), None
    except UnicodeDecodeError as exc:
        return None, "UTF-8 解码失败: %s" % exc
    except OSError as exc:
        return None, "读取失败: %s" % exc


def read_pdf(path):
    try:
        proc = subprocess.run(["pdftotext", "-layout", path, "-"],
                              capture_output=True, timeout=180)
    except FileNotFoundError:
        return None, "pdftotext 未安装，PDF 无法解析"
    except subprocess.TimeoutExpired:
        return None, "pdftotext 执行超时（180s）"
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:200]
        return None, "pdftotext 退出码 %d: %s" % (proc.returncode, err)
    text = proc.stdout.decode("utf-8", "replace")
    if not text.strip():
        return None, "pdftotext 输出为空（扫描件或纯图片 PDF）"
    return text, None


def looks_truncated(text, n_paras):
    """截断迹象：段落数 >3 且文末 160 字符内没有任何收束标点/参考文献标记。"""
    if n_paras <= 3:
        return False
    tail = text[-TAIL_WINDOW:] if len(text) > TAIL_WINDOW else text
    return not TAIL_CLOSED.search(tail.strip())


def run(input_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    names = sorted(n for n in os.listdir(input_dir)
                   if os.path.isfile(os.path.join(input_dir, n)))

    records = []
    manifest = {"input_dir": os.path.abspath(input_dir),
                "garble_limit": GARBLE_LIMIT,
                "materials": [], "unreadable": [], "empty_files": [],
                "totals": {}}
    mid = 0
    for name in names:
        ext = os.path.splitext(name)[1].lower()
        if ext not in PLAIN_TEXT_EXT and ext not in {".pdf", ".json"}:
            continue  # 非材料文件（图片等）跳过并在 totals 里计数
        mid += 1
        material = "M%d" % mid
        path = os.path.join(input_dir, name)
        size = os.path.getsize(path)
        if size == 0:
            manifest["empty_files"].append(
                {"material": material, "file": name, "reason": "文件大小为 0 字节"})
            continue

        derived = False
        if ext == ".pdf":
            text, err = read_pdf(path)
        else:
            text, err = read_plain(path)
            if err is None and ext == ".json":
                text, derived = render_case_json(text)
        if err is not None or text is None:
            manifest["unreadable"].append(
                {"material": material, "file": name, "reason": err})
            continue
        if not text.strip():
            manifest["empty_files"].append(
                {"material": material, "file": name, "reason": "全文仅含空白字符"})
            continue

        paras = paragraph_spans(text)
        garble = measure_garble(text)
        entry = {"material": material, "file": name, "ext": ext,
                 "bytes": size, "paragraphs": len(paras),
                 "derived_rendering": derived,
                 "garble_ratio": round(garble, 4),
                 "garble_suspect": garble > GARBLE_LIMIT,
                 "truncation_suspect": looks_truncated(text, len(paras))}
        manifest["materials"].append(entry)
        for idx, (start, piece) in enumerate(paras, start=1):
            records.append({"anchor": "%s-P%03d" % (material, idx),
                            "material": material, "file": name, "para": idx,
                            "char_start": start,
                            "char_end": start + len(piece),
                            "text": piece})

    manifest["totals"] = {"materials": len(manifest["materials"]),
                          "paragraphs": len(records),
                          "unreadable": len(manifest["unreadable"]),
                          "empty_files": len(manifest["empty_files"])}
    with open(os.path.join(out_dir, "anchor_map.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print(json.dumps(manifest["totals"], ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input_dir", help="材料目录（评测时为 /input）")
    ap.add_argument("out_dir", help="锚点库与 QC 清单输出目录（如 /app/work/anchors）")
    args = ap.parse_args()
    if not os.path.isdir(args.input_dir):
        sys.exit("input_dir 不存在: %s" % args.input_dir)
    return run(args.input_dir, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
