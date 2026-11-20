#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_chain.py — 链完整性核验：四条链任何一处断开都显式报告，绝不静默修补。

核验项：
  C1 字段可回链：lineage.jsonl 每条记录的每个字段、以及 canonical_records.json
     每个 canonical 字段，其 raw_pointer 都必须能在真实响应文件中解析，
     且解析值与 raw_excerpt 一致（前缀截断比较）。
  C2 item 全处置：每个原始响应文件的每个 item 要么被采用（dedup_decision 含
     canonical），要么被丢弃且原因码 ∈ {duplicate_of, relevance_excluded,
     unparsed, withdrawn}。
  C3 台账页存在：query_ledger.jsonl 中每个 response_file 都在磁盘上存在。
  C4 确定性重放：同一输入双跑 build_lineage.py（脚本内自动执行），
     lineage.jsonl + canonical_records.json 的 SHA-256 必须一致。

断链逐条写入 chain_gaps.jsonl（gap_type/record_uid/pointer/detail），并输出
verify_report.json 汇总；--report 可按模板渲染 lineage_report.md。

退出码：0=四项核验全过（无断链）；2=输入缺失（无 lineage/台账，诚实降级）；
3=发现断链或重放不一致（校验失败）。顶层异常汇总并以 exit 2 降级。

用法：
  python3 verify_chain.py [--summary /app/work/case_summary.json]
      [--work /app/work] [--exclusions FILE] [--report /app/output/lineage_report.md]
      [--template <skill>/templates/lineage_report.md] [--import-diff FILE]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

DISCARD_REASONS = {"duplicate_of", "relevance_excluded", "unparsed",
                   "withdrawn"}
EXCERPT_MAX = 200


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path):
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    yield json.loads(ln)
                except json.JSONDecodeError:
                    yield {"_bad_line": ln[:80]}


def split_pointer(ptr):
    out = []
    for seg in str(ptr).split("."):
        m = re.match(r"^([^\[\]]+)((?:\[\d+\])*)$", seg)
        if not m:
            out.append((seg, None))
            continue
        out.append((m.group(1), None))
        for i in re.findall(r"\[(\d+)\]", m.group(2)):
            out.append((None, int(i)))
    return out


def resolve_pointer(obj, ptr, raw_text):
    """解析 raw_pointer；支持 JSON 路径 / line[i].k / row[i].k / char[s:e]。"""
    ptr = str(ptr)
    m = re.match(r"^char\[(\d+):(\d+)\]$", ptr)
    if m:
        return raw_text[int(m.group(1)):int(m.group(2))]
    steps = split_pointer(ptr)
    cur = obj
    for name, idx in steps:
        if name in ("line", "row") and idx is None:
            continue
        if name is not None:
            if not isinstance(cur, dict) or name not in cur:
                raise KeyError(name)
            cur = cur[name]
        else:
            if not isinstance(cur, list) or idx >= len(cur):
                raise IndexError(idx)
            cur = cur[idx]
    return cur


def load_root_for_pointer(path, ptr):
    """按指针根类型加载可解析对象。返回 (obj, raw_text)。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    ptr = str(ptr)
    if ptr.startswith("line["):
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        return [json.loads(ln) for ln in lines], raw
    if ptr.startswith("row["):
        import csv as _csv
        import io
        return list(_csv.DictReader(io.StringIO(raw))), raw
    try:
        return json.loads(raw), raw
    except (json.JSONDecodeError, ValueError):
        return None, raw


def adapt_line_row_pointer(obj, ptr):
    """line[3].doi → 对 obj(list) 先取 [3]，再走 doi。"""
    steps = split_pointer(ptr)
    cur = obj
    for name, idx in steps:
        if name in ("line", "row"):
            continue
        if name is not None:
            if not isinstance(cur, dict) or name not in cur:
                raise KeyError(name)
            cur = cur[name]
        else:
            if not isinstance(cur, list) or idx >= len(cur):
                raise IndexError(idx)
            cur = cur[idx]
    return cur


def check_pointer(path, ptr, excerpt):
    """返回 None（通过）或断链细节字符串。"""
    try:
        obj, raw = load_root_for_pointer(path, ptr)
    except Exception as e:
        return "response_parse_error: %r" % e
    try:
        if re.match(r"^char\[\d+:\d+\]$", str(ptr)):
            val = resolve_pointer(None, ptr, raw)
        elif str(ptr).startswith(("line[", "row[")):
            val = adapt_line_row_pointer(obj, ptr)
        else:
            val = resolve_pointer(obj, ptr, raw)
    except (KeyError, IndexError, TypeError) as e:
        return "pointer_unresolvable: %r" % e
    sval = str(val)
    if excerpt is not None and sval[:EXCERPT_MAX] != str(excerpt):
        return "value_mismatch: 解析值 %r 与 raw_excerpt %r 不一致" % (
            sval[:60], str(excerpt)[:60])
    return None


# ---------------------------------------------------------------- 报告渲染

def md_table(headers, rows):
    if not rows:
        return "（无）"
    out = ["| " + " | ".join(headers) + " |",
           "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def render_report(template_path, out_path, ctx):
    with open(template_path, "r", encoding="utf-8") as f:
        text = f.read()
    for k, v in ctx.items():
        text = text.replace("{{%s}}" % k, str(v))
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if leftover:
        text += "\n\n> 渲染警告：模板占位符未被填充: %s\n" % ", ".join(
            sorted(set(leftover)))
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)


def main_inner(args):
    if not os.path.isfile(args.summary):
        print("ERROR: case_summary 不存在（材料不足）: %s" % args.summary,
              file=sys.stderr)
        return 2
    try:
        summary = load_json(args.summary)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3

    lin_path = os.path.join(args.work, "lineage.jsonl")
    can_path = os.path.join(args.work, "canonical_records.json")
    if not os.path.isfile(lin_path) or not os.path.isfile(can_path):
        print("ERROR: lineage.jsonl / canonical_records.json 缺失，请先运行 "
              "build_lineage.py（材料不足，诚实降级）。", file=sys.stderr)
        return 2

    lineage = [r for r in iter_jsonl(lin_path) if isinstance(r, dict)]
    canon = load_json(can_path)
    by_uid = {r.get("record_uid"): r for r in lineage}
    mat_by_name = {m.get("file"): m for m in summary.get("materials") or []}
    gaps = []

    def gap(gtype, **kw):
        g = {"gap_id": "G%03d" % (len(gaps) + 1), "gap_type": gtype}
        g.update(kw)
        gaps.append(g)

    # ---- C1 字段可回链 ----
    def trace(uid, field, fx):
        m = mat_by_name.get(fx.get("_file"))
        ptr, excerpt = fx.get("raw_pointer"), fx.get("raw_excerpt")
        if not m or not ptr:
            gap("field_pointer_missing", record_uid=uid, field=field,
                pointer=ptr, detail="无 raw_pointer 或响应文件未登记")
            return
        detail = check_pointer(m["path"], ptr, excerpt)
        if detail:
            gap("field_chain_broken", record_uid=uid, field=field,
                pointer=ptr, detail=detail)

    for r in lineage:
        for f, fx in sorted((r.get("field_extractions") or {}).items()):
            fx = dict(fx)
            fx["_file"] = r.get("response_file")
            trace(r.get("record_uid"), f, fx)
    for c in canon.get("canonicals") or []:
        for f, fx in sorted((c.get("fields") or {}).items()):
            src = fx.get("from_record")
            fx = dict(fx)
            fx["_file"] = (by_uid.get(src) or {}).get("response_file")
            trace(c.get("canonical_id"), f, fx)

    # ---- C2 item 全处置 ----
    for m in summary.get("materials") or []:
        if m.get("sniff") not in ("crossref", "europepmc", "publisher",
                                  "recordlist", "jsonl", "csv"):
            continue
        n = m.get("item_count")
        if not isinstance(n, int):
            continue
        for i in range(n):
            uid = "%s:%s:item[%d]" % (m["sniff"], m["file"], i)
            r = by_uid.get(uid)
            if r is None:
                gap("item_undisposed", record_uid=uid,
                    detail="lineage 中无此 item 的任何处置记录")
                continue
            adopted = bool((r.get("dedup_decision") or {}).get("canonical"))
            disc = r.get("discard") or {}
            if not adopted and disc.get("reason_code") not in DISCARD_REASONS:
                gap("item_undisposed", record_uid=uid,
                    detail="既未采用亦无合法丢弃原因码（got=%r）"
                           % disc.get("reason_code"))

    # ---- C3 台账页存在 ----
    ledger_entries = list(iter_jsonl(os.path.join(args.work,
                                                  "query_ledger.jsonl")))
    for e in ledger_entries:
        rf = e.get("response_file")
        if not rf:
            continue
        m = mat_by_name.get(rf)
        if not m or not os.path.isfile(m.get("path") or ""):
            gap("response_file_missing", query_id=e.get("query_id"),
                response_file=rf, detail="台账登记的响应文件在磁盘上不存在")

    # ---- C4 确定性重放（双跑 hash 比对）----
    build = args.build_script or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "build_lineage.py")
    hashes = []
    for run_no in (1, 2):
        with tempfile.TemporaryDirectory(
                prefix="querytrace_replay%d_" % run_no) as td:
            cmd = [sys.executable, build, "--summary", args.summary,
                   "--work", td]
            if args.exclusions:
                cmd += ["--exclusions", args.exclusions]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                gap("replay_build_failed", detail="重放第 %d 跑 exit=%d: %s"
                    % (run_no, p.returncode, (p.stderr or "")[-200:]))
                continue
            h = hashlib.sha256()
            for fn in ("lineage.jsonl", "canonical_records.json"):
                with open(os.path.join(td, fn), "rb") as f:
                    h.update(f.read())
            hashes.append(h.hexdigest())
    replay_ok = len(hashes) == 2 and hashes[0] == hashes[1]
    if len(hashes) == 2 and hashes[0] != hashes[1]:
        gap("nondeterministic_replay",
            detail="同一输入双跑输出 hash 不一致: %s vs %s"
                   % (hashes[0][:16], hashes[1][:16]))

    # ---- 输出 ----
    gaps_path = os.path.join(args.work, "chain_gaps.jsonl")
    with open(gaps_path, "w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False, sort_keys=True) + "\n")
    report = {
        "checks": {
            "C1_field_traceability": "pass" if not any(
                g["gap_type"].startswith("field_") for g in gaps) else "fail",
            "C2_item_disposition": "pass" if not any(
                g["gap_type"] == "item_undisposed" for g in gaps) else "fail",
            "C3_ledger_pages_exist": "pass" if not any(
                g["gap_type"] == "response_file_missing"
                for g in gaps) else "fail",
            "C4_deterministic_replay": "pass" if replay_ok else "fail",
        },
        "gap_count": len(gaps),
        "replay_hash": hashes[0] if replay_ok else None,
    }
    rep_path = os.path.join(args.work, "verify_report.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)

    if args.report:
        qrows = [[e.get("query_id"), e.get("source_db"),
                  (e.get("query_text") or "（query_unrecorded）")[:60],
                  e.get("total_hits") if e.get("total_hits") is not None else "-",
                  e.get("items_returned")
                  if e.get("items_returned") is not None else "-",
                  e.get("response_file") or "-"]
                 for e in ledger_entries]
        crows = []
        for c in canon.get("canonicals") or []:
            f_ = c.get("fields") or {}
            ident = (f_.get("doi") or f_.get("pmid") or {}).get("value", "-")
            crows.append([c.get("canonical_id"), c.get("cluster_basis"),
                          str(ident)[:40],
                          (f_.get("title") or {}).get("value", "-")[:60],
                          ", ".join(c.get("members") or [])])
        grows = [[g.get("gap_id"), g.get("gap_type"),
                  g.get("record_uid") or g.get("query_id") or "-",
                  str(g.get("detail"))[:80]] for g in gaps] or []
        audit = {}
        apath = os.path.join(args.work, "query_audit.json")
        if os.path.isfile(apath):
            try:
                audit = load_json(apath)
            except Exception:
                audit = {}
        pag = audit.get("pagination") or []
        idiff_txt = "（未运行 import_diff.py 或无导入状态材料）"
        if args.import_diff and os.path.isfile(args.import_diff):
            try:
                idiff = load_json(args.import_diff)
                cl = idiff.get("classes") or {}
                idiff_txt = "\n".join(
                    "- **%s**：%d 条" % (k, len(v)) for k, v in
                    sorted(cl.items()))
            except Exception:
                pass
        ctx = {
            "CASE_ID": summary.get("case_id", "unknown-case"),
            "SKILL_NAME": "querytrace-lineage-chain",
            "STATUS": "pass" if not gaps else "fail(%d gaps)" % len(gaps),
            "QUERY_LEDGER_TABLE": md_table(
                ["query_id", "source_db", "query_text", "total_hits",
                 "items_returned", "response_file"], qrows),
            "AUDIT_MECHANICAL": (audit.get("mechanical_copy") or {}).get(
                "verdict", "（无审计数据）"),
            "AUDIT_PAGINATION": "\n".join(
                "- %s: %s（pages=%d, returned=%s, total=%s）"
                % (p.get("source_db"), p.get("status"), p.get("pages"),
                   p.get("returned_sum"), p.get("total_hits"))
                for p in pag) or "（无审计数据）",
            "AUDIT_RATELIMIT": "\n".join(
                "- %s: %s %s" % (db, v.get("classification"),
                                 v.get("matched_patterns"))
                for db, v in sorted(
                    (audit.get("rate_limit") or {}).items())) or "（无审计数据）",
            "CANONICAL_TABLE": md_table(
                ["canonical_id", "cluster_basis", "identifier", "title",
                 "members"], crows),
            "UNRESOLVED_PAIRS": json.dumps(
                canon.get("unresolved_pairs") or [], ensure_ascii=False,
                indent=2),
            "CHAIN_GAPS": md_table(["gap_id", "gap_type", "object", "detail"],
                                   grows),
            "IMPORT_DIFF": idiff_txt,
            "REPLAY_STATEMENT": (
                "确定性重放双跑 hash 一致（SHA-256 前缀 %s），同输入同输出。"
                % hashes[0][:16]) if replay_ok else
                "重放不一致或重放失败，详见 chain_gaps.jsonl。",
        }
        render_report(args.template, args.report, ctx)
        print("OK: lineage_report 已渲染 -> %s" % args.report)

    print("OK: verify_report -> %s (gaps=%d, replay=%s)"
          % (rep_path, len(gaps), "consistent" if replay_ok else "INCONSISTENT"))
    for g in gaps:
        print("GAP: %s %s %s" % (g["gap_id"], g["gap_type"],
                                 str(g.get("detail"))[:120]), file=sys.stderr)
    return 0 if not gaps else 3


def main():
    ap = argparse.ArgumentParser(
        description="链完整性四核验 + 确定性重放双跑（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--exclusions", default=None,
                    help="重放时透传给 build_lineage.py 的排除文件")
    ap.add_argument("--report", default=None, help="渲染 lineage_report.md 的路径")
    ap.add_argument("--template",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "templates", "lineage_report.md"))
    ap.add_argument("--import-diff", default=None, help="import_diff.json 路径（可选）")
    ap.add_argument("--build-script", default=None,
                    help="build_lineage.py 路径（默认取同目录）")
    args = ap.parse_args()
    try:
        return main_inner(args)
    except Exception as e:
        print("ERROR: 未捕获异常，诚实降级 exit 2: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
