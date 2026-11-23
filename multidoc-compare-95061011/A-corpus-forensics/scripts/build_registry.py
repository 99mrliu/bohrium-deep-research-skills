#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_registry.py — 语料取证注册表构建器（corpus forensics registry builder）。

在任何多文档比较之前运行。对语料目录中的每篇文档：
  1. 提取文本（.md/.txt 直读；.jsonl 若自带 paragraph_id 则沿用；.pdf 调 pdftotext，
     工具缺失标记 tool_missing，绝不静默跳过）；
  2. 解析保真审计（复用同目录 parse_audit.py；若导入失败则用内置最小判据）；
  3. 计算规范化文本指纹 fingerprint = sha256(normalized_text)；
  4. 8-gram shingle Jaccard 检测 exact_duplicate / near_duplicate / probable_version_pair
     （阈值见 references/forensics-rules.md）；
  5. 按空行切分稳定段落，paragraph_id = <DOCID>-P<序号>，content_hash = sha256(规范化段落)[:12]。

输出（写入 --out 目录）：
  registry.json            每文档：doc_id/path/title_guess/fingerprint/parse_fidelity/
                           identity_verdict/段落数等
  <DOCID>.paragraphs.jsonl 每行 {"doc_id","paragraph_id","content_hash","text"}

只使用 Python 标准库，无网络访问；macOS / Linux 可运行。
退出码：0 正常；1 用法或 IO 错误。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    import parse_audit as _audit
except Exception:  # 独立拷贝运行时退化为内置最小审计
    _audit = None

TEXT_EXTS = {".md", ".txt"}
JSONL_EXTS = {".jsonl"}
PDF_EXTS = {".pdf"}
ALL_EXTS = TEXT_EXTS | JSONL_EXTS | PDF_EXTS

# ---- 取证阈值（与 references/forensics-rules.md 保持一致） ----
SHINGLE_N = 8
NEAR_DUP_JACCARD = 0.70      # shingle Jaccard >= 0.70 -> near_duplicate
VERSION_JACCARD = 0.20       # 0.20 <= J < 0.70 且标题相似 -> probable_version_pair
TITLE_SIM_JACCARD = 0.50     # 标题 token Jaccard >= 0.50 视为标题相似


# ---------- 文本规范化与指纹 ----------
def normalize_text(text):
    """NFKC + 小写 + 非字母数字(保留 CJK)归一为空格 + 折叠空白。"""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^0-9a-z一-鿿]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint(text):
    return sha256_hex(normalize_text(text))


def content_hash(text):
    return sha256_hex(normalize_text(text))[:12]


def word_tokens(text):
    return normalize_text(text).split()


def shingle_set(tokens, n=SHINGLE_N):
    if not tokens:
        return set()
    if len(tokens) < n:  # 极短文本退化为单一 shingle，保证可比较
        return {tuple(tokens)}
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return (inter / union) if union else 0.0


def title_similarity(t1, t2):
    a, b = set(word_tokens(t1)), set(word_tokens(t2))
    return jaccard(a, b)


# ---------- 文档读取 ----------
def sanitize_doc_id(stem, idx):
    doc_id = re.sub(r"[^0-9A-Za-z]+", "-", stem).strip("-")
    return doc_id if doc_id else "DOC-%03d" % idx


def title_guess(text, fallback):
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^#+\s*", "", s).strip()
        if s:
            return s[:120]
    return fallback


def split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def load_jsonl_paragraphs(path):
    """若 .jsonl 每行是含 paragraph_id 与 text/content 的对象，则沿用其段落结构；
    否则返回 None，调用方按普通纯文本处理。"""
    paras = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if isinstance(obj, dict) and "paragraph_id" in obj and ("text" in obj or "content" in obj):
                    paras.append((str(obj["paragraph_id"]),
                                  str(obj.get("text", obj.get("content", "")))))
                else:
                    return None
    except OSError:
        return None
    return paras or None


def extract_pdf_text(path):
    """返回 (text, audit_dict)。pdftotext 缺失 -> (None, {verdict: tool_missing})。"""
    if _audit is not None:
        res = _audit.audit_pdf(path, keep_text=True)
        text = res.pop("text", None)
        return text, res
    # 退化路径：自带最小实现
    if shutil.which("pdftotext") is None:
        return None, {"mode": "pdf", "verdict": "tool_missing",
                      "error": "pdftotext not found in PATH"}
    import subprocess
    try:
        r = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, timeout=120)
    except Exception as e:
        return None, {"mode": "pdf", "verdict": "failed", "error": str(e)}
    if r.returncode != 0:
        return None, {"mode": "pdf", "verdict": "failed", "error": (r.stderr or "")[:500]}
    text = r.stdout or ""
    verdict = "good" if len(text) >= 100 else "failed"
    return text, {"mode": "pdf", "verdict": verdict, "total_chars": len(text)}


def audit_plain_text(text):
    if _audit is not None:
        return _audit.audit_text(text)
    return {"mode": "text", "verdict": "good" if len(text) >= 100 else "failed",
            "total_chars": len(text)}


# ---------- 主流程 ----------
def build(corpus_dir, out_dir):
    corpus_dir = os.path.abspath(corpus_dir)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    files = []
    for dirpath, _dn, filenames in os.walk(corpus_dir):
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in ALL_EXTS:
                files.append(os.path.join(dirpath, name))
    files.sort()

    documents = []
    canonicals = []  # 已被接受为 unique 的文档，用于身份比对基准

    for idx, path in enumerate(files, 1):
        ext = os.path.splitext(path)[1].lower()
        stem = os.path.splitext(os.path.basename(path))[0]
        doc_id = sanitize_doc_id(stem, idx)
        rel_path = os.path.relpath(path, corpus_dir)

        text, audit = None, None
        jsonl_paras = None
        if ext in PDF_EXTS:
            text, audit = extract_pdf_text(path)
        else:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError as e:
                text, audit = None, {"mode": "text", "verdict": "failed", "error": str(e)}
            else:
                audit = audit_plain_text(text)
                if ext in JSONL_EXTS:
                    jsonl_paras = load_jsonl_paragraphs(path)

        parse_fidelity = (audit or {}).get("verdict", "failed")
        readable = text is not None and parse_fidelity not in ("failed", "tool_missing")
        title = title_guess(text, stem) if text else stem

        # ---- 段落切分与锚定 ----
        para_records = []
        if readable:
            if jsonl_paras:
                raw_paras = [(pid, t) for pid, t in jsonl_paras if t.strip()]
            else:
                raw_paras = [(None, p) for p in split_paragraphs(text)]
            for i, (given_pid, ptext) in enumerate(raw_paras, 1):
                pid = given_pid or ("%s-P%03d" % (doc_id, i))
                para_records.append({
                    "doc_id": doc_id,
                    "paragraph_id": pid,
                    "content_hash": content_hash(ptext),
                    "text": ptext,
                })

        paras_file = "%s.paragraphs.jsonl" % doc_id
        with open(os.path.join(out_dir, paras_file), "w", encoding="utf-8") as f:
            for rec in para_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # ---- 身份鉴定（只与已接受的 canonical 文档比较）----
        verdict, evidence = "unique", {}
        if readable:
            fp = fingerprint(text)
            shingles = shingle_set(word_tokens(text))
            best = None
            for canon in canonicals:
                if fp == canon["fingerprint"]:
                    best = (canon, 1.0, 1.0, "exact")
                    break
                j = jaccard(shingles, canon["shingles"])
                ts = title_similarity(title, canon["title_guess"])
                if best is None or j > best[1]:
                    best = (canon, j, ts, "sim")
            if best is not None:
                canon, j, ts, kind = best
                if kind == "exact":
                    verdict = "exact_duplicate"
                elif j >= NEAR_DUP_JACCARD:
                    verdict = "near_duplicate"
                elif j >= VERSION_JACCARD and ts >= TITLE_SIM_JACCARD:
                    verdict = "probable_version_pair"
                if verdict != "unique":
                    evidence = {
                        "related_to": canon["doc_id"],
                        "shingle_jaccard": round(j, 4),
                        "title_similarity": round(ts, 4),
                        "basis": ("fingerprint identical" if kind == "exact" else
                                  "shingle jaccard %.3f, title similarity %.3f" % (j, ts)),
                    }
            if verdict == "unique":
                canonicals.append({
                    "doc_id": doc_id, "fingerprint": fp, "shingles": shingles,
                    "title_guess": title,
                })
        else:
            # 不可读文档无法做身份鉴定，诚实标注
            verdict = "undetermined"
            evidence = {"basis": "document unreadable (parse_fidelity=%s); "
                                 "identity cannot be established" % parse_fidelity}

        documents.append({
            "doc_id": doc_id,
            "path": rel_path,
            "abs_path": path,
            "format": ext.lstrip("."),
            "title_guess": title,
            "fingerprint": fingerprint(text) if readable else None,
            "n_chars": len(text) if text else 0,
            "parse_fidelity": parse_fidelity,
            "parse_audit": audit,
            "identity_verdict": verdict,
            "identity_evidence": evidence,
            "is_canonical": verdict == "unique",
            "n_paragraphs": len(para_records),
            "paragraphs_file": paras_file,
        })
        print("[registry] %-12s parse=%-12s identity=%-22s paras=%d  %s"
              % (doc_id, parse_fidelity, verdict, len(para_records), rel_path),
              file=sys.stderr)

    registry = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_dir": corpus_dir,
        "tool_status": {"pdftotext": "available" if shutil.which("pdftotext") else "missing"},
        "thresholds": {
            "shingle_n": SHINGLE_N,
            "near_duplicate_jaccard": NEAR_DUP_JACCARD,
            "version_pair_jaccard": VERSION_JACCARD,
            "title_similarity_jaccard": TITLE_SIM_JACCARD,
        },
        "n_documents": len(documents),
        "documents": documents,
    }
    with open(os.path.join(out_dir, "registry.json"), "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("registry written to %s (%d documents)"
          % (os.path.join(out_dir, "registry.json"), len(documents)), file=sys.stderr)
    return registry


def main(argv=None):
    ap = argparse.ArgumentParser(description="构建语料取证注册表 registry.json + 段落锚定 jsonl")
    ap.add_argument("corpus_dir", help="语料目录（.md/.txt/.jsonl/.pdf）")
    ap.add_argument("--out", required=True, help="输出目录（registry.json 与 <DOCID>.paragraphs.jsonl）")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.corpus_dir):
        print("error: corpus_dir not found: %s" % args.corpus_dir, file=sys.stderr)
        return 1
    build(args.corpus_dir, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
