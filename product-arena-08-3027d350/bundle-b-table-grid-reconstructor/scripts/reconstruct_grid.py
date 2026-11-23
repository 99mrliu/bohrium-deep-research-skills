#!/usr/bin/env python3
"""reconstruct_grid.py — 网格重建层（表格结构重建技能 B 的第 3 步）。

把 detect_tables.py 检出的每个表格区域重建为单元格网格：
    - 空白对齐表：按共识分列位切行成格；首格为空且仅一格非空的行视为上一行
      该列的折行续接（合并进上格）；表头文字跨过分列位 → colspan；
      数据区空格不猜，标 unresolved。
    - 线框表：按 | 切分，边框行剔除；单元格空同样标 unresolved。
每个表输出三态：table_<id>.json（带坐标/合并/置信度的完整网格）、
table_<id>.md（阅读用）、table_<id>.csv（计算用）。歧义全部落盘，
不靠猜补齐。最后写 reconstruction_report.json；给 --case 时生成契约感知
result.json（含 case_id 与 output_contract 全部字段，无法填充者置空并说明）。

退出码 0=全部表重建成功；2=部分（有 unresolved 或歧义）；3=输入缺失。
"""
import argparse
import csv
import json
import os
import re
import sys


def snap_columns(cols, lines):
    """把共识分列位吸附到 [c-4, c+4] 内"最多行在该列是空白"的位置，
    保证切分不切断任何单元格文字。"""
    snapped = []
    for c in cols:
        best, best_score = c, -1
        for x in range(c - 4, c + 5):
            score = sum(1 for ln in lines
                        if 0 <= x < len(ln) and ln[x] == " ")
            if score > best_score or (score == best_score
                                      and abs(x - c) < abs(best - c)):
                best, best_score = x, score
        snapped.append(best)
    return snapped


def split_line(line, cols):
    bounds = [0] + cols + [len(line) + 1]
    return [line[bounds[k]:bounds[k + 1]].strip() for k in range(len(cols) + 1)]


def raw_span(line, cols, k):
    bounds = [0] + cols + [len(line) + 1]
    seg = line[bounds[k]:bounds[k + 1]]
    start = bounds[k] + (len(seg) - len(seg.lstrip()))
    end = bounds[k] + len(seg.rstrip())
    return start, end


def rebuild_whitespace(lines, cols):
    """返回 rows: [[cell,...]]，cell 为 dict；以及 notes。"""
    notes = []
    rows = []
    for ln_no, line in lines:
        cells = split_line(line, cols)
        if not any(cells):
            continue
        nonempty = [k for k, c in enumerate(cells) if c]
        if rows and cells[0] == "" and len(nonempty) == 1 and nonempty[0] > 0:
            k = nonempty[0]
            prev = rows[-1][k]
            prev["text"] = (prev["text"] + " " + cells[k]).strip()
            prev["wrapped"] = True
            continue
        row = []
        for k, c in enumerate(cells):
            row.append({"text": c, "row": len(rows), "col": k,
                        "rowspan": 1, "colspan": 1})
        rows.append(row)
    # 表头合并：首行单元格文字跨过分列位 → colspan
    if rows:
        head_line = lines[0][1]
        for k, cell in enumerate(rows[0]):
            if not cell["text"]:
                continue
            s, e = raw_span(head_line, cols, k)
            crossed = [c for c in cols[k:] if s < c - 2 and e > c + 2]
            if crossed:
                cell["colspan"] = 1 + len(crossed)
                cell["merged_header"] = True
                for j in range(1, cell["colspan"]):
                    if k + j < len(rows[0]):
                        rows[0][k + j]["merged_into"] = [0, k]
                        rows[0][k + j]["text"] = ""
                notes.append(f"表头 {cell['text']!r} 跨 {cell['colspan']} 列")
    # 数据区空格：不猜，标 unresolved
    for r, row in enumerate(rows):
        if r == 0:
            continue
        for cell in row:
            if not cell["text"] and "merged_into" not in cell:
                cell["unresolved"] = "空单元格：可能为纵向合并或缺失，未判定"
                notes.append(f"行 {r} 列 {cell['col']} 空单元格未判定")
    return rows, notes


def rebuild_ruled(lines):
    notes, rows = [], []
    for ln_no, line in lines:
        if re.match(r"^[\s+\-|=_]{6,}$", line):
            continue
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        row = [{"text": p, "row": len(rows), "col": k,
                "rowspan": 1, "colspan": 1} for k, p in enumerate(parts)]
        rows.append(row)
    for r, row in enumerate(rows):
        if r == 0:
            continue
        for cell in row:
            if not cell["text"]:
                cell["unresolved"] = "空单元格：未判定"
                notes.append(f"行 {r} 列 {cell['col']} 空单元格未判定")
    return rows, notes


def to_markdown(rows):
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    head = [c["text"] or ("↤合并" if "merged_into" in c else "")
            for c in rows[0]]
    out = ["| " + " | ".join(head) + " |",
           "|" + "---|" * ncols]
    for r in rows[1:]:
        out.append("| " + " | ".join(
            (c["text"] + (" ⚠" if "unresolved" in c else ""))
            + (" 〔跨%d列〕" % c["colspan"] if c.get("colspan", 1) > 1 else "")
            for c in r) + " |")
    return "\n".join(out)


def to_csv_rows(rows):
    grid = []
    for r in rows:
        grid.append([c["text"] for c in r])
    return grid


def fill_contract(case, tables_payload, out_dir, cell_notes=None):
    case_id = case.get("case_id") or case.get("id") or "unknown"
    contract = case.get("output_contract") or {}
    fields = contract.get("fields", contract) if isinstance(contract, dict) \
        else contract
    if isinstance(fields, dict):
        names = list(fields.keys())
    elif isinstance(fields, list):
        names = [x.get("name") if isinstance(x, dict) else str(x)
                 for x in fields]
    else:
        names = []
    payload, unresolved = {}, []
    for name in names:
        lname = name.lower()
        if ("table" in lname or "grid" in lname or "cell" in lname
                or "machine" in lname or "structured" in lname
                or "csv" in lname):
            payload[name] = tables_payload
        elif "provenance" in lname or "evidence" in lname:
            payload[name] = {"rule": "每表带 page 与源行区间 region，"
                                     "单元格带 row/col 与合并标记"}
        else:
            payload[name] = None
            unresolved.append(name)
    status = "success" if not unresolved and not cell_notes else "partial"
    uncertainties = []
    if unresolved:
        uncertainties += [f"契约字段 {n} 无可靠填充来源，如实置空"
                          for n in unresolved]
    if cell_notes:
        uncertainties += [f"单元格歧义（共 {len(cell_notes)} 条，详见 "
                          "reconstruction_report.json）：" + n
                          for n in cell_notes[:10]]
        if len(cell_notes) > 10:
            uncertainties.append(f"……其余 {len(cell_notes) - 10} 条见报告")
    result = {
        "case_id": case_id, "status": status, "result": payload,
        "evidence": {"tables_index": "tables_index.json",
                     "reconstruction_report": "reconstruction_report.json"},
        "uncertainty": uncertainties,
        "sources": ["tables_index.json"],
        "change_record": ["extract_layout → detect_tables → reconstruct_grid"],
    }
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return status, unresolved


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", required=True, help="tables_index.json")
    ap.add_argument("--pages", required=True, help="pages/ 目录")
    ap.add_argument("--case", help="/input/case.json")
    ap.add_argument("--out", required=True, help="/app/output")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not os.path.exists(args.index):
        print(json.dumps({"status": "failed", "reason": "index_missing"}))
        return 3
    tables = json.load(open(args.index, encoding="utf-8"))
    if not tables:
        print(json.dumps({"status": "partial", "reason": "no_tables"}))
        return 2

    all_notes, payloads = [], []
    worst = 0
    for t in tables:
        page_path = os.path.join(args.pages, f"page{t['page']:02d}.txt")
        if not os.path.exists(page_path):
            all_notes.append(f"{t['table_id']}: 缺页文本，跳过")
            worst = 2
            continue
        with open(page_path, encoding="utf-8") as f:
            page_lines = f.read().splitlines()
        s, e = t["region"]
        region_lines = [(k, page_lines[k]) for k in range(s, e + 1)
                        if k < len(page_lines)]
        if t["kind"] == "ruled":
            rows, notes = rebuild_ruled(region_lines)
        else:
            snapped = snap_columns(t["columns"],
                                   [ln for _, ln in region_lines])
            rows, notes = rebuild_whitespace(region_lines, snapped)
        all_notes.extend(f"{t['table_id']}: {n}" for n in notes)
        if notes:
            worst = 2
        grid = {"table_id": t["table_id"], "page": t["page"],
                "caption": t["caption"], "kind": t["kind"],
                "source_region": t["region"],
                "confidence": t["confidence"],
                "n_rows": len(rows),
                "n_cols": max((len(r) for r in rows), default=0),
                "rows": rows}
        tid = re.sub(r"[^\w.-]", "_", str(t["table_id"]))
        with open(os.path.join(args.out, f"table_{tid}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(grid, f, ensure_ascii=False, indent=2)
        with open(os.path.join(args.out, f"table_{tid}.md"), "w",
                  encoding="utf-8") as f:
            f.write(f"<!-- 表格重建结果；⚠=未判定单元格 -->\n\n"
                    f"**{t.get('caption') or tid}**（第 {t['page']} 页，"
                    f"源行 {t['region']}）\n\n" + to_markdown(rows) + "\n")
        with open(os.path.join(args.out, f"table_{tid}.csv"), "w",
                  encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(to_csv_rows(rows))
        payloads.append({"table_id": t["table_id"], "page": t["page"],
                         "json": f"table_{tid}.json",
                         "markdown": f"table_{tid}.md",
                         "csv": f"table_{tid}.csv",
                         "n_rows": grid["n_rows"], "n_cols": grid["n_cols"],
                         "notes": notes})

    report = {"status": "ok" if worst == 0 else "partial",
              "tables": len(payloads), "notes": all_notes}
    with open(os.path.join(args.out, "reconstruction_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    status = report["status"]
    unresolved_contract = []
    if args.case:
        case = json.load(open(args.case, encoding="utf-8"))
        cstatus, unresolved_contract = fill_contract(
            case, payloads, args.out, cell_notes=all_notes)
        if cstatus == "partial":
            status = "partial"
    print(json.dumps({"status": status, "tables": len(payloads),
                      "notes": len(all_notes),
                      "contract_unresolved": unresolved_contract},
                     ensure_ascii=False))
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
