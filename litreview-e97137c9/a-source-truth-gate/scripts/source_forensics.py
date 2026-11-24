#!/usr/bin/env python3
"""source_forensics.py — 来源取证与身份核验（bundle A 签名脚本）。

对每篇已解析文献：
  1. 从第一页文本提取身份证据：标题候选、年份候选、DOI、arXiv id、作者行候选。
  2. 与 case 提供的元数据比对 → identity_status: confirmed | mismatch | no_metadata_provided。
  3. 版本与风险标记：preprint / journal / retracted_or_withdrawn / metadata_incomplete。
  4. 近重复分组裁定代表篇（优先 fulltext，其次词数多者），其余 duplicate_of。
  5. 信任分层 trust_tier：
       T1 可支撑 established：representative + fulltext + 无撤稿标记；
       T2 仅 suggestive：abstract_only 或 metadata 冲突待核；
       T3 不得作为实质论断来源：metadata_only / failed / 撤稿未说明。
产物：source_manifest.json, forensics_report.md
"""
import json
import os
import re
import sys

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
ARXIV_RE = re.compile(r"arXiv:\d{4}\.\d{4,5}(v\d+)?", re.I)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
RETRACT_RE = re.compile(r"\b(retracted|retraction|withdrawn|withdrawal)\b", re.I)
PREPRINT_RE = re.compile(r"\b(preprint|arxiv|biorxiv|medrxiv|submitted to|under review|working paper)\b", re.I)
JOURNAL_RE = re.compile(r"\b(journal|proceedings|conference|vol\.|volume|issue|doi)\b", re.I)


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def first_page_text(work, doc_id):
    rows = load_jsonl(os.path.join(work, "pages", f"{doc_id}.jsonl"))
    return rows[0]["text"] if rows else ""


def extract_identity(text):
    head = text[:3000]
    lines = [l.strip() for l in head.splitlines() if l.strip()]
    title_cand = lines[0][:250] if lines else ""
    doi = DOI_RE.search(head)
    arxiv = ARXIV_RE.search(head)
    years = YEAR_RE.findall(head)
    year = None
    for y in years:
        y = int(y)
        if 1990 <= y <= 2030:
            year = y
            break
    author_cand = ""
    for l in lines[1:4]:
        if re.search(r"[A-Z][a-z]+(,| and | [A-Z]\.)", l) and len(l) < 200:
            author_cand = l
            break
    return {
        "title_candidate": title_cand,
        "year_candidate": year,
        "doi": doi.group(0).rstrip(".") if doi else None,
        "arxiv": arxiv.group(0) if arxiv else None,
        "author_line_candidate": author_cand,
    }


def token_overlap(a, b):
    ta = set(re.findall(r"[a-z0-9一-鿿]+", (a or "").lower()))
    tb = set(re.findall(r"[a-z0-9一-鿿]+", (b or "").lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def compare_metadata(identity, meta):
    if not meta:
        return "no_metadata_provided", []
    notes = []
    ok = True
    pt = str(meta.get("title", ""))
    if pt and identity["title_candidate"]:
        ov = token_overlap(pt, identity["title_candidate"])
        if ov < 0.5:
            ok = False
            notes.append(f"title_overlap={ov:.2f}<0.5")
    py = meta.get("year")
    if py and identity["year_candidate"] and int(py) != int(identity["year_candidate"]):
        ok = False
        notes.append(f"year {py}!={identity['year_candidate']}")
    pd_ = str(meta.get("doi", ""))
    if pd_ and identity["doi"] and pd_.lower() != identity["doi"].lower():
        ok = False
        notes.append("doi_mismatch")
    return ("confirmed" if ok else "mismatch"), notes


def risk_flags(text):
    flags = []
    head = text[:4000]
    if RETRACT_RE.search(head):
        flags.append("retracted_or_withdrawn_marker")
    if PREPRINT_RE.search(head):
        flags.append("preprint_marker")
    elif JOURNAL_RE.search(head):
        flags.append("journal_marker")
    return flags


def choose_representative(members, docs_by_id):
    def rank(did):
        d = docs_by_id[did]
        return (1 if d.get("tier") == "fulltext" else 0, d.get("words", 0))
    return max(members, key=rank)


def run(work):
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    docs_by_id = {d["doc_id"]: d for d in docs}
    groups_path = os.path.join(work, "dup_groups.json")
    groups = json.load(open(groups_path, encoding="utf-8")) if os.path.exists(groups_path) else []

    dup_role = {}
    for g in groups:
        rep = choose_representative(g["members"], docs_by_id)
        for m in g["members"]:
            dup_role[m] = ("representative" if m == rep else f"duplicate_of:{rep}")

    manifest = []
    for d in docs:
        did = d["doc_id"]
        entry = {"doc_id": did, "tier": d.get("tier"), "sha256": d.get("sha256"),
                 "dup_role": dup_role.get(did, "singleton")}
        if d.get("tier") in ("fulltext", "abstract_only"):
            text = first_page_text(work, did)
            identity = extract_identity(text)
            status, notes = compare_metadata(identity, d.get("provided_metadata") or {})
            flags = risk_flags(text)
            if d.get("tier") == "abstract_only":
                flags.append("abstract_only")
            entry.update(identity=identity, identity_status=status,
                         identity_notes=notes, flags=flags)
            if "retracted_or_withdrawn_marker" in flags:
                trust = "T3"
            elif d.get("tier") == "fulltext" and entry["dup_role"] != "singleton" \
                    and not str(entry["dup_role"]).startswith("representative"):
                trust = "T3"
            elif d.get("tier") == "fulltext" and status != "mismatch" \
                    and entry["dup_role"] in ("singleton", "representative"):
                trust = "T1"
            else:
                trust = "T2"
            if status == "mismatch":
                trust = "T2"
                entry["flags"].append("metadata_mismatch")
            if str(entry["dup_role"]).startswith("duplicate_of"):
                trust = "T3"
        else:
            entry.update(identity={}, identity_status="unparsed",
                         identity_notes=[], flags=["no_fulltext"])
            trust = "T3"
        entry["trust_tier"] = trust
        manifest.append(entry)

    with open(os.path.join(work, "source_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    lines = ["# 来源取证报告（source forensics）", "",
             "| doc | tier | trust | identity | dup | flags |", "|-|-|-|-|-|-|"]
    for e in manifest:
        lines.append("| {doc_id} | {tier} | {trust_tier} | {identity_status} | {dup_role} | {fl} |".format(
            fl=", ".join(e["flags"]) or "-", **e))
    lines += ["", "## 信任分层规则", "",
              "- T1：representative + fulltext + 无撤稿标记 + 元数据不冲突 → 可支撑 established 论断。",
              "- T2：abstract_only / 元数据冲突待核 → strength ≤ suggestive。",
              "- T3：metadata_only / failed / 撤稿标记 / 重复篇 → 不得作为实质论断来源，仅记录。", ""]
    with open(os.path.join(work, "forensics_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return manifest


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    manifest = run(args.work)
    tiers = {}
    for e in manifest:
        tiers[e["trust_tier"]] = tiers.get(e["trust_tier"], 0) + 1
    print(json.dumps({"manifest": len(manifest), "trust_tiers": tiers}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
