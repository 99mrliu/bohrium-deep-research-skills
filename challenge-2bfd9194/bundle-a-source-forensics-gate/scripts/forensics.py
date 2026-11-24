#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forensics.py — 入库前逐文件真实性取证引擎（仅 Python 标准库）。

核心主张：未经验证真实性的文件不得作为可信资料入库。

对每个文件给出 verdict：
  authentic        魔数与扩展名一致（或无期望），截断检查通过
  type_mismatch    扩展名与魔数签名不符（如 .pdf 实为文本、改名伪装）
  corrupt_suspect  签名匹配但结尾结构缺失（PDF 缺 %%EOF / ZIP 缺 EOCD /
                   PNG 缺 IEND / JPEG 缺 FF D9），疑似损坏或截断
  empty            零字节文件
  unreadable       无法读取（权限 / IO 错误），记录错误信息

用法：
  作为模块：from forensics import forensic_file, forensic_tree, stream_sha256
  命令行：  python3 forensics.py <root_dir>  → 打印 JSON 取证报告
"""
import hashlib
import json
import os
import sys
import unicodedata

# ---------------------------------------------------------------- 签名库
# (魔数前缀, 类型名)；按特异度从高到低排列，先匹配先生效。
SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"%PDF-", "pdf"),
    (b"PK\x03\x04", "zip"),            # docx/xlsx/pptx 同为 ZIP 容器
    (b"\x1f\x8b", "gzip"),
    (b"SQLite format 3\x00", "sqlite"),
    (b"\xd0\xcf\x11\xe0\xa6\xb1\x1a\xe1", "ole2"),  # 老 doc/xls/ppt
    (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
]

# 扩展名 → 可接受的真实类型集合。不在表中的扩展名不做 mismatch 判定。
EXT_EXPECT = {
    ".pdf": {"pdf"},
    ".png": {"png"},
    ".jpg": {"jpeg"}, ".jpeg": {"jpeg"},
    ".zip": {"zip"}, ".docx": {"zip"}, ".xlsx": {"zip"}, ".pptx": {"zip"},
    ".gz": {"gzip"}, ".gzip": {"gzip"},
    ".sqlite": {"sqlite"}, ".sqlite3": {"sqlite"}, ".db": {"sqlite"},
    ".doc": {"ole2"}, ".xls": {"ole2"}, ".ppt": {"ole2"},
    ".rar": {"rar"}, ".7z": {"7z"},
    ".txt": {"text", "xml"}, ".md": {"text", "xml"}, ".csv": {"text", "xml"},
    ".tsv": {"text", "xml"}, ".log": {"text"}, ".py": {"text"},
    ".json": {"text"}, ".jsonl": {"text"}, ".yaml": {"text"}, ".yml": {"text"},
    ".xml": {"xml", "text"}, ".html": {"text", "xml"}, ".htm": {"text", "xml"},
}

TEXT_TYPES = {"text", "xml"}

VERDICTS = ("authentic", "type_mismatch", "corrupt_suspect", "empty", "unreadable")

CHUNK = 64 * 1024                 # 流式哈希块大小 64KB
HEAD_LEN = 512                    # 魔数探测读取的头部字节数
TAIL_LEN = 64 * 1024              # 结尾结构检查读取的尾部字节数
PDF_TAIL_WINDOW = 1024            # PDF 规范：%%EOF 应在文件尾 1KB 内
ENC_PROBE_LIMIT = 1024 * 1024     # 文本编码探测最多读取 1MB


def stream_sha256(path, chunk=CHUNK, progress=None):
    """流式 SHA-256。>256MB 文件同样全量哈希；每块调用 progress(n) 回调
    （调用方可在回调里 yield / 心跳），避免一次性读入造成内存峰值。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
            if progress is not None:
                progress(len(buf))
    return h.hexdigest()


def magic_of(head):
    """按签名库识别头部魔数；无签名命中时回退 XML/文本判定。"""
    for magic, name in SIGNATURES:
        if head.startswith(magic):
            return name
    probe = head.lstrip()
    if probe.startswith(b"<?xml"):
        return "xml"
    if _looks_text(head):
        return "text"
    return "unknown_binary"


def _looks_text(data):
    if not data:
        return False
    if b"\x00" in data:
        return False
    for enc in ("utf-8", "gb18030"):
        try:
            data.decode(enc)
            return True
        except (UnicodeDecodeError, ValueError):
            continue
    return False


def probe_encoding(path):
    """文本编码探测：依次尝试 UTF-8(含 BOM) / GB18030。
    返回 dict(encoding, has_replacement, note)。"""
    with open(path, "rb") as f:
        raw = f.read(ENC_PROBE_LIMIT)
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
        if enc == "utf-8-sig":
            enc = "utf-8-bom" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        return {
            "encoding": enc,
            "has_replacement": "�" in text,
            "note": None,
        }
    return {"encoding": None, "has_replacement": None,
            "note": "utf-8/gb18030 均无法解码，疑似二进制"}


def _tail_check(ftype, path, size):
    """结尾结构启发式检查。返回 (ok, evidence)；无规则的类型返回 (True, None)。"""
    if ftype not in ("pdf", "zip", "png", "jpeg"):
        return True, None
    with open(path, "rb") as f:
        f.seek(max(0, size - TAIL_LEN))
        tail = f.read()
    if ftype == "pdf":
        window = tail[-PDF_TAIL_WINDOW:] if len(tail) >= PDF_TAIL_WINDOW else tail
        ok = b"%%EOF" in window
        expect = "尾部 1KB 内应含 %%EOF"
    elif ftype == "zip":
        ok = b"PK\x05\x06" in tail   # EOCD 记录
        expect = "尾部应含 EOCD 记录 PK\\x05\\x06"
    elif ftype == "png":
        ok = tail[-8:] == b"IEND\xaeB`\x82"
        expect = "结尾应为 IEND 块 (49 45 4E 44 AE 42 60 82)"
    else:  # jpeg
        ok = tail[-2:] == b"\xff\xd9"
        expect = "结尾应为 FF D9"
    evidence = {
        "check": "truncation",
        "expected": expect,
        "actual_tail_hex": tail[-16:].hex(" ") if tail else "",
        "passed": ok,
    }
    return ok, evidence


def forensic_file(path, rel=None):
    """对单个文件做完整取证，返回取证记录 dict。"""
    rec = {
        "path": rel if rel is not None else path,
        "size": None,
        "mtime": None,
        "sha256": None,
        "extension": "",
        "detected_type": None,
        "encoding": None,
        "verdict": None,
        "evidence": {},
    }
    try:
        st = os.stat(path)
        rec["size"] = st.st_size
        rec["mtime"] = st.st_mtime
    except OSError as exc:
        rec["verdict"] = "unreadable"
        rec["evidence"] = {"error": "stat failed: %s" % exc}
        return rec

    name = os.path.basename(path)
    rec["extension"] = os.path.splitext(name)[1].lower()

    if rec["size"] == 0:
        rec["verdict"] = "empty"
        rec["sha256"] = hashlib.sha256(b"").hexdigest()
        rec["evidence"] = {"size": 0}
        return rec

    try:
        with open(path, "rb") as f:
            head = f.read(HEAD_LEN)
        rec["sha256"] = stream_sha256(path)
    except (PermissionError, OSError) as exc:
        rec["verdict"] = "unreadable"
        rec["evidence"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
        return rec

    detected = magic_of(head)
    rec["detected_type"] = detected
    rec["evidence"]["head_hex"] = head[:16].hex(" ")

    expected = EXT_EXPECT.get(rec["extension"])
    if expected and detected not in expected:
        rec["verdict"] = "type_mismatch"
        rec["evidence"].update({
            "check": "signature_vs_extension",
            "extension": rec["extension"],
            "expected_types": sorted(expected),
            "detected_type": detected,
        })
        return rec

    ok, tail_ev = _tail_check(detected, path, rec["size"])
    if not ok:
        rec["verdict"] = "corrupt_suspect"
        rec["evidence"].update(tail_ev)
        return rec
    if tail_ev:
        rec["evidence"]["truncation"] = tail_ev

    if detected in TEXT_TYPES:
        enc = probe_encoding(path)
        rec["encoding"] = enc["encoding"]
        rec["evidence"]["encoding_probe"] = enc

    if expected is None:
        rec["evidence"]["note"] = "扩展名无签名期望，仅记录探测结果"
    rec["verdict"] = "authentic"
    return rec


def forensic_tree(root, paths=None):
    """对 root 下全部文件（或给定相对路径列表）取证。
    文件名比较使用 NFC 规范化，遍历顺序确定（排序）。"""
    if paths is None:
        paths = []
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                paths.append(rel)
    paths = sorted(paths, key=lambda p: unicodedata.normalize("NFC", p))
    records = []
    for rel in paths:
        records.append(forensic_file(os.path.join(root, rel), rel))
    counts = {v: 0 for v in VERDICTS}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "root": os.path.abspath(root),
        "file_count": len(records),
        "verdict_counts": counts,
        "records": records,
    }


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 forensics.py <root_dir>\n")
        return 2
    report = forensic_tree(argv[1])
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
