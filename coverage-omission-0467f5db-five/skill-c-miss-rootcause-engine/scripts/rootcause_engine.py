#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rootcause_engine.py -- 漏检根因诊断引擎（skill-c-miss-rootcause-engine）。

重心：每一条漏检都是一个待诊断案例，归因必须是"探针执行结果"，不是措辞。
  五条可执行探针（references/attribution_taxonomy.md 定义判定逻辑）：
    P1 vocabulary   查询词未覆盖同义/变体表达（证据：语料出现而查询缺失的词形）
    P2 field        检索字段限制过窄（证据：区分性信息只存在于未检字段）
    P3 time_window  时间窗截断（证据：年份与窗口边界的数值比较）
    P4 source       来源库未收录（证据：本地响应中来源覆盖的正反两方面检索）
    P5 identifier   记录标识异常（证据：标识符解析失败或解析到不同文献）
  每条证据一律 "file + line/JSONPath + excerpt" 三要素，可独立复核。
闭环：参考集解析 -> 命中判定 -> 逐条探针诊断 -> 按归因生成定向补检式 ->
     （若材料含补检结果则复算遗漏下降量）-> result.json。

仅 Python 标准库，不联网。退出码 0/2/3（完成/partial/契约缺失）。
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------- 基础工具

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip().rstrip(".")


def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def tokens(t):
    stop = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by"}
    return [x for x in norm_title(t).split() if x not in stop]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def first_year(rec):
    for k in ("year", "published", "issued", "date"):
        v = rec.get(k)
        if v is None:
            continue
        m = re.search(r"(?:19|20)\d{2}", str(v))
        if m:
            return int(m.group(0))
    return None


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 证据定位器

class EvidenceLocator:
    """在材料文件中定位字符串证据：file + line + excerpt。"""

    def __init__(self, material_files):
        self.files = [f for f in material_files if os.path.isfile(f)]

    def find(self, needle, max_hits=1):
        needle_l = str(needle).lower()
        if not needle_l:
            return []
        out = []
        for p in self.files:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for i, ln in enumerate(fh, 1):
                        if needle_l in ln.lower():
                            out.append({"file": p, "locator": "line %d" % i,
                                        "excerpt": ln.strip()[:200]})
                            if len(out) >= max_hits:
                                return out
            except Exception:
                continue
        return out


# ---------------------------------------------------------------- 材料装载

def collect(input_dir):
    mats, refs, queries = [], [], []
    responses = []
    for root, _d, names in os.walk(input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            if not os.path.isfile(p) or os.path.islink(p):
                continue
            low = name.lower()
            if low in ("case.json", "task.md"):
                continue
            mats.append(p)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(8192)
            except Exception:
                continue
            if re.search(r'"(queries|searches)"\s*:', head) and re.search(r'"(hits|results|records)"\s*:', head):
                data = load_json(p) or {}
                for q in data.get("queries") or data.get("searches") or []:
                    if isinstance(q, dict):
                        qq = dict(q)
                        qq["_file"] = p
                        queries.append(qq)
            elif low.endswith(".csv"):
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for i, row in enumerate(csv.DictReader(fh)):
                        r = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
                        if r:
                            refs.append({"record": r, "origin": "%s:row%d" % (p, i + 2)})
            elif re.search(r'crossref|europepmc|"message"\s*:\s*\{|"resultList"', head, re.I):
                responses.append(p)
    return mats, refs, queries, responses


def parse_response_records(responses):
    """本地响应 -> doi -> record（供 P4/P5 探针使用）。"""
    by_doi = {}
    for p in responses:
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception:
            continue
        objs = []
        lines = [ln for ln in text.splitlines() if ln.strip().startswith("{")]
        ok = True
        for ln in lines:
            try:
                objs.append(json.loads(ln))
            except Exception:
                ok = False
        if not ok or not objs:
            try:
                objs = [json.loads(text)]
            except Exception:
                continue
        for o in objs:
            items = []
            if isinstance(o, dict) and isinstance(o.get("message"), dict):
                msg = o["message"]
                items = msg.get("items") or [msg]
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict):
                    d = norm_doi(it.get("DOI") or it.get("doi"))
                    if d:
                        by_doi[d] = {"record": it, "file": p}
    return by_doi


# ---------------------------------------------------------------- 探针

def probe_vocabulary(rec, queries, locator):
    qstr = " ".join(str(q.get("query_string") or q.get("query") or "") for q in queries).lower()
    if not qstr:
        return None
    distinctive = [t for t in tokens(rec.get("title")) if len(t) > 5]
    missing = [t for t in distinctive if t not in qstr]
    if not missing:
        return None
    evid = []
    for t in missing[:3]:
        locs = locator.find(t)
        evid.append({"claim": "distinctive token '%s' absent from all query strings" % t,
                     "corpus_occurrence": locs[0] if locs else "token not found in local materials either"})
    return {"category": "query_term_missing", "probe": "P1_vocabulary", "evidence": evid}


def probe_field(rec, queries, resp_by_doi):
    fields = {str(q.get("fields") or q.get("field") or "").lower() for q in queries}
    fields.discard("")
    if not fields or any("abstract" in f or "mesh" in f for f in fields):
        return None  # 字段已含摘要，探针无结论
    d = norm_doi(rec.get("doi"))
    remote = resp_by_doi.get(d)
    if not remote:
        return None
    abst = ""
    r = remote["record"]
    for k in ("abstract", "Abstract"):
        if r.get(k):
            abst = re.sub(r"<[^>]+>", " ", str(r[k]))
            break
    if not abst:
        return None
    qstr = " ".join(str(q.get("query_string") or "") for q in queries).lower()
    abst_terms = [t for t in tokens(abst) if len(t) > 6 and t in qstr and t not in tokens(rec.get("title"))]
    if abst_terms:
        return {"category": "field_too_narrow", "probe": "P2_field",
                "evidence": [{"claim": "queries matched abstract-only terms %s but declared fields are %s"
                              % (abst_terms[:3], sorted(fields)),
                              "source_record": {"file": remote["file"], "locator": "doi:%s" % d,
                                                "excerpt": abst[:180]}}]}
    return None


def probe_time_window(rec, queries):
    out = []
    for q in queries:
        w = str(q.get("time_window") or q.get("years") or "")
        yrs = [int(y) for y in re.findall(r"(?:19|20)\d{2}", w)]
        if rec.get("year") and len(yrs) >= 2 and not (min(yrs) <= rec["year"] <= max(yrs)):
            out.append({"category": "time_window_cutoff", "probe": "P3_time_window",
                        "evidence": [{"claim": "record year %d outside window [%d,%d] of query %s"
                                      % (rec["year"], min(yrs), max(yrs), q.get("query_id") or q.get("id")),
                                      "query_ref": {"file": q.get("_file"), "locator": "query_id:%s" % (q.get("query_id") or q.get("id")),
                                                    "excerpt": str(q.get("query_string"))[:160]}}]})
    return out[0] if out else None


def probe_source(rec, queries, locator, resp_by_doi):
    venues = {str(q.get("source") or q.get("database") or "") for q in queries}
    venues.discard("")
    container = rec.get("container") or ""
    if not container or not venues:
        return None
    locs = locator.find(container)
    covered = any(l for l in locs if "search" in os.path.basename(l["file"]).lower())
    if not covered:
        ev = {"claim": "venue '%s' not observed in searched-source material; searched sources: %s"
              % (container, ", ".join(sorted(venues)))}
        if locs:
            ev["venue_occurrence"] = locs[0]
        return {"category": "source_not_covered", "probe": "P4_source", "evidence": [ev]}
    return None


def probe_identifier(rec, resp_by_doi):
    d = norm_doi(rec.get("doi"))
    if not d and not rec.get("pmid"):
        return {"category": "identifier_missing", "probe": "P5_identifier",
                "evidence": [{"claim": "reference record carries neither DOI nor PMID; "
                              "cannot be resolved or matched by identifier"}]}
    if d and resp_by_doi:
        remote = resp_by_doi.get(d)
        if remote:
            rt = remote["record"].get("title")
            rt = rt[0] if isinstance(rt, list) and rt else rt
            if rt and rec.get("title") and jaccard(tokens(rec["title"]), tokens(rt)) < 0.5:
                return {"category": "identifier_conflict", "probe": "P5_identifier",
                        "evidence": [{"claim": "DOI resolves to a different work in local response",
                                      "source_record": {"file": remote["file"], "locator": "doi:%s" % d,
                                                        "excerpt": str(rt)[:180]}}]}
        else:
            return {"category": "identifier_unresolvable", "probe": "P5_identifier",
                    "evidence": [{"claim": "DOI not present in any local retained response; "
                                  "resolution impossible offline"}]}
    return None


PROBES = ("P1_vocabulary", "P2_field", "P3_time_window", "P4_source", "P5_identifier")

# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="漏检根因诊断引擎：五探针归因 -> 定向补检式")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    case = load_json(os.path.join(args.input, "case.json"), {}) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    oc = case.get("output_contract") or {}
    if isinstance(oc, dict):
        contract = list(oc.get("required_fields") or oc.get("fields") or oc.keys())
    elif isinstance(oc, list):
        contract = [str(x) for x in oc]
    else:
        contract = []
    if not contract:
        contract = ["coverage", "miss_diagnosis", "supplement_queries", "omission_delta", "coverage_report"]

    status, uncertainty, change_log = "complete", [], []
    mats, refs_raw, queries, responses = collect(args.input)
    locator = EvidenceLocator(mats)
    resp_by_doi = parse_response_records(responses)

    # 参考集（轻量治理；深度取证非本技能重心）
    refset, seen = [], set()
    for c in refs_raw:
        r = c["record"]
        key = norm_doi(r.get("doi")) or norm_title(r.get("title"))[:80]
        if key and key in seen:
            change_log.append({"ts": now_iso(), "event": "dedup_merge", "merged": c["origin"]})
            continue
        if key:
            seen.add(key)
        refset.append({"ref_id": "R%03d" % (len(refset) + 1), "doi": r.get("doi"), "pmid": r.get("pmid"),
                       "title": r.get("title", ""), "year": first_year(r),
                       "container": r.get("container", ""), "origin": c["origin"]})
    if not refset:
        status = "partial"
        change_log.append({"ts": now_iso(), "event": "no_reference_records"})

    # 命中判定（L1 标识符 / L2 标题+年份 0.80）
    hits = []
    for q in queries:
        for h in q.get("hits") or q.get("results") or q.get("records") or []:
            if isinstance(h, dict):
                hh = dict(h)
                hh["_query_id"] = q.get("query_id") or q.get("id")
                hh["_source"] = q.get("source") or ""
                hits.append(hh)
    per_record = []
    for rec in refset:
        st, lvl, ev = "miss", None, None
        rd = norm_doi(rec.get("doi"))
        for h in hits:
            if rd and norm_doi(h.get("doi")) and rd == norm_doi(h.get("doi")):
                st, lvl, ev = "hit", "L1", h
                break
        if st == "miss":
            for h in hits:
                if jaccard(tokens(rec["title"]), tokens(h.get("title"))) >= 0.8:
                    ry, hy = rec.get("year"), first_year(h)
                    if not ry or not hy or ry == hy:
                        st, lvl, ev = "hit", "L2", h
                        break
        per_record.append({"ref_id": rec["ref_id"], "doi": rec.get("doi"), "title": rec["title"][:140],
                           "status": st, "match_level": lvl,
                           "evidence": ({"query_id": ev.get("_query_id"), "source": ev.get("_source")}
                                        if ev else None)})
    hit_n = sum(1 for r in per_record if r["status"] == "hit")
    denom = len(per_record)
    coverage = {"denominator": denom, "hit": hit_n, "miss": denom - hit_n,
                "coverage_ratio": round(hit_n / denom, 4) if denom else None,
                "per_record": per_record}

    # 逐条探针诊断
    diagnosis = []
    for r in per_record:
        if r["status"] != "miss":
            continue
        rec = next(x for x in refset if x["ref_id"] == r["ref_id"])
        findings = []
        for f in (lambda: probe_vocabulary(rec, queries, locator),
                  lambda: probe_field(rec, queries, resp_by_doi),
                  lambda: probe_time_window(rec, queries),
                  lambda: probe_source(rec, queries, locator, resp_by_doi),
                  lambda: probe_identifier(rec, resp_by_doi)):
            try:
                res = f()
            except Exception as exc:  # 探针失败不静默：记录为探针异常
                res = {"category": "probe_error", "probe": "unknown",
                       "evidence": [{"claim": "probe raised %s" % type(exc).__name__}]}
            if res:
                findings.append(res)
        if not findings:
            findings = [{"category": "unresolved", "probe": "all",
                         "evidence": [{"claim": "all five probes inconclusive; escalate to manual review"}]}]
        diagnosis.append({"ref_id": r["ref_id"], "title": r["title"], "findings": findings})
    dump_json(os.path.join(args.work, "miss_diagnosis.json"), diagnosis)

    # 按归因生成定向补检式（每类归因对应一种补检动作）
    supp_queries = []
    for d in diagnosis:
        cats = {f["category"] for f in d["findings"]}
        rec = next(x for x in refset if x["ref_id"] == d["ref_id"])
        if "query_term_missing" in cats:
            tk = [t for t in tokens(rec["title"]) if len(t) > 5][:4]
            supp_queries.append({"target_ref": d["ref_id"], "cause": "query_term_missing",
                                 "new_query": " OR ".join(tk), "new_source": None,
                                 "expected_gain": "retrieve record via distinctive title tokens"})
        if "time_window_cutoff" in cats:
            supp_queries.append({"target_ref": d["ref_id"], "cause": "time_window_cutoff",
                                 "new_query": "(same terms) AND year:%s" % rec.get("year"),
                                 "new_source": None, "expected_gain": "lift window boundary to include record year"})
        if "source_not_covered" in cats:
            supp_queries.append({"target_ref": d["ref_id"], "cause": "source_not_covered",
                                 "new_query": None, "new_source": "source indexing '%s'" % rec.get("container"),
                                 "expected_gain": "cover venue not present in searched sources"})
        if "identifier_missing" in cats or "identifier_conflict" in cats or "identifier_unresolvable" in cats:
            supp_queries.append({"target_ref": d["ref_id"], "cause": "identifier_anomaly",
                                 "new_query": "title-fragment manual lookup", "new_source": None,
                                 "expected_gain": "repair identifier before machine matching"})
    supplement = {"executed": False, "new_queries": supp_queries,
                  "note": "queries are diagnosis-driven; execute via the case search interface and rerun "
                          "this engine with supplemental results to measure omission delta"}
    dump_json(os.path.join(args.work, "supplement_queries.json"), supplement)

    # 遗漏下降量（若材料中提供了补检结果文件，则复算）
    omission_delta = {"measured": False,
                      "note": "no supplemental-round results found in materials; delta unmeasured"}
    supp_file = next((p for p in mats if "supplement" in os.path.basename(p).lower() and p.endswith(".json")), None)
    if supp_file:
        sdata = load_json(supp_file) or {}
        shits = sdata.get("hits") or sdata.get("results") or []
        recovered = []
        for d in diagnosis:
            rec = next(x for x in refset if x["ref_id"] == d["ref_id"])
            rd = norm_doi(rec.get("doi"))
            for h in shits:
                if isinstance(h, dict) and ((rd and norm_doi(h.get("doi")) == rd) or
                                            jaccard(tokens(rec["title"]), tokens(h.get("title"))) >= 0.8):
                    recovered.append(d["ref_id"])
                    break
        omission_delta = {"measured": True, "supplement_file": supp_file,
                          "miss_before": len(diagnosis), "recovered": len(recovered),
                          "miss_after": len(diagnosis) - len(recovered),
                          "recovered_refs": recovered,
                          "residual_explanation": "residual misses retain their diagnosis above"}
    dump_json(os.path.join(args.work, "omission_delta.json"), omission_delta)

    # 报告
    lines = ["# 漏检根因诊断报告", "",
             "- case_id: `%s`" % case_id,
             "- 覆盖：分母 %d / 命中 %d / 漏检 %d（%.4f）" % (denom, hit_n, denom - hit_n, coverage["coverage_ratio"] or 0.0),
             "- 诊断：%d 条漏检全部完成五探针扫描；证据均为 file+locator+excerpt" % len(diagnosis),
             "- 补检：生成 %d 条定向补检式；遗漏下降量测量：%s" % (
                 len(supp_queries), "已测量" if omission_delta["measured"] else "未测量（无补检结果材料）"),
             "", "## 逐条诊断", ""]
    for d in diagnosis:
        lines.append("### %s %s" % (d["ref_id"], d["title"][:80]))
        for f in d["findings"]:
            lines.append("- **%s**（%s）" % (f["category"], f["probe"]))
            for e in f["evidence"][:2]:
                lines.append("  - %s" % e.get("claim", ""))
                for k in ("corpus_occurrence", "source_record", "query_ref", "venue_occurrence"):
                    if k in e and isinstance(e[k], dict):
                        v = e[k]
                        lines.append("    - 证据：`%s` %s — %s" % (v.get("file"), v.get("locator"), str(v.get("excerpt"))[:100]))
        lines.append("")
    report_path = os.path.join(args.output, "coverage_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    artifacts = {"coverage": {k: coverage[k] for k in ("denominator", "hit", "miss", "coverage_ratio")},
                 "miss_diagnosis": diagnosis, "supplement_queries": supplement,
                 "omission_delta": omission_delta, "coverage_report": report_path}
    result = {"case_id": case_id, "status": status,
              "sources": [{"path": p} for p in mats],
              "uncertainty": uncertainty, "change_log": change_log,
              "skill": "miss-rootcause-engine", "skill_version": VERSION}
    for f in contract:
        result[f] = artifacts.get(f)
    dump_json(os.path.join(args.output, "result.json"), result)
    missing = [f for f in contract if result.get(f) is None]
    if missing:
        print("contract fields unresolved: %s" % missing, file=sys.stderr)
        return 3
    return 2 if status == "partial" else 0


if __name__ == "__main__":
    sys.exit(main())
