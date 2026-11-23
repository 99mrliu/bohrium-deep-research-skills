#!/usr/bin/env python3
"""为源材料建立带逐字找回映射的确定性锚点索引（仅标准库）。"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
GUIDE = "请人工粘贴该文件逐页或逐段文本为 UTF-8 txt/md，再重新建立索引；不要猜测缺失原文。"


def atomic_json(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".source-index-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def normalize_with_map(raw):
    """返回 NFKC/连字/断词/空白归一化串及每个字符对应的原串偏移。"""
    out, offsets = [], []
    i = 0

    def emit(char, offset):
        for piece in unicodedata.normalize("NFKC", LIGATURES.get(char, char)):
            if piece.isspace():
                if out and out[-1] != " ":
                    out.append(" ")
                    offsets.append(offset)
            else:
                out.append(piece)
                offsets.append(offset)

    while i < len(raw):
        char = raw[i]
        if char == "-" and i > 0 and raw[i - 1].isalnum():
            j = i + 1
            saw_newline = False
            while j < len(raw) and raw[j].isspace():
                saw_newline = saw_newline or raw[j] in "\r\n"
                j += 1
            if saw_newline and j < len(raw) and raw[j].isalnum():
                i = j
                continue
        emit(char, i)
        i += 1
    while out and out[-1] == " ":
        out.pop()
        offsets.pop()
    return "".join(out), offsets


def text_anchors(doc_id, text, kind):
    anchors = []
    if kind == "json":
        try:
            value = json.loads(text)
            records = value if isinstance(value, list) else value.get("records", []) if isinstance(value, dict) and isinstance(value.get("records"), list) else None
            if records is None:
                records = [{"key": key, "value": value[key]} for key in sorted(value)] if isinstance(value, dict) else [value]
            for number, record in enumerate(records, 1):
                anchors.append((doc_id + ".record" + str(number), json.dumps(record, ensure_ascii=False, sort_keys=True)))
        except Exception as exc:
            return [], "JSON 畸形，无法按记录编号：" + str(exc)
    else:
        parts = re.split(r"(?:\r?\n){2,}", text)
        for number, part in enumerate(parts, 1):
            if part.strip():
                anchors.append((doc_id + ".para" + str(number), part))
    return anchors, ""


def pdf_anchors(doc_id, path):
    pdftotext, pdfinfo = shutil.which("pdftotext"), shutil.which("pdfinfo")
    notes, pages = [], []
    if not pdftotext:
        return [], True, ["未找到 pdftotext，PDF 未抽取。", GUIDE]
    page_count = None
    if pdfinfo:
        proc = subprocess.run([pdfinfo, path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
        match = re.search(r"^Pages:\s+(\d+)", proc.stdout, re.M)
        if proc.returncode == 0 and match:
            page_count = int(match.group(1))
        else:
            notes.append("pdfinfo 失败：" + proc.stderr.strip()[:300])
    else:
        notes.append("未找到 pdfinfo，改用整篇 pdftotext 并以换页符分页。")
    try:
        if page_count is not None:
            for page in range(1, page_count + 1):
                proc = subprocess.run([pdftotext, "-layout", "-f", str(page), "-l", str(page), path, "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
                if proc.returncode != 0:
                    return [], True, notes + ["pdftotext 第 %d 页失败：%s" % (page, proc.stderr.strip()[:300]), GUIDE]
                pages.append((doc_id + ".p" + str(page), proc.stdout.replace("\f", "")))
        else:
            proc = subprocess.run([pdftotext, "-layout", path, "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
            if proc.returncode != 0:
                message = proc.stderr.strip()[:300]
                if re.search(r"encrypt|password", message, re.I):
                    message = "PDF 可能加密或需要口令：" + message
                return [], True, notes + [message, GUIDE]
            chunks = proc.stdout.split("\f")
            if chunks and not chunks[-1].strip():
                chunks.pop()
            pages = [(doc_id + ".p" + str(i), chunk) for i, chunk in enumerate(chunks, 1)]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return [], True, notes + ["PDF 抽取异常：" + str(exc), GUIDE]
    anchors = []
    for anchor_id, raw in pages:
        anchors.append((anchor_id, raw))
        if not raw.strip():
            notes.append(anchor_id + " 整页抽取为空，可能为扫描页或抽取缺陷。")
    return anchors, any(not raw.strip() for _, raw in pages), notes + ([GUIDE] if any(not raw.strip() for _, raw in pages) else [])


def make_anchor(anchor_id, raw):
    normalized, offsets = normalize_with_map(raw)
    return {"anchor_id": anchor_id, "raw_text": raw, "normalized_text": normalized, "offset_map": offsets}


def build(input_dir, includes):
    documents, global_notes = [], []
    try:
        names = sorted(os.listdir(input_dir))
    except OSError as exc:
        return {"documents": [], "degraded": True, "notes": ["输入目录不可读：" + str(exc), GUIDE]}
    if includes:
        names = [name for name in includes if name in names]
    names = [name for name in names if name not in ("case.json", "task.md") and os.path.splitext(name)[1].lower() in (".pdf", ".txt", ".md", ".json")]
    for doc_number, name in enumerate(names, 1):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        doc_id, notes, degraded = "doc" + str(doc_number), [], False
        try:
            with open(path, "rb") as handle:
                payload = handle.read()
            digest, size = hashlib.sha256(payload).hexdigest(), len(payload)
            if name.lower().endswith(".pdf"):
                pairs, degraded, pdf_notes = pdf_anchors(doc_id, path)
                notes.extend(pdf_notes)
            else:
                try:
                    text = payload.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    text, degraded = payload.decode("utf-8", errors="replace"), True
                    notes.append("UTF-8 解码缺陷，已替换非法字节：" + str(exc))
                pairs, error = text_anchors(doc_id, text, os.path.splitext(name)[1].lower()[1:])
                if error:
                    notes, degraded = notes + [error, GUIDE], True
            documents.append({"doc_id": doc_id, "file": name, "sha256": digest, "bytes": size, "degraded": degraded, "notes": notes, "anchors": [make_anchor(anchor_id, raw) for anchor_id, raw in pairs]})
        except Exception as exc:
            documents.append({"doc_id": doc_id, "file": name, "sha256": None, "bytes": None, "degraded": True, "notes": ["材料索引异常：" + str(exc), GUIDE], "anchors": []})
    if not documents:
        global_notes.append("未发现可索引材料。")
    return {"schema_version": "1.0", "degraded": any(doc["degraded"] for doc in documents) or not documents, "notes": global_notes, "documents": documents}


def main():
    parser = argparse.ArgumentParser(description="扫描 PDF/txt/md/json，输出稳定锚点、哈希和归一化偏移索引。")
    parser.add_argument("--input-dir", default="/input", help="材料目录，默认 /input")
    parser.add_argument("--output", default="/app/work/source_index.json", help="索引输出路径")
    parser.add_argument("--include", action="append", help="仅索引指定文件，可重复；默认扫描全部支持材料")
    args = parser.parse_args()
    result = build(args.input_dir, args.include)
    atomic_json(args.output, result)
    print("已索引 %d 个材料；degraded=%s；输出 %s" % (len(result["documents"]), result["degraded"], args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
