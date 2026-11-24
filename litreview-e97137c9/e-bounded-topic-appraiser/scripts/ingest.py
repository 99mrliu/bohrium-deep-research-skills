#!/usr/bin/env python3
"""ingest.py — 防御式输入解析与语料锚点化（bundle E: bounded-topic-appraiser）。

自行实现的精简版解析器（不 import 任何其他 bundle）。职责：
  1. 防御式读取 case.json / task.md（不假设字段名，按候选键递归探测）。
  2. 发现文献材料（case 指定优先，否则扫描输入目录）。
  3. 逐文档抽取文本（pdftotext -layout → 纯文本回退），分页锚点化，SHA-256 留痕。
  4. 分级（fulltext / abstract_only / failed / metadata_only）。
  5. 递归探测候选选题（candidate_topics/proposals/options/topics）与
     约束（constraints/budget/limitations/requirements），写入 work/case_extras.json。
产物（work 目录下）：case_profile.json, docs.jsonl, pages/<doc_id>.jsonl,
case_extras.json, uncertainties.json（解析阶段的降级说明）。
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
TOPIC_KEYS = ["candidate_topics", "proposals", "options", "topics"]
CONSTRAINT_KEYS = ["constraints", "budget", "limitations", "requirements"]
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


def find_all(obj, keys, path="$"):
    """递归收集所有命中候选键的 (路径, 值)，用于候选选题/约束的多处出现。"""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and v not in (None, "", []):
                hits.append((f"{path}.{k}", v))
            hits += find_all(v, keys, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits += find_all(item, keys, f"{path}[{i}]")
    return hits


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
        pages = [p for p in text.split("\f") if p.strip()]
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


def discover_documents(case, input_dir):
    docs = find_key(case, DOC_KEYS) or []
    out = []
    if isinstance(docs, (str, dict)):
        docs = [docs]
    for item in docs:
        meta, ref = {}, None
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
    if re.match(r"^https?://", ref):
        return None
    if os.path.isabs(ref) and os.path.exists(ref):
        return ref
    for base in (input_dir or "", os.getcwd()):
        cand = os.path.join(base, ref)
        if os.path.exists(cand):
            return cand
    return None


def _flatten_items(value):
    """把候选选题/约束的任意嵌套值拍平为字符串清单。"""
    out = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k in ("title", "name", "topic", "proposal", "text", "description", "value"):
            if isinstance(value.get(k), str):
                out.append(value[k])
                break
        else:
            out.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            out += _flatten_items(item)
    elif value is not None:
        out.append(str(value))
    return out


def extract_case_extras(case):
    """递归探测候选选题与约束；保留原始命中路径以便审计。"""
    topic_hits = find_all(case, TOPIC_KEYS)
    cons_hits = find_all(case, CONSTRAINT_KEYS)
    topics, constraints = [], []
    for _, v in topic_hits:
        topics += _flatten_items(v)
    for _, v in cons_hits:
        constraints += _flatten_items(v)
    # 去重保序
    topics = list(dict.fromkeys(t.strip() for t in topics if t and t.strip()))
    constraints = list(dict.fromkeys(c.strip() for c in constraints if c and c.strip()))
    return {
        "candidate_topics": topics,
        "constraints": constraints,
        "probing": {
            "topic_hits": [p for p, _ in topic_hits],
            "constraint_hits": [p for p, _ in cons_hits],
            "topic_keys_tried": TOPIC_KEYS,
            "constraint_keys_tried": CONSTRAINT_KEYS,
        },
    }


def build_corpus(case_path, task_path, input_dir, work):
    os.makedirs(work, exist_ok=True)
    pages_dir = os.path.join(work, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    uncertainties = []

    case = {}
    if case_path and os.path.exists(case_path):
        case = json.loads(read_text_file(case_path))
    task_text = read_text_file(task_path) if task_path and os.path.exists(task_path) else ""

    case_id = find_key(case, CASE_ID_KEYS)
    if case_id is None:
        case_id = os.path.splitext(os.path.basename(case_path))[0] if case_path else "unknown_case"
        uncertainties.append("case_id 未在 case.json 中命中候选键，已用文件名代替")
    rq = find_key(case, RQ_KEYS) or ""
    if not rq and task_text:
        rq = task_text.strip().splitlines()[0][:300]
    contract = find_key(case, CONTRACT_KEYS)
    if contract is None:
        uncertainties.append("output_contract 未命中候选键，result.json 将按默认结构交付")

    extras = extract_case_extras(case)
    if not extras["candidate_topics"]:
        uncertainties.append("case.json 未提供候选选题；appraise 阶段将回退读取模型产物 work/topics.md")
    if not extras["constraints"]:
        uncertainties.append("case.json 未提供约束；constraint_fit 将记 null 并按权重归一化")

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

    docs = []
    for i, (ref, meta) in enumerate(discover_documents(case, input_dir), 1):
        doc_id = f"D{i}"
        local = resolve_ref(ref, input_dir)
        rec = {"doc_id": doc_id, "ref": ref, "provided_metadata": meta}
        if local is None:
            rec.update(tier="metadata_only", words=0, pages=0,
                       extract_method="url_only", sha256=None,
                       title_hint=str(meta.get("title", ref))[:200])
            docs.append(rec)
            uncertainties.append(f"{doc_id}：仅有 URL/题录无本地全文，记 metadata_only，不伪造全文")
            continue
        rec["path"] = local
        rec["sha256"] = sha256_file(local)
        pages, method = extract_pages(local)
        rec["extract_method"] = method
        if method == "pdftotext_missing":
            uncertainties.append(f"{doc_id}：pdftotext 不可用，PDF 无法解析")
        if not pages:
            rec.update(tier="failed", words=0, pages=0)
            docs.append(rec)
            uncertainties.append(f"{doc_id}：文本抽取失败（{method}），记 failed")
            continue
        full_text = "\n\n".join(pages)
        wc = word_count(full_text)
        tier = "fulltext" if wc >= FULLTEXT_MIN_WORDS else "abstract_only"
        if tier == "abstract_only":
            uncertainties.append(f"{doc_id}：不足 {FULLTEXT_MIN_WORDS} 词，按 abstract_only 降级使用")
        title_hint = ""
        for line in pages[0].splitlines():
            if len(line.strip()) >= 8:
                title_hint = re.sub(r"\s+", " ", line.strip())[:200]
                break
        rec.update(words=wc, pages=len(pages), tier=tier, title_hint=title_hint)
        with open(os.path.join(pages_dir, f"{doc_id}.jsonl"), "w", encoding="utf-8") as f:
            for n, ptext in enumerate(pages, 1):
                f.write(json.dumps({"page": n, "text": ptext}, ensure_ascii=False) + "\n")
        docs.append(rec)

    if not any(d["tier"] in ("fulltext", "abstract_only") for d in docs):
        uncertainties.append("零可用文献（全部 metadata_only/failed 或无材料），后续阶段将交付 status=blocked")

    with open(os.path.join(work, "case_profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    with open(os.path.join(work, "docs.jsonl"), "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(os.path.join(work, "case_extras.json"), "w", encoding="utf-8") as f:
        json.dump(extras, f, ensure_ascii=False, indent=2)
    with open(os.path.join(work, "uncertainties.json"), "w", encoding="utf-8") as f:
        json.dump(uncertainties, f, ensure_ascii=False, indent=2)
    return profile, docs, extras


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", default=None)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    profile, docs, extras = build_corpus(args.case, args.task, args.input_dir, args.work)
    tiers = {}
    for d in docs:
        tiers[d["tier"]] = tiers.get(d["tier"], 0) + 1
    print(json.dumps({"case_id": profile["case_id"], "docs": len(docs), "tiers": tiers,
                      "candidate_topics": len(extras["candidate_topics"]),
                      "constraints": len(extras["constraints"])}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
