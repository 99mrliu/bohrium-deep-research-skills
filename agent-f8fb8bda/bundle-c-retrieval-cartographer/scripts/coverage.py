#!/usr/bin/env python3
"""coverage.py — 覆盖矩阵与研究空白导出（只从检索记录导出）。

读 search_log.jsonl，每行：
    {"action_id": ..., "sq_ids": [...], "query": ..., "source": ...,
     "hits": [{"dedup_key": ..., "title": ..., "relevant": true/false}, ...]}

处理：
    1. 全局按 dedup_key 去重；重复命中计入 dupes_skipped。
    2. 输出 coverage_matrix.json：每个 SQ × source 的相关命中数；
       SQ 状态：met（≥3）/ unmet（1-2）/ searched_absent（检索过但 0 条相关）
       / not_searched（无任何检索记录）；并给出每 SQ 最后一轮新增相关数
       作为饱和度信号。
    3. 输出 research_gaps.json：高置信缺口仅允许来自 searched_absent 的 SQ；
       not_searched 的 SQ 一律 not_assessable；unmet 仅列为 low_coverage，
       不得声称为研究空白。
    4. --gaps-file 可选：校验 Agent 撰写的空白条目。凡声称"未见/缺乏 X 研究"
       的条目必须引用至少一个 searched_absent 的 SQ，且不得引用任何
       非 searched_absent 的 SQ，否则 exit 1（防止凭空写空白）。

退出码：
    0  成功（含 --gaps-file 校验通过）
    1  --gaps-file 校验违例（stdout 逐项清单）
    2  用法 / IO / JSON 解析错误
"""
import argparse
import json
import os
import re
import sys

ABSENCE_RE = re.compile(
    r"未见|缺乏|缺少|缺失|没有(?:相关|相应)?(?:研究|报道|文献|证据)|无相关|尚未见"
    r"|研究空白|存在.{0,6}空白"
    r"|no\s+(?:stud|research|evidence|report)|lack(?:s|ing)?\s+of|absen"
    r"|few\s+stud|research\s+gap",
    re.IGNORECASE,
)
SQ_REF_RE = re.compile(r"SQ-\d+", re.IGNORECASE)
ENTRY_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def norm_title(title):
    return re.sub(r"\s+", " ", str(title).lower()).strip()[:40]


def hit_key(hit):
    dk = hit.get("dedup_key")
    if isinstance(dk, str) and dk.strip():
        return dk.strip()
    return "title:" + norm_title(hit.get("title", ""))


def load_decomp_sqs(path):
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    sqs = []
    if isinstance(data, dict) and isinstance(data.get("sub_questions"), list):
        for sq in data["sub_questions"]:
            if isinstance(sq, dict) and sq.get("id"):
                sqs.append(str(sq["id"]))
    return sqs


def write_json(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(description="覆盖矩阵与研究空白导出")
    parser.add_argument("--log", default="/app/work/search_log.jsonl",
                        help="search_log.jsonl 路径")
    parser.add_argument("--decomp", default="/app/output/decomposition.json",
                        help="decomposition.json 路径（提供 SQ 全集；缺失时 SQ 全集 "
                             "取检索记录中出现的并集）")
    parser.add_argument("--out-dir", default="/app/output", help="产物输出目录")
    parser.add_argument("--gaps-file", default=None,
                        help="可选：Agent 撰写的研究空白条目文件（md/txt），"
                             "声称空白的条目必须映射到 searched_absent 的 SQ")
    parser.add_argument("--met-threshold", type=int, default=3,
                        help="SQ 达标相关命中数阈值（默认 3）")
    args = parser.parse_args()

    if not os.path.isfile(args.log):
        print("[ERROR] 检索记录不存在：%s" % args.log, file=sys.stderr)
        return 2

    # ---- 解析 JSONL -------------------------------------------------------
    entries = []
    try:
        with open(args.log, "r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    print("[ERROR] 第 %d 行 JSON 解析失败：%s" % (lineno, exc),
                          file=sys.stderr)
                    return 2
                if not isinstance(obj, dict):
                    print("[ERROR] 第 %d 行不是 JSON 对象" % lineno, file=sys.stderr)
                    return 2
                entries.append((lineno, obj))
    except OSError as exc:
        print("[ERROR] 检索记录读取失败：%s" % exc, file=sys.stderr)
        return 2

    # ---- SQ 全集 -----------------------------------------------------------
    sq_universe = load_decomp_sqs(args.decomp)
    for _, obj in entries:
        ids = obj.get("sq_ids")
        if ids is None and obj.get("sq_id") is not None:
            ids = [obj["sq_id"]]
        for sid in (ids or []):
            sid = str(sid)
            if sid not in sq_universe:
                sq_universe.append(sid)

    def new_stat():
        return {
            "searched": False,
            "sources": {},
            "sources_searched": [],
            "relevant_total": 0,
            "seen_keys": set(),
            "last_entry_index": -1,
            "last_entry_new_relevant": 0,
            "actions": [],
        }

    stats = {sid: new_stat() for sid in sq_universe}

    global_seen = set()
    dupes_skipped = 0
    total_hits = 0
    total_relevant_kept = 0

    for idx, (lineno, obj) in enumerate(entries):
        ids = obj.get("sq_ids")
        if ids is None and obj.get("sq_id") is not None:
            ids = [obj["sq_id"]]
        ids = [str(x) for x in (ids or [])]
        source = str(obj.get("source", "UNKNOWN_SOURCE"))
        hits = obj.get("hits", [])
        if not isinstance(hits, list):
            print("[ERROR] 第 %d 行 hits 不是列表" % lineno, file=sys.stderr)
            return 2
        action_id = str(obj.get("action_id", "line-%d" % lineno))

        kept = []  # (key, relevant) 本轮全局去重后保留
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            total_hits += 1
            key = hit_key(hit)
            if key in global_seen:
                dupes_skipped += 1
                continue
            global_seen.add(key)
            relevant = bool(hit.get("relevant"))
            kept.append((key, relevant))
            if relevant:
                total_relevant_kept += 1

        for sid in ids:
            st = stats.setdefault(sid, new_stat())
            st["searched"] = True
            st["actions"].append(action_id)
            if source not in st["sources_searched"]:
                st["sources_searched"].append(source)
            st["last_entry_index"] = idx
            new_rel = 0
            for key, relevant in kept:
                if not relevant:
                    continue
                st["sources"][source] = st["sources"].get(source, 0) + 1
                st["relevant_total"] += 1
                if key not in st["seen_keys"]:
                    new_rel += 1
                st["seen_keys"].add(key)
            st["last_entry_new_relevant"] = new_rel

    thr = args.met_threshold

    def status_of(st):
        if not st["searched"]:
            return "not_searched"
        if st["relevant_total"] >= thr:
            return "met"
        if st["relevant_total"] == 0:
            return "searched_absent"
        return "unmet"

    # ---- coverage_matrix.json ---------------------------------------------
    sq_blocks = {}
    all_sources = sorted({src for st in stats.values() for src in st["sources"]})
    for sid in sq_universe:
        st = stats[sid]
        sq_blocks[sid] = {
            "status": status_of(st),
            "relevant_total": st["relevant_total"],
            "by_source": {src: st["sources"].get(src, 0) for src in all_sources},
            "sources_searched": st["sources_searched"],
            "actions": st["actions"],
            "saturation": {
                "new_relevant_last_action": st["last_entry_new_relevant"],
                "signal": ("not_searched" if not st["searched"]
                           else "saturated" if st["last_entry_new_relevant"] == 0
                           else "active"),
            },
        }
    summary = {"met": 0, "unmet": 0, "searched_absent": 0, "not_searched": 0}
    for sid in sq_universe:
        summary[sq_blocks[sid]["status"]] += 1
    coverage = {
        "met_threshold": thr,
        "sources": all_sources,
        "sq_count": len(sq_universe),
        "summary": summary,
        "totals": {
            "log_entries": len(entries),
            "hits_total": total_hits,
            "relevant_kept": total_relevant_kept,
            "dupes_skipped": dupes_skipped,
        },
        "sq_status": sq_blocks,
        "status_definitions": {
            "met": "检索过且去重后相关命中 ≥ met_threshold",
            "unmet": "检索过但相关命中 1..met_threshold-1（覆盖不足，非空白证据）",
            "searched_absent": "检索过且相关命中为 0（唯一允许导出高置信空白的状态）",
            "not_searched": "无任何检索记录（不可评估，严禁声称空白）",
        },
    }

    # ---- research_gaps.json -------------------------------------------------
    gaps = {
        "rule": "高置信缺口仅允许来自 searched_absent 的 SQ；not_searched 一律 "
                "not_assessable；unmet 仅为 low_coverage，不得声称为研究空白。",
        "high_confidence_gaps": [],
        "not_assessable": [],
        "low_coverage": [],
    }
    for sid in sq_universe:
        blk = sq_blocks[sid]
        if blk["status"] == "searched_absent":
            gaps["high_confidence_gaps"].append({
                "sq_id": sid,
                "type": "searched_absent",
                "basis": {
                    "actions": blk["actions"],
                    "sources_searched": blk["sources_searched"],
                    "relevant_total": 0,
                },
                "statement_hint": "已按计划检索但相关命中为 0，可据此声称高置信缺口。",
            })
        elif blk["status"] == "not_searched":
            gaps["not_assessable"].append({
                "sq_id": sid,
                "reason": "not_searched：搜过没有 ≠ 没搜过；未检索方向严禁声称空白。",
            })
        elif blk["status"] == "unmet":
            gaps["low_coverage"].append({
                "sq_id": sid,
                "relevant_total": blk["relevant_total"],
                "note": "覆盖不足（< %d 条相关），证据不够，不能判定为研究空白。" % thr,
            })

    try:
        cov_path = os.path.join(args.out_dir, "coverage_matrix.json")
        gap_path = os.path.join(args.out_dir, "research_gaps.json")
        write_json(cov_path, coverage)
        write_json(gap_path, gaps)
    except OSError as exc:
        print("[ERROR] 产物写入失败：%s" % exc, file=sys.stderr)
        return 2

    print("[OK] coverage_matrix.json -> %s" % os.path.abspath(cov_path))
    print("[OK] research_gaps.json  -> %s" % os.path.abspath(gap_path))
    print("[OK] SQ 状态汇总：met=%d unmet=%d searched_absent=%d not_searched=%d；"
          "dupes_skipped=%d" % (summary["met"], summary["unmet"],
                                summary["searched_absent"], summary["not_searched"],
                                dupes_skipped))

    # ---- --gaps-file 校验 ---------------------------------------------------
    if args.gaps_file is not None:
        if not os.path.isfile(args.gaps_file):
            print("[ERROR] gaps 文件不存在：%s" % args.gaps_file, file=sys.stderr)
            return 2
        try:
            with open(args.gaps_file, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            print("[ERROR] gaps 文件读取失败：%s" % exc, file=sys.stderr)
            return 2
        searched_absent = {sid for sid in sq_universe
                           if sq_blocks[sid]["status"] == "searched_absent"}
        violations = []
        n_entries = 0
        n_claims = 0
        for lineno, line in enumerate(lines, start=1):
            if not ENTRY_RE.match(line):
                continue
            n_entries += 1
            if not ABSENCE_RE.search(line):
                continue
            n_claims += 1
            refs = {r.upper() for r in SQ_REF_RE.findall(line)}
            ok_refs = refs & searched_absent
            bad_refs = refs - searched_absent
            if not ok_refs or bad_refs:
                reason = []
                if not ok_refs:
                    reason.append("未引用任何 searched_absent 的 SQ")
                if bad_refs:
                    reason.append("引用了非 searched_absent 的 SQ：%s"
                                  % ", ".join(sorted(bad_refs)))
                violations.append("第 %d 行：%s（%s）"
                                  % (lineno, line.strip()[:80], "；".join(reason)))
        if violations:
            print("GAPS GATE FAILED：声称空白的条目必须且只能映射到 "
                  "searched_absent 的 SQ（当前 searched_absent：%s）"
                  % (", ".join(sorted(searched_absent)) or "无"))
            for v in violations:
                print("[GAP] %s" % v)
            return 1
        print("[OK] gaps 文件校验通过（条目 %d 条，空白声称 %d 条，"
              "均映射到 searched_absent）" % (n_entries, n_claims))
    return 0


if __name__ == "__main__":
    sys.exit(main())
