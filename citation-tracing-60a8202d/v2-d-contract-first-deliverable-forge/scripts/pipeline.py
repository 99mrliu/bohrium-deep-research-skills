#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline.py — 语料发现 → 解析 → 去重 → 1–2 层引用扩展 → 按 output_contract 填充 result.json

运行契约（Harbor 默认值）：
    python3 pipeline.py --case /input/case.json --out /app/output --workdir /app/work
本地合成示例：
    python3 pipeline.py --case ../examples/case.json --roots ../examples/corpus \
        --out ../examples/run_out/output --workdir ../examples/run_out/work

特性：
  * 递归扫描候选根（--roots 指定 > /input > /app/work > cwd），识别
    .json/.jsonl/.csv/.tsv/.edgelist/.bib；解析 Crossref / EuropePMC /
    OpenAlex / 通用 JSON（节点含 references/citations）/ 通用边表；
  * 每条记录、每条边带 locator {file, pointer}，可回指复核；
  * DOI 规范化 + 标题规范化双键去重；两键皆缺失的记录保持独立；
  * 解析不出的引用目标保留为 stub（绝不补造作者/年份/标题）；
  * ingest 完成后立即落盘一版 honest partial result.json，扩展完成后覆盖增强；
  * 默认离线；--allow-net 仅 best-effort 占位（当前版本只记日志，不真正联网）。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

CANDIDATE_EXTS = {".json", ".jsonl", ".csv", ".tsv", ".edgelist", ".bib"}
DOI_RE = re.compile(r"^10\.\d{4,9}/", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


# ---------------------------------------------------------------- 规范化工具
def norm_doi(value) -> str:
    if not value:
        return ""
    d = str(value).strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "dx.doi.org/"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
    return d.strip().strip(".").lower()


def norm_title(value) -> str:
    if not value:
        return ""
    t = _PUNCT.sub(" ", str(value).lower())
    return _WS.sub(" ", t).strip()


def looks_like_doi(token) -> bool:
    t = str(token).strip().lower()
    return bool(DOI_RE.match(t)) or "doi.org/" in t


def make_record(doi="", title="", year=None, authors=None, venue="",
                references=None, source=None):
    return {
        "doi": norm_doi(doi),
        "title": (title or "").strip(),
        "year": year,
        "authors": [a for a in (authors or []) if a],
        "venue": (venue or "").strip(),
        "references": [str(r).strip() for r in (references or []) if str(r).strip()],
        "source": source or {"file": "", "pointer": ""},
    }


# ---------------------------------------------------------------- 各格式解析
def crossref_item_to_record(item, file, pointer):
    title = item.get("title") or item.get("short-title") or ""
    if isinstance(title, list):
        title = title[0] if title else ""
    year = None
    dp = (item.get("issued") or {}).get("date-parts")
    if dp and dp[0]:
        year = dp[0][0]
    authors = []
    for a in item.get("author", []) or []:
        if isinstance(a, dict):
            authors.append(" ".join(x for x in (a.get("given", ""), a.get("family", "")) if x).strip())
    venue = ""
    ct = item.get("container-title")
    if isinstance(ct, list) and ct:
        venue = str(ct[0])
    refs = []
    for r in item.get("reference", []) or []:
        if isinstance(r, dict):
            refs.append(r.get("DOI") or r.get("article-title") or r.get("unstructured") or "")
        else:
            refs.append(str(r))
    return make_record(item.get("DOI", ""), title, year, authors, venue, refs,
                       {"file": file, "pointer": pointer})


def europepmc_item_to_record(item, file, pointer):
    refs = []
    for r in ((item.get("referenceList") or {}).get("reference", []) or []):
        if isinstance(r, dict):
            refs.append(r.get("doi") or r.get("title") or r.get("citation") or "")
        else:
            refs.append(str(r))
    venue = ((item.get("journalInfo") or {}).get("journal") or {}).get("title", "")
    authors = [a.strip() for a in str(item.get("authorString", "")).split(",") if a.strip()]
    year = item.get("pubYear")
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = None
    return make_record(item.get("doi", ""), item.get("title", ""), year, authors, venue,
                       refs, {"file": file, "pointer": pointer})


def openalex_item_to_record(item, file, pointer):
    authorships = item.get("authorships") or []
    authors = []
    for a in authorships:
        name = ((a or {}).get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    venue = ((item.get("primary_location") or {}).get("source") or {}).get("display_name", "") or ""
    return make_record(item.get("doi", ""), item.get("display_name") or item.get("title", ""),
                       item.get("publication_year"), authors, venue,
                       item.get("referenced_works", []) or [],
                       {"file": file, "pointer": pointer})


def generic_node_to_record(node, file, pointer):
    """通用 JSON 节点：含 doi/title/references/citations 中任意字段的 dict。"""
    refs = node.get("references") or node.get("reference") or []
    if isinstance(refs, (str, dict)):
        refs = [refs]
    norm_refs = []
    for r in refs:
        if isinstance(r, dict):
            norm_refs.append(r.get("doi") or r.get("DOI") or r.get("title") or "")
        else:
            norm_refs.append(str(r))
    year = node.get("year") or node.get("pubYear") or node.get("publication_year")
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = None
    authors = node.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    return make_record(node.get("doi") or node.get("DOI", ""), node.get("title", ""),
                       year, authors, node.get("venue", "") or node.get("journal", ""),
                       norm_refs, {"file": file, "pointer": pointer})


def parse_json_obj(obj, file, pointer="$"):
    """按形态识别 JSON 对象，返回 record 列表；无法识别返回 None。"""
    if isinstance(obj, dict):
        if "message" in obj:  # Crossref
            msg = obj["message"]
            items = msg.get("items") if isinstance(msg, dict) and isinstance(msg.get("items"), list) else [msg]
            return [crossref_item_to_record(it, file, f"{pointer}.message.items[{i}]"
                    if len(items) > 1 else f"{pointer}.message")
                    for i, it in enumerate(items) if isinstance(it, dict)]
        if "resultList" in obj:  # EuropePMC
            results = (obj.get("resultList") or {}).get("result", []) or []
            return [europepmc_item_to_record(it, file, f"{pointer}.resultList.result[{i}]")
                    for i, it in enumerate(results) if isinstance(it, dict)]
        if "results" in obj and isinstance(obj["results"], list):  # OpenAlex 风格
            return [openalex_item_to_record(it, file, f"{pointer}.results[{i}]")
                    for i, it in enumerate(obj["results"]) if isinstance(it, dict)]
        if "referenced_works" in obj:  # 单条 OpenAlex work
            return [openalex_item_to_record(obj, file, pointer)]
        if any(k in obj for k in ("references", "citations", "doi", "DOI", "title")):
            return [generic_node_to_record(obj, file, pointer)]
        return None
    if isinstance(obj, list):  # 顶层数组：逐元素按通用节点/记录处理
        recs = []
        for i, it in enumerate(obj):
            if isinstance(it, dict):
                sub = parse_json_obj(it, file, f"{pointer}[{i}]")
                if sub:
                    recs.extend(sub)
        return recs or None
    return None


_BIB_ENTRY = re.compile(r"@\w+\s*\{\s*([^,]+)\s*,(.*?)\}\s*(?=@|\Z)", re.S)
_BIB_FIELD = re.compile(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,?\s*(?=\w+\s*=|$)", re.S)


def parse_bib_text(text, file):
    recs = []
    for m in _BIB_ENTRY.finditer(text):
        fields = {k.lower(): _WS.sub(" ", v).strip() for k, v in _BIB_FIELD.findall(m.group(2))}
        recs.append(make_record(fields.get("doi", ""), fields.get("title", ""),
                                fields.get("year"), [fields.get("author", "")],
                                fields.get("journal", "") or fields.get("booktitle", ""),
                                [], {"file": file, "pointer": f"@{m.group(1).strip()}"}))
    return recs


def parse_edge_table(path: Path, dialect):
    """通用边表：header 含 source/target（或 citing/cited、from/to）列。"""
    rows_out = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, dialect=dialect)
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        colmap = {}
        for want, alts in (("source", ("source", "citing", "from", "src")),
                           ("target", ("target", "cited", "to", "dst"))):
            for h in header:
                if h in alts:
                    colmap[want] = h
                    break
        if len(colmap) != 2:
            return None
        for i, row in enumerate(reader, start=2):  # 行号含表头
            low = {k.strip().lower(): v for k, v in row.items() if k}
            s, t = (low.get(colmap["source"]) or "").strip(), (low.get(colmap["target"]) or "").strip()
            if s and t:
                rows_out.append({"src": s, "dst": t,
                                 "source": {"file": str(path), "pointer": f"row {i}"}})
    return rows_out


# ---------------------------------------------------------------- 语料发现与解析
def discover_files(roots, exclude_dirs):
    found = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in CANDIDATE_EXTS:
            found.append(root.resolve())
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames
                                 if (Path(dirpath) / d).resolve() not in exclude_dirs)
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.suffix.lower() in CANDIDATE_EXTS:
                    found.append(p.resolve())
    # 去重并稳定排序（确定性输出）
    return sorted(set(found), key=lambda p: str(p))


def parse_file(path: Path):
    """返回 (records, table_edges, fmt, error)；失败不中断，error 记字符串。"""
    ext = path.suffix.lower()
    try:
        if ext == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            recs = parse_json_obj(obj, str(path))
            if recs is None:
                return [], [], "json(unsupported)", "JSON 结构不属于已知形态，跳过"
            return recs, [], "json", ""
        if ext == ".jsonl":
            recs = []
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    return recs, [], "jsonl", f"line {i}: {exc}"
                sub = parse_json_obj(obj, str(path), pointer=f"line {i}")
                if sub:
                    for r in sub:
                        r["source"]["pointer"] = f"line {i}"
                    recs.extend(sub)
            return recs, [], "jsonl", ""
        if ext in (".csv", ".tsv"):
            dialect = "excel" if ext == ".csv" else "excel-tab"
            edges = parse_edge_table(path, dialect)
            if edges is None:
                return [], [], ext[1:], "边表缺少 source/target 列，跳过"
            return [], edges, f"{ext[1:]}(edge-table)", ""
        if ext == ".edgelist":
            edges = []
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                parts = line.split()
                if len(parts) >= 2 and not line.startswith("#"):
                    edges.append({"src": parts[0], "dst": parts[1],
                                  "source": {"file": str(path), "pointer": f"line {i}"}})
            return [], edges, "edgelist", ""
        if ext == ".bib":
            return parse_bib_text(path.read_text(encoding="utf-8"), str(path)), [], "bib", ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        return [], [], ext[1:], str(exc)
    return [], [], ext[1:], "未处理的扩展名"


# ---------------------------------------------------------------- 主流程
def build_arg_parser():
    ap = argparse.ArgumentParser(description="引文追踪管线：契约优先填充 result.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", nargs="*", default=None,
                    help="语料候选根（默认顺序：/input > /app/work > cwd）")
    ap.add_argument("--max-layers", type=int, default=2, help="引用扩展层数（1–2 推荐）")
    ap.add_argument("--allow-net", action="store_true", help="best-effort 联网（当前版本仅记日志）")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    t0 = time.time()
    case_path = Path(args.case).resolve()
    out_dir = Path(args.out).resolve()
    workdir = Path(args.workdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case.get("case_id", "")
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    uncertainty = []
    if not contract:
        uncertainty.append("case.json 缺少 output_contract；result.json 仅包含最低字段集合")

    if args.allow_net:
        print("[pipeline] NOTE: --allow-net 已给定，但本版本保持离线，仅记录日志", file=sys.stderr)
        uncertainty.append("--allow-net 已请求但未执行任何网络访问（离线优先）")

    # ---- 语料候选根：--roots 指定 > /input > /app/work > cwd
    if args.roots:
        roots = [Path(r) for r in args.roots]
    else:
        roots = [p for p in (Path("/input"), Path("/app/work"), Path.cwd()) if p.exists()]
    exclude = {out_dir, workdir}
    files = [f for f in discover_files(roots, exclude) if f != case_path]
    print(f"[pipeline] roots: {[str(r) for r in roots]}")
    print(f"[pipeline] discovered {len(files)} candidate files")

    # ---- 解析 + 来源注册表
    raw_records, table_edges, sources = [], [], []
    for f in files:
        recs, edges, fmt, err = parse_file(f)
        sources.append({"file": str(f), "format": fmt, "records": len(recs),
                        "edges": len(edges),
                        "status": "failed" if err and not recs and not edges else
                                  ("partial" if err else "ok"),
                        "error": err})
        if err:
            uncertainty.append(f"来源解析问题 {f.name}: {err}")
        raw_records.extend(recs)
        table_edges.extend(edges)
    n_failed = sum(1 for s in sources if s["status"] == "failed")
    print(f"[pipeline] parsed {len(raw_records)} records, {len(table_edges)} table edges "
          f"from {len(files)} files ({n_failed} failed)")

    # ---- 身份合并：DOI 精确键 + 标题规范化键
    records, doi_index, title_index, merge_log = [], {}, {}, []
    for rec in raw_records:
        nd, nt = rec["doi"], norm_title(rec["title"])
        keep = doi_index.get(nd) if nd else None
        if keep is None and nt:
            keep = title_index.get(nt)
        if keep is None:
            rec["id"] = f"P{len(records) + 1}"
            records.append(rec)
            if nd:
                doi_index[nd] = rec["id"]
            if nt:
                title_index[nt] = rec["id"]
        else:
            kept = next(r for r in records if r["id"] == keep)
            merge_log.append({"kept": keep,
                              "merged_from": rec["source"],
                              "match_key": "doi" if nd and doi_index.get(nd) == keep else "title"})
            for fld in ("doi", "title", "year", "venue"):
                if not kept.get(fld) and rec.get(fld):
                    kept[fld] = rec[fld]
            if not kept["authors"] and rec["authors"]:
                kept["authors"] = rec["authors"]
            for ref in rec["references"]:
                if ref not in kept["references"]:
                    kept["references"].append(ref)
            nd2, nt2 = kept["doi"], norm_title(kept["title"])
            if nd2:
                doi_index.setdefault(nd2, keep)
            if nt2:
                title_index.setdefault(nt2, keep)
    if merge_log:
        uncertainty.append(f"身份合并 {len(merge_log)} 次（DOI/标题键），明细见 result.merge_log")
    print(f"[pipeline] dedup: {len(raw_records)} -> {len(records)} records "
          f"({len(merge_log)} merges)")

    by_id = {r["id"]: r for r in records}

    def resolve_ref(token):
        t = str(token).strip()
        if looks_like_doi(t):
            hit = doi_index.get(norm_doi(t))
            if hit:
                return hit
        nt = norm_title(t)
        if nt and nt in title_index:
            return title_index[nt]
        hit = doi_index.get(norm_doi(t))
        return hit

    def new_stub(token, src_locator):
        sid = f"S{sum(1 for r in records if r.get('stub')) + 1}"
        stub = make_record(doi=token if looks_like_doi(token) else "",
                           source=src_locator)
        stub.update({"id": sid, "stub": True, "unresolved_ref": str(token).strip()})
        records.append(stub)
        by_id[sid] = stub
        if stub["doi"]:
            doi_index[stub["doi"]] = sid
        return sid

    # ---- honest partial：ingest 完成立即落盘一版
    def contract_mirror(ctx, note_prefix=""):
        """按 output_contract 逐字段镜像填充；未知字段给类型空值并记 uncertainty。"""
        out = {}
        for field, decl in contract.items():
            filler = FILLERS.get(field)
            if filler is not None:
                out[field] = filler(ctx)
            else:
                out[field] = {"array": [], "object": {}, "number": 0, "boolean": False}.get(
                    str(decl).strip().lower(), "")
                ctx["extra_uncertainty"].append(
                    f"{note_prefix}自定义契约字段 {field!r} 无内置填充器，已给类型空值")
        return out

    def base_context(status, cand, edge_list, ev, layer_counts, method_summary):
        return {"case_id": case_id, "status": status, "candidates": cand,
                "edges": edge_list, "sources": sources, "evidence_records": ev,
                "uncertainty": uncertainty, "layer_counts": layer_counts,
                "method_summary": method_summary, "extra_uncertainty": uncertainty,
                "seed_view": seed_view}

    seed_view = {"id": "", "doi": "", "title": "", "found": False,
                 "source": {"file": "", "pointer": ""}}
    partial_ctx = base_context(
        "partial", [], [], [], {},
        "阶段检查点：ingest 与身份合并已完成，引用扩展尚未执行（honest partial，稍后覆盖增强）。")
    partial_ctx["uncertainty"] = uncertainty  # 共享列表，扩展阶段继续追加
    partial = dict(contract_mirror(partial_ctx, "honest partial 阶段："))
    partial.setdefault("case_id", case_id)
    partial["status"] = "partial"
    partial.setdefault("seed", seed_view)
    partial.setdefault("seed_paper", seed_view)
    partial.setdefault("candidates", [])
    partial.setdefault("edges", [])
    partial.setdefault("sources", sources)
    partial.setdefault("evidence_records", [])
    partial.setdefault("uncertainty", uncertainty)
    partial["merge_log"] = merge_log
    partial.setdefault("layer_counts", {})
    (out_dir / "result.json").write_text(
        json.dumps(partial, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[pipeline] honest partial written: {out_dir / 'result.json'}")

    # ---- 种子鲁棒解析
    seed_spec = case.get("seed_paper") or case.get("seed") or {}
    if isinstance(seed_spec, str):
        seed_spec = {"doi": seed_spec if looks_like_doi(seed_spec) else "",
                     "title": "" if looks_like_doi(seed_spec) else seed_spec}
    seed_id = None
    if seed_spec.get("doi"):
        seed_id = doi_index.get(norm_doi(seed_spec["doi"]))
    if seed_id is None and seed_spec.get("title"):
        seed_id = title_index.get(norm_title(seed_spec["title"]))
    if seed_id is None and not (seed_spec.get("doi") or seed_spec.get("title")):
        uncertainty.append("case.json 未提供可用 seed_paper（doi/title 均缺失）")
    if seed_id is not None:
        sr = by_id[seed_id]
        seed_view = {"id": sr["id"], "doi": sr["doi"], "title": sr["title"],
                     "year": sr["year"], "found": True, "source": sr["source"]}
        print(f"[pipeline] seed resolved: {seed_id} {sr['title']!r}")
    else:
        seed_view = {"id": "", "doi": seed_spec.get("doi", ""), "title": seed_spec.get("title", ""),
                     "found": False, "source": {"file": "", "pointer": ""}}
        uncertainty.append("种子论文未能在本地语料中解析；候选集为空")
        print("[pipeline] WARNING: seed not resolved in corpus", file=sys.stderr)

    # ---- 解析全部 references → 全局边与反向索引（恢复前向边）
    ref_edges = []       # citing -> cited (kind=reference)
    rev_index = {}       # cited_id -> [citing_id]
    stubs_created = 0
    for rec in list(records):
        if rec.get("stub"):
            continue
        for token in rec["references"]:
            tgt = resolve_ref(token)
            if tgt is None:
                tgt = new_stub(token, rec["source"])
                stubs_created += 1
            edge = {"source": rec["id"], "target": tgt, "kind": "reference",
                    "direction_restored": False, "locator": rec["source"]}
            ref_edges.append(edge)
            rev_index.setdefault(tgt, []).append(rec["id"])
    for te in table_edges:  # 通用边表：视为 reference 边（source 引用 target）
        s = resolve_ref(te["src"]) or new_stub(te["src"], te["source"])
        d = resolve_ref(te["dst"]) or new_stub(te["dst"], te["source"])
        ref_edges.append({"source": s, "target": d, "kind": "reference",
                          "direction_restored": False, "locator": te["source"]})
        rev_index.setdefault(d, []).append(s)
    if stubs_created:
        uncertainty.append(
            f"{stubs_created} 个引用目标无法在语料中解析，已保留为 stub（仅原始指针与定位，未补造元数据）")

    # ---- 1–max_layers 层引用扩展（BFS）
    layers, relation = {}, {}
    expansion_edges, seen_edge = [], set()

    def push_edge(src, dst, kind, restored, locator):
        key = (src, dst, kind)
        if key in seen_edge:
            return
        seen_edge.add(key)
        expansion_edges.append({"source": src, "target": dst, "kind": kind,
                                "direction_restored": restored, "locator": locator})

    layer_counts = {}
    if seed_id is not None:
        layers[seed_id] = 0
        frontier = [seed_id]
        for layer in range(1, max(1, args.max_layers) + 1):
            new_nodes = []
            for node in frontier:
                for e in ref_edges:  # 后向：citing -> cited
                    if e["source"] != node:
                        continue
                    push_edge(node, e["target"], "reference", False, e["locator"])
                    if e["target"] not in layers:
                        layers[e["target"]] = layer
                        new_nodes.append(e["target"])
                        relation[e["target"]] = f"被 {node} 列为参考文献（后向追踪，reference 边）"
                for citer in rev_index.get(node, []):  # 前向：cited -> citing（反向索引恢复）
                    loc = by_id[citer]["source"]
                    push_edge(node, citer, "citation", True, loc)
                    if citer not in layers:
                        layers[citer] = layer
                        new_nodes.append(citer)
                        relation[citer] = (f"正向引用 {node}（前向追踪，citation 边由全语料反向索引恢复，"
                                           f"direction_restored=true）")
            layer_counts[f"layer_{layer}"] = len(new_nodes)
            frontier = new_nodes

    # ---- 候选清单与证据记录
    candidates = []
    for rid, lay in sorted(layers.items(), key=lambda kv: (kv[1], kv[0])):
        if lay == 0:
            continue
        rec = by_id[rid]
        candidates.append({
            "id": rid, "doi": rec["doi"], "title": rec["title"], "year": rec["year"],
            "layer": lay, "stub": bool(rec.get("stub")),
            "relation": relation.get(rid, ""),
            "source": rec["source"],
            **({"unresolved_ref": rec["unresolved_ref"]} if rec.get("stub") else {}),
        })
    evidence_records = []
    for c in candidates:
        evidence_records.append({
            "type": "candidate", "candidate_id": c["id"],
            "claim": f"候选 {c['id']}（{c['title'] or c.get('unresolved_ref', '')}）经引用扩展在第 {c['layer']} 层发现",
            "basis": c["relation"], "locator": c["source"]})
    for e in expansion_edges:
        evidence_records.append({
            "type": "edge",
            "claim": f"引用边 {e['source']} -> {e['target']}（{e['kind']}）",
            "basis": ("数据源直接给出参考文献列表" if not e["direction_restored"]
                      else "数据源仅给参考文献列表，前向边经全语料反向索引恢复（direction_restored=true）"),
            "locator": e["locator"]})

    # ---- 状态判定与方法摘要
    if seed_id is None:
        status = "failed"
    elif candidates and not any(s["status"] == "failed" for s in sources):
        status = "ok" if not stubs_created else "partial"
    elif candidates:
        status = "partial"
    else:
        status = "partial"
    seed_title = seed_view.get("title") or seed_view.get("doi") or "(未解析)"
    method_summary = (
        f"围绕种子《{seed_title}》执行 1–{max(1, args.max_layers)} 层引用扩展："
        f"后向沿 references 边（citing→cited），前向经全语料反向索引恢复 citation 边"
        f"（cited→citing，direction_restored=true）；身份合并采用 DOI 规范化精确键＋"
        f"标题规范化键；去重后候选 {len(candidates)} 条、扩展边 {len(expansion_edges)} 条、"
        f"stub {stubs_created} 个；全部记录带 locator 可回指。")

    # ---- 按 output_contract 逐字段镜像填充（覆盖 honest partial）
    final_ctx = base_context(status, candidates, expansion_edges, evidence_records,
                             layer_counts, method_summary)
    result = dict(contract_mirror(final_ctx))
    result.setdefault("case_id", case_id)
    result["status"] = status
    result.setdefault("seed", seed_view)
    result.setdefault("seed_paper", seed_view)
    result.setdefault("candidates", candidates)
    result.setdefault("edges", expansion_edges)
    result.setdefault("sources", sources)
    result.setdefault("evidence_records", evidence_records)
    result.setdefault("uncertainty", uncertainty)
    result.setdefault("layer_counts", layer_counts)
    result["merge_log"] = merge_log
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    dt = time.time() - t0
    print(f"[pipeline] final result.json written: {out_dir / 'result.json'}")
    print(f"[pipeline] status={status} candidates={len(candidates)} "
          f"edges={len(expansion_edges)} stubs={stubs_created} merges={len(merge_log)} "
          f"elapsed={dt:.2f}s")
    return 0 if status in ("ok", "partial") else 1


# 契约字段填充器注册表（contract.py 的 FILL_PLAN 与之一一对应）
FILLERS = {
    "case_id": lambda c: c["case_id"],
    "seed_paper": lambda c: c["seed_view"],
    "seed": lambda c: c["seed_view"],
    "candidates": lambda c: c["candidates"],
    "edges": lambda c: c["edges"],
    "sources": lambda c: c["sources"],
    "evidence_records": lambda c: c["evidence_records"],
    "status": lambda c: c["status"],
    "uncertainty": lambda c: c["uncertainty"],
    "layer_counts": lambda c: c["layer_counts"],
    "method_summary": lambda c: c["method_summary"],
}


if __name__ == "__main__":
    sys.exit(main())
