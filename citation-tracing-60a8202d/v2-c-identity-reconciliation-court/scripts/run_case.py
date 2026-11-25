#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_case.py — 在合并后的实体图上做 1–2 层引用扩展并交付 result.json（第二步）。

输入：
  --case     case.json（含 case_id / seed / output_contract），默认 /input/case.json
  --workdir  identity_merge.py 的产物目录（entities.jsonl + merge_ledger.json），默认 /app/work
  --out      交付目录（result.json + merge_report.md），默认 /app/output
  --layers   扩展层数（1 或 2），默认 2

行为：
  * 鲁棒解析种子（DOI / 标题 / 对象 / 列表）；
  * 用成员记录的 references（citing→cited）与 citations（cited→citing）建实体级图；
    数据源只给参考文献列表时，用全语料反向索引恢复前向边并标 direction_restored: true；
  * 解析不出的引用目标保留为 stub（只带原始指针与定位），绝不补造元数据；
  * result.json 逐字段镜像 output_contract 全字段（含未知字段，填空并记 uncertainty）。
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from identity_merge import norm_doi, norm_title  # noqa: E402


def load_entities(workdir):
    path = Path(workdir) / "entities.jsonl"
    entities = []
    if not path.exists():
        return entities, f"缺少 {path}，请先运行 identity_merge.py"
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entities.append(json.loads(line))
        except Exception as e:  # noqa: BLE001
            return entities, f"entities.jsonl 第 {ln} 行解析失败: {e}"
    return entities, None


def load_case(case_path):
    p = Path(case_path)
    if not p.exists():
        return {}, f"case 文件不存在: {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:  # noqa: BLE001
        return {}, f"case.json 解析失败: {e}"


def resolve_seed(case, by_doi, by_title):
    """鲁棒种子解析：支持字符串 DOI / 标题、对象、列表；返回 (seeds, notes)。"""
    raw = case.get("seed") or case.get("seeds") or case.get("seed_papers") or []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    seeds, notes = [], []
    for item in raw:
        doi = title = None
        if isinstance(item, str):
            if "/" in item or item.lower().startswith(("10.", "doi", "http")):
                doi = item
            else:
                title = item
        elif isinstance(item, dict):
            doi = item.get("doi") or item.get("DOI")
            title = item.get("title")
        ent = None
        nd = norm_doi(doi)
        if nd and nd in by_doi:
            ent = by_doi[nd]
        elif title and norm_title(title) in by_title:
            ent = by_title[norm_title(title)]
        if ent:
            seeds.append(ent)
        else:
            notes.append(f"种子未在语料中解析到实体，保留为 stub: {item!r}")
            seeds.append({"entity_id": None, "stub": True, "raw": item,
                          "doi": nd, "title": title})
    return seeds, notes


def ref_pointer(member_locator, idx):
    return {"file": member_locator["file"],
            "pointer": f"{member_locator['pointer']}.references[{idx}]"}


def build_graph(entities):
    """实体级引用图。返回 (edges, stubs, by_doi, by_title, reverse_index)。"""
    by_doi, by_title = {}, {}
    for e in entities:
        for d in e.get("dois") or []:
            by_doi[d] = e
        for m in e.get("members") or []:
            t = norm_title(m.get("title"))
            if t and t not in by_title:
                by_title[t] = e

    edges, stubs, reverse_index = [], [], {}
    member_of = {}
    for e in entities:
        for m in e.get("members") or []:
            member_of[m["rec_id"]] = e["entity_id"]

    def resolve(target):
        nd = norm_doi(target) if isinstance(target, str) else None
        if nd and nd in by_doi:
            return by_doi[nd]
        nt = norm_title(target) if isinstance(target, str) else None
        if nt and nt in by_title:
            return by_title[nt]
        return None

    seen_edges = set()

    def add_edge(edge):
        key = (edge["citing"], edge["cited"], edge["kind"], edge.get("direction_restored"))
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append(edge)

    for e in entities:
        # references：citing → cited（后向）；逐成员展开以保证 locator 精确
        for m in e.get("members") or []:
            for i, raw in enumerate(m.get("references") or []):
                target = resolve(raw)
                loc = {"file": m["locator"]["file"],
                       "pointer": f"{m['locator']['pointer']}.references[{i}]"}
                if target:
                    add_edge({
                        "citing": e["entity_id"], "cited": target["entity_id"],
                        "kind": "reference", "direction": "backward",
                        "direction_restored": False,
                        "raw_pointer": raw, "source": loc,
                    })
                    reverse_index.setdefault(target["entity_id"], set()).add(e["entity_id"])
                else:
                    stubs.append({"raw_pointer": raw, "role": "cited", "citing": e["entity_id"],
                                  "source": loc,
                                  "note": "引用目标不在语料中，保留为 stub（未补造元数据）"})
            # citations：cited → citing（前向，数据源显式给出）
            for i, raw in enumerate(m.get("citations") or []):
                target = resolve(raw)
                loc = {"file": m["locator"]["file"],
                       "pointer": f"{m['locator']['pointer']}.citations[{i}]"}
                if target:
                    add_edge({
                        "citing": target["entity_id"], "cited": e["entity_id"],
                        "kind": "citation", "direction": "forward",
                        "direction_restored": False,
                        "raw_pointer": raw, "source": loc,
                    })
                else:
                    stubs.append({"raw_pointer": raw, "role": "citing", "cited": e["entity_id"],
                                  "source": loc,
                                  "note": "施引目标不在语料中，保留为 stub（未补造元数据）"})

    # 反向索引恢复前向边（数据源只给参考文献列表的情形）
    for e in entities:
        for citing_id in sorted(reverse_index.get(e["entity_id"], ())):
            add_edge({
                "citing": citing_id, "cited": e["entity_id"],
                "kind": "citation", "direction": "forward",
                "direction_restored": True,
                "note": "由全语料参考文献反向索引恢复的前向边",
                "source": {"derived_from": "references_reverse_index"},
            })
    return edges, stubs, by_doi, by_title


def bfs_expand(seed_ids, edges, layers):
    """沿边做 layers 层 BFS（前向+后向），返回 {entity_id: layer}。"""
    adj = {}
    for e in edges:
        adj.setdefault(e["citing"], set()).add(e["cited"])
        adj.setdefault(e["cited"], set()).add(e["citing"])
    layer_of = {s: 0 for s in seed_ids}
    frontier = set(seed_ids)
    for lv in range(1, layers + 1):
        nxt = set()
        for node in sorted(frontier):
            for nb in sorted(adj.get(node, ())):
                if nb not in layer_of:
                    layer_of[nb] = lv
                    nxt.add(nb)
        frontier = nxt
        if not frontier:
            break
    return layer_of


def main(argv=None):
    ap = argparse.ArgumentParser(description="实体图 1–2 层引用扩展与 result.json 交付")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--layers", type=int, default=2, choices=(1, 2))
    args = ap.parse_args(argv)

    uncertainty, evidence = [], []
    case, err = load_case(args.case)
    if err:
        uncertainty.append(err)
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    contract = case.get("output_contract") or {}
    if not isinstance(contract, dict):
        uncertainty.append("output_contract 不是对象，已按空契约处理")
        contract = {}

    entities, err = load_entities(args.workdir)
    if err:
        uncertainty.append(err)
    ledger_path = Path(args.workdir) / "merge_ledger.json"
    ledger = {}
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            uncertainty.append(f"merge_ledger.json 解析失败: {e}")
    else:
        uncertainty.append("缺少 merge_ledger.json")

    by_doi, by_title = {}, {}
    for e in entities:
        for d in e.get("dois") or []:
            by_doi[d] = e
        for m in e.get("members") or []:
            t = norm_title(m.get("title"))
            if t and t not in by_title:
                by_title[t] = e

    seeds, seed_notes = resolve_seed(case, by_doi, by_title)
    uncertainty.extend(seed_notes)
    seed_ids = [s["entity_id"] for s in seeds if not s.get("stub")]

    edges, stubs, _, _ = build_graph(entities)
    for st in stubs:
        uncertainty.append(f"stub 引用目标：{st['raw_pointer']}（{st['note']}）")

    layer_of = bfs_expand(seed_ids, edges, args.layers) if seed_ids else {}
    ent_by_id = {e["entity_id"]: e for e in entities}

    candidates = []
    for eid in sorted(layer_of, key=lambda x: (layer_of[x], x)):
        e = ent_by_id[eid]
        candidates.append({
            "entity_id": eid,
            "title": e.get("title"),
            "authors": e.get("authors"),
            "year": e.get("year"),
            "doi": e.get("doi"),
            "dois": e.get("dois"),
            "venue": e.get("venue"),
            "kind": e.get("kind"),
            "lineage": e.get("lineage"),
            "member_count": e.get("member_count"),
            "layer": layer_of[eid],
            "role": "seed" if layer_of[eid] == 0 else "expanded",
            "locators": [m["locator"] for m in e.get("members") or []],
        })
        evidence.append({
            "type": "entity_identity",
            "entity_id": eid,
            "claim": f"实体 {eid} 由 {e.get('member_count')} 条成员记录合并而成，代表记录 {e.get('representative')}",
            "locators": [m["locator"] for m in e.get("members") or []],
        })
    for ed in edges:
        evidence.append({
            "type": "citation_edge",
            "claim": f"{ed['citing']} → {ed['cited']}（{ed['kind']}"
                     f"{'，direction_restored' if ed.get('direction_restored') else ''}）",
            "source": ed.get("source"),
        })

    # 合并台账摘要
    merge_summary = {
        "stats": ledger.get("stats"),
        "merged_groups": [
            {"entity_id": g["entity_id"], "members": g["members"],
             "version_chain": g.get("version_chain"), "flags": g.get("flags")}
            for g in ledger.get("groups", []) if len(g.get("members", [])) > 1
        ],
        "review_queue": ledger.get("review_queue", []),
        "distinct_same_title": ledger.get("distinct_same_title", []),
        "same_work_different_title": ledger.get("same_work_different_title", []),
    }
    if ledger.get("review_queue"):
        uncertainty.append(
            f"存在 {len(ledger['review_queue'])} 对 review_queue 存疑合并（得分 0.6–0.85），"
            "未自动合并，需人工复核，详见 merge_ledger.json / merge_report.md")
    incomplete = [e["entity_id"] for e in entities if "incomplete_record" in (e.get("flags") or [])]
    if incomplete:
        uncertainty.append(
            f"残缺记录（缺 DOI/年份等关键字段）保持为独立实体: {', '.join(sorted(incomplete))}，"
            "未参与自动合并")
    for s in ledger.get("sources", []):
        if s.get("status") == "error":
            uncertainty.append(f"来源文件解析失败：{s['file']}（{s.get('error')}）")

    status = "ok" if seed_ids else "partial"
    if not entities:
        status = "failed" if not seed_ids else "partial"

    seed_field = [
        ({"entity_id": s["entity_id"], "doi": s.get("doi"), "title": s.get("title")}
         if not s.get("stub") else {"stub": True, "raw": s.get("raw")})
        for s in seeds
    ]

    known_fields = {
        "seed": seed_field,
        "candidates": candidates,
        "edges": edges,
        "merge_summary": merge_summary,
        "sources": ledger.get("sources", []),
        "evidence_records": evidence,
        "uncertainty": uncertainty,
        "expansion_layers": args.layers,
        "stubs": stubs,
    }
    result = {
        "case_id": case_id,
        "status": status,
        "generated_by": "run_case.py (identity-reconciliation-court, offline, stdlib)",
        "seed": seed_field,
        "candidates": candidates,
        "edges": edges,
        "sources": ledger.get("sources", []),
        "evidence_records": evidence,
        "uncertainty": uncertainty,
    }
    # 逐字段镜像 output_contract：已知字段填实，未知字段填空并交代
    for key in contract:
        if key in result:
            continue
        result[key] = known_fields.get(key)
        if key not in known_fields:
            result[key] = None
            uncertainty.append(f"output_contract 字段 '{key}' 无对应数据，按空值填充")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    result_path = outdir / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
                           encoding="utf-8")

    # 人读合并台账
    lines = [
        f"# 身份合并台账（merge report）— case {case_id}",
        "",
        f"- 状态：{status}；实体数：{len(entities)}；候选数：{len(candidates)}；边数：{len(edges)}",
        f"- 合并组数：{len(merge_summary['merged_groups'])}；"
        f"存疑对：{len(merge_summary['review_queue'])}；"
        f"同名不同文对：{len(merge_summary['distinct_same_title'])}",
        "",
        "## 合并组明细",
    ]
    for g in ledger.get("groups", []):
        lines.append(f"\n### {g['entity_id']}（成员 {len(g['members'])}，代表 {g['representative']}）")
        if g.get("flags"):
            lines.append(f"- 标记：{', '.join(g['flags'])}")
        for rid, loc in sorted(g.get("member_locators", {}).items()):
            lines.append(f"- {rid}  ← `{loc['file']}` @ `{loc['pointer']}`"
                         f"（版本：{g.get('lineage', {}).get(rid)}）")
        for p in g.get("pair_scores", []):
            lines.append(f"- 打分 {p['pair'][0]}~{p['pair'][1]}: {p['score']} → {p['decision']}")
        if g.get("conflicts"):
            lines.append(f"- 冲突字段（已保留，不丢弃）：{json.dumps(g['conflicts'], ensure_ascii=False)}")
    if merge_summary["review_queue"]:
        lines.append("\n## 存疑合并队列（review_queue，需人工复核）")
        for q in merge_summary["review_queue"]:
            lines.append(f"- {q['rec_a']} ~ {q['rec_b']}: score={q['score']}；{q['reason']}")
    if merge_summary["distinct_same_title"]:
        lines.append("\n## 同名不同文（distinct_same_title）")
        for d in merge_summary["distinct_same_title"]:
            lines.append(f"- {d['rec_a']} ≠ {d['rec_b']}：《{d['title']}》；{d['reason']}")
    if merge_summary["same_work_different_title"]:
        lines.append("\n## 同文不同名（same_work_different_title）")
        for s in merge_summary["same_work_different_title"]:
            lines.append(f"- {s['rec_a']} = {s['rec_b']}（DOI {s['doi']}）；双标题保留：{s['titles']}")
    if uncertainty:
        lines.append("\n## 不确定性 / 缺失说明")
        lines.extend(f"- {u}" for u in uncertainty)
    report_path = outdir / "merge_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": status != "failed", "status": status,
                      "candidates": len(candidates), "edges": len(edges),
                      "uncertainty": len(uncertainty),
                      "result": str(result_path), "report": str(report_path)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
