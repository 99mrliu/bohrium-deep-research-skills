#!/usr/bin/env python3
"""mint_nanopubs.py — 来源指纹核验、断言落账、去重合并、版本对照与导出（纯标准库）。

输入：
  --claims   JSONL，每行一条断言（含 source_id、subject/relation/object、
             qualifiers、polarity、modality、evidence）
  --sources  JSON，来源记录列表（含 source_id、title、creators、year、
             identifier、version、path、可选 supersedes）
  --outdir   输出目录

输出：
  nanopubs.jsonl        去重合并后的断言与完整来源链
  nanopubs.trig         nanopub 风格四命名图（head/assertion/provenance/pubinfo）
  provenance-report.json 指纹核验、合并日志、版本对照、冲突项

URI 为本机确定性内容寻址（nanopub.local 命名空间），不是注册标识、不是
Trusty URI。冲突（同主体同关系同限定、客体不同）只报告、不裁定。
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import sys
import unicodedata

VERSION = "1.0.0"
NS = "https://nanopub.local"


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"\s+", " ", s).strip()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_id(payload):
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    digest = hashlib.sha256(canon.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:32]


def slug(text, limit=40):
    s = norm(text)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:limit] or "unnamed")


def semantic_key(c):
    quals = c.get("qualifiers", []) or []
    qtxt = sorted(norm(q if isinstance(q, str) else q.get("text", "")) for q in quals)
    return {
        "subject": norm(c.get("subject", "")),
        "relation": str(c.get("relation", "")),
        "object": norm(str(c.get("object", ""))),
        "qualifiers": qtxt,
        "polarity": str(c.get("polarity", "positive")),
        "modality": str(c.get("modality", "asserted")),
    }


def identifier_text(identifier):
    if isinstance(identifier, dict):
        return str(identifier.get("value", "unavailable"))
    return str(identifier) if identifier else "unavailable"


def trig_escape(s):
    s = str(s)
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def main():
    ap = argparse.ArgumentParser(description="断言落账与来源追溯导出")
    ap.add_argument("--claims", required=True)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    with open(args.sources, encoding="utf-8") as fh:
        sources = json.load(fh)
    claims = []
    with open(args.claims, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                claims.append(json.loads(line))

    report = {"tool": "mint_nanopubs", "version": VERSION, "sources": [],
              "claims_input": len(claims), "merges": [], "conflicts": [],
              "version_chains": [], "errors": []}

    # --- 来源指纹核验 ---
    src_by_id = {}
    for s in sources:
        sid = s.get("source_id")
        if not sid:
            report["errors"].append({"code": "E_SOURCE_ID_MISSING", "source": s})
            continue
        rec = dict(s)
        path = s.get("path")
        if path and os.path.isfile(path):
            actual = sha256_file(path)
            declared = s.get("sha256")
            rec["sha256_actual"] = actual
            if declared and declared != actual:
                report["errors"].append({
                    "code": "E_SOURCE_MISMATCH", "source_id": sid,
                    "declared": declared, "actual": actual,
                    "detail": "声明指纹与文件重算不一致：文件可能已被替换"})
                rec["fingerprint"] = "mismatch"
            else:
                rec["fingerprint"] = "ok"
                rec["sha256"] = actual
        elif path:
            rec["fingerprint"] = "file_missing"
            report["errors"].append({"code": "E_SOURCE_FILE_MISSING",
                                     "source_id": sid, "path": path})
        else:
            rec["fingerprint"] = "no_path"
        src_by_id[sid] = rec
        report["sources"].append({
            "source_id": sid, "title": s.get("title", "unavailable"),
            "identifier": s.get("identifier", "unavailable"),
            "version": s.get("version", "unavailable"),
            "fingerprint": rec.get("fingerprint"),
            "sha256": rec.get("sha256", rec.get("sha256_actual")),
        })

    # --- 语义键去重合并 ---
    merged = {}
    for c in claims:
        key_payload = semantic_key(c)
        key = content_id(key_payload)
        sid = c.get("source_id", "")
        binding = {
            "claim_local_id": c.get("id"),
            "source_id": sid,
            "source_sha256": src_by_id.get(sid, {}).get("sha256")
                             or src_by_id.get(sid, {}).get("sha256_actual"),
            "source_title": src_by_id.get(sid, {}).get("title", "unavailable"),
            "source_identifier": src_by_id.get(sid, {}).get("identifier", "unavailable"),
            "source_version": src_by_id.get(sid, {}).get("version", "unavailable"),
            "evidence": c.get("evidence", {}),
        }
        if key in merged:
            merged[key]["sources"].append(binding)
            report["merges"].append({
                "key": key, "kept": merged[key]["claim_uri"],
                "added_claim_id": c.get("id"), "source_id": sid,
                "detail": "语义键一致，合并保留全部来源绑定"})
        else:
            merged[key] = {
                "claim_uri": f"{NS}/RA{content_id({'claim': key_payload})}",
                "semantic_key": key_payload,
                "text": c.get("text", ""),
                "subject": c.get("subject", ""),
                "relation": c.get("relation", ""),
                "object": c.get("object", ""),
                "qualifiers": c.get("qualifiers", []),
                "polarity": c.get("polarity", "positive"),
                "modality": c.get("modality", "asserted"),
                "confidence": c.get("confidence", {}),
                "sources": [binding],
            }

    # --- 冲突检测：同主体同关系同限定、客体不同 ---
    by_srq = {}
    for key, m in merged.items():
        sk = m["semantic_key"]
        srq = (sk["subject"], sk["relation"], tuple(sk["qualifiers"]))
        by_srq.setdefault(srq, []).append(m)
    for (subj, rel, quals), items in by_srq.items():
        objs = {norm(str(m["object"])) for m in items}
        if len(items) > 1 and len(objs) > 1:
            report["conflicts"].append({
                "subject": subj, "relation": rel, "qualifiers": list(quals),
                "objects": sorted({str(m["object"]) for m in items}),
                "claim_uris": [m["claim_uri"] for m in items],
                "detail": "同主体同关系同限定但客体不同：只报告，不裁定"})

    # --- 版本对照 ---
    for s in sources:
        older = s.get("supersedes")
        if not older:
            continue
        new_id, old_id = s.get("source_id"), older
        def keys_for(sid):
            out = set()
            for key, m in merged.items():
                if any(b["source_id"] == sid for b in m["sources"]):
                    out.add(key)
            return out
        knew, kold = keys_for(new_id), keys_for(old_id)
        report["version_chains"].append({
            "supersedes": f"{new_id} supersedes {old_id}",
            "only_new": sorted(knew - kold), "only_old": sorted(kold - knew),
            "both": sorted(knew & kold),
            "detail": "仅旧/仅新断言保留原位，不擅自以新替旧"})

    # --- 导出 JSONL ---
    os.makedirs(args.outdir, exist_ok=True)
    jsonl_path = os.path.join(args.outdir, "nanopubs.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for key in sorted(merged, key=lambda k: merged[k]["claim_uri"]):
            m = merged[key]
            rec = {k: m[k] for k in ("claim_uri", "text", "subject", "relation",
                                     "object", "qualifiers", "polarity",
                                     "modality", "confidence", "sources")}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # --- 导出 TriG ---
    created = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    trig_path = os.path.join(args.outdir, "nanopubs.trig")
    lines = [
        "@prefix np: <http://www.nanopub.org/nschema#> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix dcterms: <http://purl.org/dc/terms/> .",
        "@prefix npl: <https://nanopub.local/schema#> .",
        "",
    ]
    for key in sorted(merged, key=lambda k: merged[k]["claim_uri"]):
        m = merged[key]
        uri = m["claim_uri"]
        head, assertion = f"{uri}#head", f"{uri}#assertion"
        prov, pubinfo = f"{uri}#provenance", f"{uri}#pubinfo"
        ent = f"{NS}/entity/{slug(m['subject'])}-{content_id({'e': norm(m['subject'])})[:8]}"
        rel = f"{NS}/rel/{m['relation']}"
        lines.append(f"<{uri}> a np:Nanopublication .")
        lines.append(f"<{head}> {{")
        lines.append(f"  <{uri}> np:hasAssertion <{assertion}> ;")
        lines.append(f"    np:hasProvenance <{prov}> ;")
        lines.append(f"    np:hasPublicationInfo <{pubinfo}> .")
        lines.append("}")
        lines.append(f"<{assertion}> {{")
        obj_lit = f"\"{trig_escape(m['object'])}\""
        lines.append(f"  <{ent}> <{rel}> {obj_lit} .")
        lines.append(f"  <{ent}> npl:claimText \"{trig_escape(m['text'])}\" .")
        if m.get("polarity") == "negative":
            lines.append(f"  <{ent}> npl:polarity \"negative\" .")
        if m.get("modality") and m["modality"] != "asserted":
            lines.append(f"  <{ent}> npl:modality \"{trig_escape(m['modality'])}\" .")
        for q in m.get("qualifiers", []) or []:
            qtxt = q if isinstance(q, str) else q.get("text", "")
            lines.append(f"  <{ent}> npl:qualifier \"{trig_escape(qtxt)}\" .")
        lines.append("}")
        lines.append(f"<{prov}> {{")
        for b in m["sources"]:
            src_uri = f"{NS}/source/{slug(b['source_id'])}"
            lines.append(f"  <{assertion}> prov:wasDerivedFrom <{src_uri}> .")
            lines.append(f"  <{src_uri}> dcterms:title "
                         f"\"{trig_escape(b['source_title'])}\" .")
            lines.append(f"  <{src_uri}> npl:identifier "
                         f"\"{trig_escape(identifier_text(b['source_identifier']))}\" .")
            if b.get("source_sha256"):
                lines.append(f"  <{src_uri}> npl:sha256 \"{b['source_sha256']}\" .")
            ev = b.get("evidence", {}) or {}
            if ev.get("quote"):
                lines.append(f"  <{assertion}> npl:evidenceQuote "
                             f"\"{trig_escape(ev['quote'][:500])}\" .")
        lines.append("}")
        lines.append(f"<{pubinfo}> {{")
        creators = set()
        for b in m["sources"]:
            for cr in src_by_id.get(b["source_id"], {}).get("creators", []) or []:
                creators.add(cr)
        for cr in sorted(creators):
            lines.append(f"  <{uri}> dcterms:creator \"{trig_escape(cr)}\" .")
        lines.append(f"  <{uri}> dcterms:created \"{created}\" .")
        lines.append("}")
        lines.append("")
    with open(trig_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    # --- 汇总 ---
    report["summary"] = {
        "claims_input": len(claims),
        "unique_claims": len(merged),
        "merged_events": len(report["merges"]),
        "conflicts": len(report["conflicts"]),
        "sources": len(report["sources"]),
        "fingerprint_errors": sum(1 for e in report["errors"]
                                  if e["code"].startswith("E_SOURCE")),
        "outputs": {"jsonl": os.path.abspath(jsonl_path),
                    "trig": os.path.abspath(trig_path)},
        "gate": "pass" if not report["errors"] else "fail",
    }
    report_path = os.path.join(args.outdir, "provenance-report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
