#!/usr/bin/env python3
"""ingest_audit.py -- 摄入环节计数闭合审计与摄入报告生成。

读取 sniff_parse.py 的产物（records_ingested.json + ingest_ledger.json），执行：
  A1 每文件闭合：items_found == records_parsed + items_quarantined
  A2 总量闭合：ledger.totals == records 文件 totals == 实际数组长度
  A3 来源坐标完整：每条 record 有 source_file 与 source_line（>0）
  A4 字段状态登记：field_status 非空；missing-* 数量与记录一致
  A5 编码留痕：非 utf-8 或 replaced_chars>0 的文件必须在 decode_notes 有说明
  A6 重复提示登记：duplicate_hints 中每条 kept/also 都指向真实 record_id

产物：ingest_audit.json（机器可读）、ingest_report.md（人读）。
退出码：0=全部 PASS；3=存在 FAIL；2=输入产物缺失。
"""
import argparse
import json
import os
import sys


def check(name, ok, detail):
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def main():
    ap = argparse.ArgumentParser(description="摄入计数闭合审计")
    ap.add_argument("--ingest-dir", default="/app/work/ingest")
    ap.add_argument("--out", default="/app/work/ingest")
    args = ap.parse_args()

    rec_path = os.path.join(args.ingest_dir, "records_ingested.json")
    led_path = os.path.join(args.ingest_dir, "ingest_ledger.json")
    if not (os.path.isfile(rec_path) and os.path.isfile(led_path)):
        print("MISSING-INGEST-ARTIFACTS in %s" % args.ingest_dir, file=sys.stderr)
        sys.exit(2)
    records_payload = json.load(open(rec_path, encoding="utf-8"))
    ledger = json.load(open(led_path, encoding="utf-8"))
    records = records_payload["records"]
    quarantine = records_payload["quarantine"]
    checks = []

    # A1 每文件闭合
    per_file_fail = []
    for f in ledger["files"]:
        if f["items_found"] != f["records_parsed"] + f["items_quarantined"]:
            per_file_fail.append(f["source_file"])
    checks.append(check(
        "A1-per-file-closure", not per_file_fail,
        "每文件 items_found = parsed + quarantined；异常文件：%s"
        % (per_file_fail or "无")))

    # A2 总量闭合
    t_ledger = ledger["totals"]
    t_payload = records_payload["totals"]
    a2 = (t_ledger["records_parsed"] == t_payload["records_parsed"] == len(records)
          and t_ledger["items_quarantined"] == t_payload["items_quarantined"] == len(quarantine))
    checks.append(check(
        "A2-total-closure", a2,
        "ledger=%s payload=%s actual=%d/%d"
        % (t_ledger, t_payload, len(records), len(quarantine))))

    # A3 来源坐标
    bad_src = [r["record_id"] for r in records
               if not r.get("source_file") or not r.get("source_line")]
    checks.append(check("A3-provenance-coordinates", not bad_src,
                        "缺来源坐标的记录：%s" % (bad_src or "无")))

    # A4 字段状态
    bad_fs = [r["record_id"] for r in records if not r.get("field_status")]
    n_noabs = sum(1 for r in records if "missing-abstract" in r.get("field_status", []))
    n_notitle = sum(1 for r in records if "missing-title" in r.get("field_status", []))
    checks.append(check("A4-field-status", not bad_fs,
                        "field_status 缺失：%s；missing-abstract=%d missing-title=%d"
                        % (bad_fs or "无", n_noabs, n_notitle)))

    # A5 编码留痕
    enc_fail = [f["source_file"] for f in ledger["files"]
                if (f["encoding"] != "utf-8" or f["replaced_chars"] > 0)
                and not f["decode_notes"]]
    checks.append(check("A5-encoding-trace", not enc_fail,
                        "非 utf-8 或有替换字符但无 decode_notes：%s" % (enc_fail or "无")))

    # A6 重复提示指向真实记录
    ids = {r["record_id"] for r in records}
    bad_dup = [h for h in records_payload.get("duplicate_hints", [])
               if h["kept"] not in ids or h["also"] not in ids]
    checks.append(check("A6-dup-hint-integrity", not bad_dup,
                        "重复提示 %d 条；悬空引用：%s"
                        % (len(records_payload.get("duplicate_hints", [])),
                           bad_dup or "无")))

    overall = all(c["status"] == "PASS" for c in checks)
    audit = {"overall": "PASS" if overall else "FAIL", "checks": checks,
             "totals": t_payload}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "ingest_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=2)

    lines = ["# 摄入审计报告", "",
             "总体结论：**%s**" % audit["overall"], "",
             "| 检查项 | 状态 | 说明 |", "|---|---|---|"]
    for c in checks:
        lines.append("| %s | %s | %s |" % (c["check"], c["status"],
                                           c["detail"].replace("|", "\\|")))
    lines += ["", "## 总量",
              "- 文件数：%d" % t_payload["files"],
              "- 解析记录：%d" % t_payload["records_parsed"],
              "- 隔离条目：%d" % t_payload["items_quarantined"],
              "- 精确重复提示：%d" % t_payload["duplicate_hints"],
              "", "> 本报告由 ingest_audit.py 生成；计数可与 ingest_ledger.json 逐项对账。"]
    with open(os.path.join(args.out, "ingest_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("AUDIT %s (%d checks) -> %s" % (audit["overall"], len(checks), args.out))
    sys.exit(0 if overall else 3)


if __name__ == "__main__":
    main()
