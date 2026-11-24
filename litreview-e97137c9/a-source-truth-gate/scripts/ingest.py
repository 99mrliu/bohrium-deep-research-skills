#!/usr/bin/env python3
"""ingest.py — 防御式输入解析与语料锚点化（bundle A: source-truth-gate）。

职责：
  1. 防御式读取 case.json / task.md（不假设字段名，按候选键递归探测）。
  2. 发现文献材料（case 指定优先，否则扫描输入目录）。
  3. 逐文档抽取文本（pdftotext -layout → 纯文本回退），分页锚点化，SHA-256 留痕。
  4. 分级（fulltext / abstract_only / failed / metadata_only）与近重复检测。
产物（work 目录下）：case_profile.json, docs.jsonl, pages/<doc_id>.jsonl, dup_groups.json
仅用标准库；pdftotext 缺失时自动回退并记录。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

CASE_ID_KEYS = ["case_id", "caseId", "id"]
RQ_KEYS = ["research_question", "question", "topic", "title", "objective", "rq"]
DOC_KEYS = ["documents", "papers", "references", "files", "literature", "corpus", "materials"]
CONTRACT_KEYS = ["output_contract", "contract", "output_fields", "required_fields"]
PATH_KEYS = ["path", "file", "pdf", "filepath", "file_path", "local_path"]
MATERIAL_EXTS = [".pdf", ".txt", ".md", ".html"]
PSEUDO_PAGE_CHARS = 2500
FULLTEXT_MIN_WORDS = 300


def find_key(obj, keys):
    """递归在嵌套 dict/list 中查找任一候选键，返回第一个命中的值。"""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] not in (None, "", []):
                return obj[k]
        for v in obj.values():
            hit = find_key(v, keys)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = find_key(item, keys)
            if hit is not None:
                return hit
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def strip_html(text):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text)


def pseudo_pages(text):
    """把无分页概念的纯文本按段落边界切成 ~PSEUDO_PAGE_CHARS 的伪页。"""
    paras = re.split(r"\n\s*\n", text)
    pages, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > PSEUDO_PAGE_CHARS:
            pages.append(buf)
            buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf.strip():
        pages.append(buf)
    return pages or [""]


def extract_pdf(path):
    """返回 (pages, method)。优先 pdftotext -layout；失败回退空。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext_missing"
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            out = tmp.name
        subprocess.run([exe, "-layout", path, out], check=True,
                       capture_output=True, timeout=120)
        text = read_text_file(out)
        os.unlink(out)
        pages = text.split("\f")
        pages = [p for p in pages if p.strip()]
        return (pages or None), "pdftotext"
    except Exception as exc:  # noqa: BLE001
        return None, f"pdftotext_failed:{exc.__class__.__name__}"


def extract_pages(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext in (".txt", ".md", ".html"):
        text = read_text_file(path)
        if ext == ".html":
            text = strip_html(text)
        return pseudo_pages(text), f"raw{ext}"
    return None, f"unsupported_ext:{ext}"


def word_count(text):
    latin = re.findall(r"[A-Za-z0-9]+", text)
    cjk = re.findall(r"[一-鿿]", text)
    return len(latin) + len(cjk)


def norm_title(text):
    """取首个非空行归一化作为标题候选。"""
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 8:
            return re.sub(r"\s+", " ", re.sub(r"[^\w一-鿿 ]", "", line.lower())).strip()
    return ""


def shingle_set(text, n=8):
    toks = re.findall(r"[a-z0-9一-鿿]+", text.lower())
    return {"".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def discover_documents(case, input_dir):
    """返回 [(ref, provided_meta)]，ref 为本地路径或 URL。"""
    docs = find_key(case, DOC_KEYS) or []
    out = []
    if isinstance(docs, (str, dict)):
        docs = [docs]
    for i, item in enumerate(docs):
        meta = {}
        ref = None
        if isinstance(item, str):
            ref = item
        elif isinstance(item, dict):
            meta = {k: v for k, v in item.items()
                    if isinstance(v, (str, int, float))}
            for k in PATH_KEYS:
                if k in item:
                    ref = str(item[k])
                    break
            if ref is None:
                for k in ("url", "doi", "link"):
                    if k in item:
                        ref = str(item[k])
                        break
        if ref:
            out.append((ref, meta))
    if not out and input_dir and os.path.isdir(input_dir):
        for ext in MATERIAL_EXTS:
            for name in sorted(os.listdir(input_dir)):
                if name.lower().endswith(ext):
                    out.append((os.path.join(input_dir, name), {}))
    return out


def resolve_ref(ref, input_dir):
    """把 case 中的引用解析为本地路径；URL 返回 None。"""
    if re.match(r"^https?://", ref):
        return None
    if os.path.isabs(ref) and os.path.exists(ref):
        return ref
    for base in (input_dir or "", os.getcwd()):
        cand = os.path.join(base, ref)
        if os.path.exists(cand):
            return cand
    return None


def build_corpus(case_path, task_path, input_dir, work):
    os.makedirs(work, exist_ok=True)
    pages_dir = os.path.join(work, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    case = {}
    if case_path and os.path.exists(case_path):
        case = json.loads(read_text_file(case_path))
    task_text = read_text_file(task_path) if task_path and os.path.exists(task_path) else ""

    case_id = find_key(case, CASE_ID_KEYS) or \
        (os.path.splitext(os.path.basename(case_path))[0] if case_path else "unknown_case")
    rq = find_key(case, RQ_KEYS) or ""
    if not rq and task_text:
        rq = task_text.strip().splitlines()[0][:300]
    contract = find_key(case, CONTRACT_KEYS)

    profile = {
        "case_id": str(case_id),
        "research_question": str(rq),
        "output_contract": contract,
        "task_md_excerpt": task_text[:2000],
        "field_probing": {
            "case_id_from": "case" if find_key(case, CASE_ID_KEYS) else "filename_fallback",
            "contract_found": contract is not None,
        },
    }

    docs, shingles = [], {}
    for i, (ref, meta) in enumerate(discover_documents(case, input_dir), 1):
        doc_id = f"D{i}"
        local = resolve_ref(ref, input_dir)
        rec = {"doc_id": doc_id, "ref": ref, "provided_metadata": meta}
        if local is None:
            rec.update(tier="metadata_only", words=0, pages=0,
                       extract_method="url_only", sha256=None,
                       title_hint=str(meta.get("title", ref))[:200])
            docs.append(rec)
            continue
        rec["path"] = local
        rec["sha256"] = sha256_file(local)
        pages, method = extract_pages(local)
        rec["extract_method"] = method
        if not pages:
            rec.update(tier="failed", words=0, pages=0)
            docs.append(rec)
            continue
        full_text = "\n\n".join(pages)
        wc = word_count(full_text)
        rec.update(words=wc, pages=len(pages),
                   tier="fulltext" if wc >= FULLTEXT_MIN_WORDS else "abstract_only",
                   title_hint=norm_title(pages[0])[:200])
        with open(os.path.join(pages_dir, f"{doc_id}.jsonl"), "w", encoding="utf-8") as f:
            for n, ptext in enumerate(pages, 1):
                f.write(json.dumps({"page": n, "text": ptext}, ensure_ascii=False) + "\n")
        shingles[doc_id] = shingle_set(full_text)
        docs.append(rec)

    # 近重复分组：标题相同或 shingle Jaccard ≥ 0.6
    groups, assigned = [], set()
    usable = [d for d in docs if d.get("tier") in ("fulltext", "abstract_only")]
    for i, a in enumerate(usable):
        if a["doc_id"] in assigned:
            continue
        grp = [a["doc_id"]]
        for b in usable[i + 1:]:
            if b["doc_id"] in assigned:
                continue
            same_title = a.get("title_hint") and a["title_hint"] == b.get("title_hint")
            sim = jaccard(shingles.get(a["doc_id"], set()), shingles.get(b["doc_id"], set()))
            if same_title or sim >= 0.6:
                grp.append(b["doc_id"])
                assigned.add(b["doc_id"])
        if len(grp) > 1:
            groups.append({"members": grp})
        assigned.add(a["doc_id"])

    with open(os.path.join(work, "case_profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    with open(os.path.join(work, "docs.jsonl"), "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(os.path.join(work, "dup_groups.json"), "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    return profile, docs, groups


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", default=None)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    profile, docs, groups = build_corpus(args.case, args.task, args.input_dir, args.work)
    tiers = {}
    for d in docs:
        tiers[d["tier"]] = tiers.get(d["tier"], 0) + 1
    print(json.dumps({"case_id": profile["case_id"], "docs": len(docs),
                      "tiers": tiers, "dup_groups": len(groups)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
