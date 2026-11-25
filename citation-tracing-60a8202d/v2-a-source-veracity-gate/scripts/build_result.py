#!/usr/bin/env python3
"""build_result.py — 阶段二：在审计过的语料上构建可溯源的引文追踪结果。

读取 <workdir>/records_norm.jsonl（若缺失且给了 --roots 则自动先跑审计），
鲁棒解析种子（case.json 的 seed_paper/seed/paper/doi/title 字段，
以及 task.md 文本中的 DOI 正则），DOI 规范化精确去重＋标题规范化去重，
构建引用图（references 列表＋全语料反向索引恢复前向边，边上标
direction_restored），从种子做 1–2 层扩展。

locator 门禁：任何没有 locator 的记录不得进入 candidates。

写 <out>/result.json（case_id、status、candidates、edges、sources、
evidence_records、uncertainty，并逐字段镜像 case.json 的 output_contract：
contract 里每个 key 在 result.json 顶层出现；未知语义的 key 给诚实空值
并在 uncertainty 注明）＋ <out>/provenance_report.md。

仅标准库，默认离线，脚本位置无关。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_audit import (  # noqa: E402
    DOI_RE, norm_doi, norm_title, run_audit,
)

SEED_KEYS = ("seed_paper", "seed", "paper", "seed_doi", "seed_title")

# output_contract 已知语义的 key → 填充方式（在 build_result 内部分派）
KNOWN_CONTRACT_KEYS = {
    "case_id", "status", "seed", "candidates", "edges", "sources",
    "evidence_records", "uncertainty", "screening_rationale", "omissions",
}


# ---------------------------------------------------------------- 语料装载

def load_records(workdir):
    path = Path(workdir) / "records_norm.jsonl"
    records, bad_lines = [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                bad_lines += 1
    return records, bad_lines


def record_id(rec):
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    nt = norm_title(rec.get("title"))
    if nt:
        return "title:" + nt
    return "anon:" + hashlib.sha1(
        json.dumps(rec.get("locator", {}), sort_keys=True).encode()).hexdigest()[:12]


def merge_records(records):
    """身份合并基线：DOI 规范化精确匹配 + 标题规范化匹配；
    两键都缺失的记录保持独立。返回 {id: merged_rec} 与合并冲突台账。"""
    merged, doi2id, title2id = {}, {}, {}
    conflicts = []
    for rec in records:
        if rec.get("kind") != "work":
            continue
        rid = None
        if rec.get("doi") and rec["doi"] in doi2id:
            rid = doi2id[rec["doi"]]
        else:
            nt = norm_title(rec.get("title"))
            if nt and nt in title2id:
                rid = title2id[nt]
        if rid is None:
            rid = record_id(rec)
            merged[rid] = {
                "id": rid, "title": rec.get("title"), "authors": rec.get("authors") or [],
                "year": rec.get("year"), "doi": rec.get("doi"), "venue": rec.get("venue"),
                "references": [], "citations": [], "alt_ids": [],
                "sources": [], "source_formats": [],
            }
        m = merged[rid]
        loc = rec.get("locator")
        if loc:
            m["sources"].append(loc)
        src_file = loc.get("file") if loc else None
        # 逐条引用指针保留其来源文件，保证合并后边的 file 归属保真
        for ref in rec.get("references") or []:
            m["references"].append(dict(ref, src_file=src_file))
        for cit in rec.get("citations") or []:
            m["citations"].append(dict(cit, src_file=src_file))
        for field in ("title", "year", "venue"):
            new, old = rec.get(field), m.get(field)
            if new and old and str(new) != str(old):
                conflicts.append({
                    "type": "merged-field-conflict", "id": rid, "field": field,
                    "values": sorted({str(old), str(new)}),
                    "locators": [s for s in m["sources"]],
                })
            elif new and not old:
                m[field] = new
        if rec.get("doi") and not m.get("doi"):
            m["doi"] = rec["doi"]
        for a in rec.get("authors") or []:
            if a not in m["authors"]:
                m["authors"].append(a)
        for a in rec.get("alt_ids") or []:
            if a not in m["alt_ids"]:
                m["alt_ids"].append(a)
        if rec.get("source_format") and rec["source_format"] not in m["source_formats"]:
            m["source_formats"].append(rec["source_format"])
        if rec.get("doi"):
            doi2id[rec["doi"]] = rid
        nt = norm_title(rec.get("title"))
        if nt:
            title2id[nt] = rid
    return merged, conflicts


# ---------------------------------------------------------------- 引用图

def build_indexes(merged):
    doi2id, title2id, altid2id = {}, {}, {}
    for rid, m in merged.items():
        if m.get("doi"):
            doi2id[m["doi"]] = rid
        nt = norm_title(m.get("title"))
        if nt:
            title2id[nt] = rid
        for a in m.get("alt_ids") or []:
            altid2id[str(a)] = rid
    return doi2id, title2id, altid2id


def resolve_ref(ref, doi2id, title2id, altid2id):
    if ref.get("doi") and ref["doi"] in doi2id:
        return doi2id[ref["doi"]]
    nt = norm_title(ref.get("label"))
    if nt and nt in title2id:
        return title2id[nt]
    raw = ref.get("raw_id")
    if raw and str(raw) in altid2id:
        return altid2id[str(raw)]
    return None


def stub_id(ref):
    key = ref.get("doi") or ref.get("label") or ref.get("raw_id") or "unknown"
    return "stub:" + hashlib.sha1(str(key).encode()).hexdigest()[:12]


def build_graph(merged, extra_edges):
    """构建边表。reference 边 = citing→cited；citation 边 = cited→citing。
    数据源只给参考文献列表时，用全语料反向索引恢复前向边并标
    direction_restored=true。无法解析到语料内记录的引用目标保留为 stub。"""
    doi2id, title2id, altid2id = build_indexes(merged)
    edges, stubs, unresolved = [], {}, []
    seen = set()

    def add_edge(frm, to, kind, restored, locator, note=None):
        key = (frm, to, kind, restored)
        if key in seen:
            return
        seen.add(key)
        e = {"from": frm, "to": to, "kind": kind,
             "direction_restored": bool(restored), "source": locator}
        if note:
            e["note"] = note
        edges.append(e)

    for rid, m in merged.items():
        for ref in m.get("references") or []:
            loc = {"file": ref.get("src_file")
                   or (m["sources"][0]["file"] if m["sources"] else None),
                   "pointer": ref.get("pointer")}
            target = resolve_ref(ref, doi2id, title2id, altid2id)
            if target is None:
                sid = stub_id(ref)
                if sid not in stubs:
                    stubs[sid] = {"id": sid, "label": ref.get("label"),
                                  "doi": ref.get("doi"),
                                  "first_seen": loc}
                add_edge(rid, sid, "reference", False, loc,
                         note="target_unresolved: 语料内无此记录，保留 stub")
                unresolved.append({"from": rid, "stub": sid, "locator": loc})
                continue
            add_edge(rid, target, "reference", False, loc)
            # 反向索引恢复前向边：target 的施引文献包含 rid
            add_edge(target, rid, "citation", True, loc)
        for cit in m.get("citations") or []:
            loc = {"file": cit.get("src_file")
                   or (m["sources"][0]["file"] if m["sources"] else None),
                   "pointer": cit.get("pointer")}
            citer = resolve_ref(cit, doi2id, title2id, altid2id)
            if citer is None:
                sid = stub_id(cit)
                if sid not in stubs:
                    stubs[sid] = {"id": sid, "label": cit.get("label"),
                                  "doi": cit.get("doi"), "first_seen": loc}
                add_edge(rid, sid, "citation", False, loc,
                         note="target_unresolved: 语料内无此记录，保留 stub")
                unresolved.append({"from": rid, "stub": sid, "locator": loc})
                continue
            add_edge(rid, citer, "citation", False, loc)
            add_edge(citer, rid, "reference", True, loc)

    # 通用边表文件提供的边（source/target 为 DOI 或标题文本）
    for er in extra_edges:
        src = resolve_ref({"doi": norm_doi(er.get("source")),
                           "label": er.get("source"),
                           "raw_id": er.get("source")},
                          doi2id, title2id, altid2id)
        tgt = resolve_ref({"doi": norm_doi(er.get("target")),
                           "label": er.get("target"),
                           "raw_id": er.get("target")},
                          doi2id, title2id, altid2id)
        if src and tgt:
            add_edge(src, tgt, "reference", False, er.get("locator"),
                     note="from edge-list file")
            add_edge(tgt, src, "citation", True, er.get("locator"))
    return edges, stubs, unresolved


# ---------------------------------------------------------------- 种子与扩展

def resolve_seed(case, task_text):
    """依次尝试 case.json 的 seed_paper/seed/paper/doi/title 字段，
    再用 task.md 文本中的 DOI 正则兜底。返回 {doi, title, via}。"""
    probes = []
    for key in SEED_KEYS + ("doi", "title"):
        if key not in case:
            continue
        v = case[key]
        if isinstance(v, dict):
            probes.append({"doi": norm_doi(v.get("doi") or v.get("DOI")),
                           "title": v.get("title"), "via": "case.json:%s" % key})
        elif isinstance(v, str):
            if DOI_RE.search(v):
                probes.append({"doi": norm_doi(DOI_RE.search(v).group(0)),
                               "title": None, "via": "case.json:%s" % key})
            else:
                probes.append({"doi": None, "title": v,
                               "via": "case.json:%s" % key})
    for p in probes:
        if p.get("doi") or p.get("title"):
            return p
    if task_text:
        m = DOI_RE.search(task_text)
        if m:
            return {"doi": norm_doi(m.group(0)), "title": None,
                    "via": "task.md:doi-regex"}
    return {"doi": None, "title": None, "via": None}


def find_seed_id(seed, doi2id, title2id):
    if seed.get("doi") and seed["doi"] in doi2id:
        return doi2id[seed["doi"]]
    nt = norm_title(seed.get("title"))
    if nt and nt in title2id:
        return title2id[nt]
    return None


def bfs_expand(seed_id, edges, max_hops=2):
    """从种子做 1–2 层扩展。reference 边向后（被引出处），citation 边向前
    （施引后续）。返回 {id: {depth, via}} 与每个 id 对应的证据边。"""
    adj = {}
    for e in edges:
        if e["to"].startswith("stub:"):
            continue
        adj.setdefault(e["from"], []).append(e)
    reached, ev = {}, {}
    if seed_id is None:
        return reached, ev
    frontier = [seed_id]
    seen = {seed_id}
    for depth in (1, 2):
        if depth > max_hops or not frontier:
            break
        nxt = []
        for cur in frontier:
            for e in adj.get(cur, []):
                nb = e["to"]
                if nb in seen:
                    continue
                seen.add(nb)
                direction = ("backward(参考文献)"
                             if e["kind"] == "reference" else "forward(施引)")
                reached[nb] = {"depth": depth, "via": direction}
                ev.setdefault(nb, []).append(e)
                nxt.append(nb)
        frontier = nxt
    return reached, ev


# ---------------------------------------------------------------- 结果装配

def build(case_path, task_path, out_dir, workdir, roots=None, max_hops=2):
    out_dir, workdir = Path(out_dir), Path(workdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    case, uncertainty = {}, []
    if Path(case_path).is_file():
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8"))
        except Exception as exc:
            uncertainty.append("case.json 解析失败：%s" % exc)
    else:
        uncertainty.append("case.json 不存在：%s" % case_path)
    task_text = ""
    if task_path and Path(task_path).is_file():
        task_text = Path(task_path).read_text(encoding="utf-8", errors="replace")

    records_path = workdir / "records_norm.jsonl"
    if not records_path.is_file():
        if roots:
            run_audit(roots, workdir)
        else:
            uncertainty.append(
                "records_norm.jsonl 缺失且未提供 --roots；"
                "请先运行 source_audit.py")
    records, bad_lines = ([], 0)
    if records_path.is_file():
        records, bad_lines = load_records(workdir)
    if bad_lines:
        uncertainty.append("records_norm.jsonl 有 %d 行无法解析，已跳过" % bad_lines)

    works = [r for r in records if r.get("kind") == "work"]
    edge_records = [r for r in records if r.get("kind") == "edge"]
    merged, merge_conflicts = merge_records(works)
    for c in merge_conflicts:
        uncertainty.append("合并字段冲突：%s 的 %s 存在多个值 %s（保留可回指）"
                           % (c["id"], c["field"], " / ".join(c["values"])))
    edges, stubs, unresolved = build_graph(merged, edge_records)

    seed = resolve_seed(case, task_text)
    doi2id, title2id, _ = build_indexes(merged)
    seed_id = find_seed_id(seed, doi2id, title2id)
    if seed_id is None:
        uncertainty.append("种子未在语料中解析到记录（doi=%s, title=%s, via=%s）"
                           % (seed.get("doi"), seed.get("title"), seed.get("via")))

    reached, ev = bfs_expand(seed_id, edges, max_hops=max_hops)

    # ---- locator 门禁：没有 locator 的记录不得进入 candidates
    candidates, gated = [], []
    for rid, meta in sorted(reached.items(), key=lambda kv: (kv[1]["depth"], kv[0])):
        m = merged[rid]
        locators = [s for s in m.get("sources") if s and s.get("file") and s.get("pointer")]
        if not locators:
            gated.append(rid)
            continue
        candidates.append({
            "id": rid, "title": m.get("title"), "authors": m.get("authors"),
            "year": m.get("year"), "doi": m.get("doi"), "venue": m.get("venue"),
            "depth": meta["depth"], "reached_via": meta["via"],
            "source_formats": m.get("source_formats"),
            "sources": locators,
        })
    if gated:
        uncertainty.append("locator 门禁拦截 %d 条无定位记录：%s"
                           % (len(gated), "、".join(gated)))
    if unresolved:
        uncertainty.append("%d 条引用目标在语料内无记录，已保留为 stub（不补造元数据）"
                           % len(unresolved))

    # ---- sources：优先复用审计注册表
    sources = []
    reg_path = workdir / "source_registry.json"
    if reg_path.is_file():
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            for e in reg.get("files", []):
                sources.append({"file": e["file"], "sha1": e.get("sha1"),
                                "bytes": e.get("bytes"), "format": e.get("format"),
                                "records": e.get("records"), "status": e.get("status")})
        except Exception as exc:
            uncertainty.append("source_registry.json 读取失败：%s" % exc)
    if not sources:
        seen_files = {}
        for c in candidates:
            for loc in c["sources"]:
                seen_files.setdefault(loc["file"], {"file": loc["file"],
                                                    "format": None, "status": "locator-only"})
        sources = sorted(seen_files.values(), key=lambda d: d["file"])

    evidence_records = []
    for c in candidates:
        ev_edges = ev.get(c["id"], [])
        evidence_records.append({
            "candidate_id": c["id"],
            "title": c["title"],
            "depth": c["depth"],
            "reached_via": c["reached_via"],
            "edge_evidence": [
                {"from": e["from"], "to": e["to"], "kind": e["kind"],
                 "direction_restored": e["direction_restored"],
                 "source": e.get("source")} for e in ev_edges],
            "locators": c["sources"],
        })

    # ---- 诚实 status：存在真实性瑕疵（损坏/未解析语料文件、合并冲突、
    # 未解析引用 stub、门禁拦截、坏行）时，即使扩展成功也报 partial。
    veracity_flags = []
    failed_sources = [s["file"] for s in sources
                      if s.get("status") in ("failed", "unparsed")]
    if failed_sources:
        veracity_flags.append("%d 个语料文件解析失败/未判定：%s"
                              % (len(failed_sources), "、".join(failed_sources)))
    if merge_conflicts:
        veracity_flags.append("%d 组合并字段冲突" % len(merge_conflicts))
    if unresolved:
        veracity_flags.append("%d 条未解析引用目标（stub）" % len(unresolved))
    if gated:
        veracity_flags.append("%d 条记录被 locator 门禁拦截" % len(gated))
    if bad_lines:
        veracity_flags.append("%d 行 records_norm 坏行" % bad_lines)
    for vf in veracity_flags:
        uncertainty.append("真实性瑕疵（status 降级依据）：%s" % vf)

    if not works:
        status = "failed"
        uncertainty.append("语料中没有可用的文献记录")
    elif seed_id is None:
        status = "partial" if works else "failed"
    elif not candidates:
        status = "partial"
    else:
        status = "partial" if veracity_flags else "ok"

    seed_out = {"doi": seed.get("doi"), "title": seed.get("title"),
                "via": seed.get("via"),
                "corpus_id": seed_id,
                "found_in_corpus": seed_id is not None}

    rationale = (
        "从种子出发沿引用图做 1–%d 层扩展（reference 边向后、"
        "citation 边向前，前向边由全语料反向索引恢复处标 direction_restored）；"
        "身份合并采用 DOI 规范化精确匹配＋标题规范化匹配；"
        "所有候选均通过 locator 门禁（必须带 {file, pointer} 定位）。"
        % max_hops)
    omissions = (
        [{"type": "unresolved-reference", "detail": u} for u in unresolved[:50]]
        + [{"type": "locator-gated", "detail": g} for g in gated])

    result = {
        "case_id": case.get("case_id") or case.get("id") or "UNKNOWN",
        "status": status,
        "seed": seed_out,
        "candidates": candidates,
        "edges": edges,
        "sources": sources,
        "evidence_records": evidence_records,
        "uncertainty": uncertainty,
        "stubs": sorted(stubs.values(), key=lambda d: d["id"]),
        "screening_rationale": rationale,
        "omissions": omissions,
    }

    # ---- output_contract 逐字段镜像：contract 每个 key 必须在顶层出现；
    # 未知语义的 key 给诚实空值并在 uncertainty 注明。
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for key in contract:
            if key not in result:
                result[key] = None
                if key not in KNOWN_CONTRACT_KEYS:
                    result["uncertainty"].append(
                        "output_contract 字段 '%s' 语义未在本 Skill 中定义，"
                        "已按诚实空值(null)填充" % key)
        result["output_contract_mirrored"] = sorted(contract.keys())
    elif contract:
        result["uncertainty"].append("output_contract 不是对象，无法逐字段镜像")

    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "provenance_report.md").write_text(
        render_provenance(result, merged), encoding="utf-8")
    return result


def render_provenance(result, merged):
    L = ["# 溯源报告（provenance_report）", ""]
    s = result["seed"]
    L.append("## 种子")
    L.append("")
    L.append("- DOI：%s" % (s.get("doi") or "（未给出）"))
    L.append("- 标题：%s" % (s.get("title") or "（未给出）"))
    L.append("- 种子解析途径：%s；语料内命中：%s"
             % (s.get("via"), "是" if s.get("found_in_corpus") else "否"))
    L.append("")
    L.append("## 状态：%s" % result["status"])
    L.append("")
    L.append("- 候选数：%d；边数：%d；stub（未解析引用目标）数：%d"
             % (len(result["candidates"]), len(result["edges"]),
                len(result.get("stubs", []))))
    L.append("")
    L.append("## 候选清单（逐条可回指）")
    L.append("")
    L.append("| # | 深度 | 方向 | 标题 | DOI | 来源定位 |")
    L.append("|---|---|---|---|---|---|")
    for i, c in enumerate(result["candidates"], 1):
        locs = "<br>".join("`%s` `%s`" % (l["file"], l["pointer"])
                           for l in c["sources"])
        L.append("| %d | %d | %s | %s | %s | %s |"
                 % (i, c["depth"], c["reached_via"], c.get("title") or "",
                    c.get("doi") or "", locs))
    L.append("")
    L.append("## 引用边（每条边带数据源定位）")
    L.append("")
    L.append("| from | to | 类型 | direction_restored | source |")
    L.append("|---|---|---|---|---|")
    for e in result["edges"]:
        src = e.get("source") or {}
        L.append("| %s | %s | %s | %s | `%s` `%s` |"
                 % (e["from"], e["to"], e["kind"], e["direction_restored"],
                    src.get("file"), src.get("pointer")))
    L.append("")
    L.append("## 不确定性与诚实说明")
    L.append("")
    if result["uncertainty"]:
        for u in result["uncertainty"]:
            L.append("- %s" % u)
    else:
        L.append("（无）")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="构建可溯源引文追踪结果（阶段二）")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", action="append", default=None,
                    help="records_norm.jsonl 缺失时用于自动审计的候选根")
    ap.add_argument("--max-hops", type=int, default=2)
    args = ap.parse_args(argv)
    result = build(args.case, args.task, args.out, args.workdir,
                   roots=args.roots, max_hops=args.max_hops)
    print(json.dumps({
        "case_id": result["case_id"], "status": result["status"],
        "candidates": len(result["candidates"]),
        "edges": len(result["edges"]),
        "uncertainty": len(result["uncertainty"]),
        "out": str(Path(args.out).resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
