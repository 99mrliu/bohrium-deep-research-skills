#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selfcheck.py — 对 scripts/ 全部工具在合成 fixtures 上执行端到端自检。

断言覆盖:
  1. 每种日期格式解析正确（ISO/美式长式/欧式长式/中文/紧凑/月/年）；
  2. 歧义数字日期 → 两种解释 + 歧义警告（绝不静默取舍）；
  3. 无法解析字符串 → 保留原文 + 警告（退出码 1，绝不猜测）；
  4. OCR 混淆日期：keep-raw 保留原文 + 疑似警告；fix-digit-confusion 按声明策略修复；
  5. 事件抽取：口径分类正确，unknown 事件带警告；
  6. 时间轴：授权日早于申请日的顺序冲突被检测（退出码 1）；
  7. 观测同族：优先权日冲突被检测；一致时报告 consistent；
  8. 估算器：护栏字段齐全（is_estimate/not_legal_status/assumptions/as_of）；
  9. 估算器缺少 as_of → 拒绝（退出码 1）；
 10. 估算器 --self-test 通过；输出无禁用措辞。

退出码: 0 全部通过（打印摘要） / 1 存在失败项 / 2 用法错误
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
FIXTURES = os.path.join(ROOT, "examples", "fixtures")

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                         (" — " + detail) if detail and not cond else ""))


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                          capture_output=True, text=True)


def run_json(script, *args):
    p = run(script, *args)
    try:
        return p, json.loads(p.stdout)
    except json.JSONDecodeError:
        return p, None


def main():
    tmp = tempfile.mkdtemp(prefix="chronology_selfcheck_")

    # ---- 1. 各格式解析 -------------------------------------------------
    cases = [
        ("2018-06-05", "2018-06-05", "iso8601", "day"),
        ("Jun. 5, 2018", "2018-06-05", "us_long", "day"),
        ("5 June 2018", "2018-06-05", "eu_long", "day"),
        ("2018年6月5日", "2018-06-05", "zh_ymd", "day"),
        ("20180605", "2018-06-05", "compact_yyyymmdd", "day"),
        ("2018-06", "2018-06", "iso8601_month", "month"),
        ("2018", "2018", "year_only", "year"),
    ]
    for raw, iso, tag, prec in cases:
        p, js = run_json("date_norm.py", raw)
        ok = (p.returncode == 0 and js and js["iso"] == iso
              and tag in js["format_tag"] and js["precision"] == prec)
        check("format parse: %r" % raw, ok, p.stdout[:200])

    # ---- 2. 歧义数字日期 ----------------------------------------------
    p, js = run_json("date_norm.py", "03/04/2018")
    isos = {i["iso"] for i in (js or {}).get("interpretations", [])}
    check("ambiguous numeric date -> 2 interpretations + warning",
          p.returncode == 0 and isos == {"2018-03-04", "2018-04-03"}
          and any("AMBIGUOUS" in w for w in js["warnings"]),
          p.stdout[:300])

    # ---- 3. 无法解析 → 保留原文 + 警告 --------------------------------
    p, js = run_json("date_norm.py", "not a date")
    check("unparseable kept raw + warning, exit 1",
          p.returncode == 1 and js and js["iso"] is None
          and js["raw"] == "not a date"
          and any("UNPARSEABLE_DATE_KEPT_RAW" in w for w in js["warnings"]),
          (p.stdout + p.stderr)[:300])

    # ---- 4. OCR 混淆日期 ------------------------------------------------
    p, js = run_json("date_norm.py", "2O18-06-05")
    check("ocr keep-raw: raw kept + suspected warning, exit 1",
          p.returncode == 1 and js and js["iso"] is None
          and any("SUSPECTED_OCR_DIGIT_CONFUSION" in w for w in js["warnings"]),
          (p.stdout + p.stderr)[:300])
    p, js = run_json("date_norm.py", "2O18-06-05",
                     "--ocr-policy", "fix-digit-confusion")
    check("ocr fix-digit-confusion: parsed with declared policy + warning",
          p.returncode == 0 and js and js["iso"] == "2018-06-05"
          and js["format_tag"].startswith("ocr_fixed:")
          and any("OCR_DIGIT_CONFUSION_FIXED" in w for w in js["warnings"]),
          (p.stdout + p.stderr)[:300])

    # ---- 5. 事件抽取 ----------------------------------------------------
    ev1001 = os.path.join(tmp, "gx1001_events.json")
    p = run("event_extract.py", os.path.join(FIXTURES, "rec_GX1001.txt"),
            "-o", ev1001)
    js = None
    if p.returncode == 0 and os.path.exists(ev1001):
        with open(ev1001, encoding="utf-8") as f:
            js = json.load(f)
    events = (js or {}).get("records", [{}])[0].get("events", [])
    kinds = {e["kind"] for e in events}
    by_kind = {}
    for e in events:
        by_kind.setdefault(e["kind"], []).append(e)
    check("event_extract GX1001: priority/filing/publication/grant/unknown present",
          p.returncode == 0
          and {"priority", "filing", "publication", "grant", "unknown"} <= kinds,
          p.stderr[:300])
    check("GX1001 priority iso=2018-06-05",
          bool(by_kind.get("priority"))
          and by_kind["priority"][0]["iso"] == "2018-06-05")
    check("GX1001 filing compact iso=2019-06-03",
          bool(by_kind.get("filing"))
          and by_kind["filing"][0]["iso"] == "2019-06-03")
    unknown_ev = by_kind.get("unknown", [])
    check("GX1001 unknown-kind event has warning + 2 interpretations (6/5/2018)",
          bool(unknown_ev)
          and any("UNKNOWN_EVENT_KIND" in w for w in unknown_ev[0]["warnings"])
          and len(unknown_ev[0]["interpretations"]) == 2
          and unknown_ev[0]["quote"] and unknown_ev[0]["span"][1] > unknown_ev[0]["span"][0])

    ev1002 = os.path.join(tmp, "gx1002_events.json")
    p = run("event_extract.py", os.path.join(FIXTURES, "rec_GX1002.txt"),
            "-o", ev1002)
    with open(ev1002, encoding="utf-8") as f:
        js2 = json.load(f)
    events2 = js2["records"][0]["events"]
    ocr_ev = [e for e in events2 if e["raw"] == "2O2O-O6-15"]
    check("GX1002 OCR-garbled date kept raw with warning (keep-raw policy)",
          p.returncode == 0 and bool(ocr_ev) and ocr_ev[0]["iso"] is None
          and any("UNPARSEABLE_DATE_KEPT_RAW" in w for w in ocr_ev[0]["warnings"]))
    ev1002_fix = os.path.join(tmp, "gx1002_events_fix.json")
    p = run("event_extract.py", os.path.join(FIXTURES, "rec_GX1002.txt"),
            "--ocr-policy", "fix-digit-confusion", "-o", ev1002_fix)
    with open(ev1002_fix, encoding="utf-8") as f:
        js2f = json.load(f)
    ocr_fix = [e for e in js2f["records"][0]["events"] if e["raw"] == "2O2O-O6-15"]
    check("GX1002 OCR date parsed under declared fix policy -> 2020-06-15",
          p.returncode == 0 and bool(ocr_fix) and ocr_fix[0]["iso"] == "2020-06-15")

    ev1003 = os.path.join(tmp, "gx1003_events.json")
    p = run("event_extract.py", os.path.join(FIXTURES, "rec_GX1003.txt"),
            "-o", ev1003)
    check("event_extract GX1003 ok", p.returncode == 0, p.stderr[:300])

    # ---- 6. 时间轴 + 顺序冲突 ------------------------------------------
    tl_out = os.path.join(tmp, "timelines.json")
    p = run("timeline_build.py", "--events", ev1001, ev1002, "-o", tl_out)
    with open(tl_out, encoding="utf-8") as f:
        tl = json.load(f)
    ov = [c for c in tl["conflicts"] if c["type"] == "order_violation"]
    check("order violation (grant 2018-05-01 < filing 2019-06-04) detected, exit 1",
          p.returncode == 1 and any(
              c["record_id"] == "rec_GX1002"
              and c["expected"] == "filing <= grant" for c in ov),
          json.dumps(tl["conflicts"], ensure_ascii=False)[:300])
    gx1002_tl = [t for t in tl["timelines"] if t["record_id"] == "rec_GX1002"][0]
    check("GX1002 unparseable OCR event listed as unplaced",
          any(u["raw"] == "2O2O-O6-15" for u in gx1002_tl["unplaced"]))

    # ---- 7. 观测同族优先权核查 ------------------------------------------
    fam_out = os.path.join(tmp, "family.json")
    p = run("timeline_build.py", "--events", ev1001, ev1003, "--family",
            "-o", fam_out)
    with open(fam_out, encoding="utf-8") as f:
        fam = json.load(f)
    check("family priority conflict detected (2018-06-05 vs 2018-06-15), exit 1",
          p.returncode == 1 and fam["family_check"]
          and fam["family_check"]["type"] == "family_priority_conflict"
          and fam["family_check"]["distinct_priority_dates"] == ["2018-06-05", "2018-06-15"],
          json.dumps(fam.get("family_check"), ensure_ascii=False)[:300])
    fam_ok = os.path.join(tmp, "family_ok.json")
    p = run("timeline_build.py", "--events", ev1001, "--family", "-o", fam_ok)
    with open(fam_ok, encoding="utf-8") as f:
        fam1 = json.load(f)
    check("single-member family check consistent, exit 0",
          p.returncode == 0 and fam1["family_check"]
          and fam1["family_check"]["type"] == "family_priority_consistent")

    # ---- 8. 估算护栏 -----------------------------------------------------
    est_out = os.path.join(tmp, "estimate.json")
    p = run("term_estimate.py", "--request",
            os.path.join(FIXTURES, "estimate_request.json"), "-o", est_out)
    with open(est_out, encoding="utf-8") as f:
        est = json.load(f)
    check("estimate guardrails present (is_estimate/not_legal_status/assumptions/as_of)",
          p.returncode == 0 and est.get("is_estimate") is True
          and est.get("not_legal_status") is True
          and bool(est.get("assumptions")) and est.get("as_of") == "2026-11-25")
    check("estimate values: term end 2039-06-03; 3 maintenance windows",
          est["estimates"]["estimated_20y_term_end"]["value"] == "2039-06-03"
          and len(est["estimates"]["us_maintenance_windows"]) == 3
          and est["estimates"]["us_maintenance_windows"][0]["window_open"] == "2025-04-12")

    # ---- 9. 缺少 as_of → 拒绝 -------------------------------------------
    p = run("term_estimate.py", "--earliest-filing", "2019-06-03",
            "--case-id", "X")
    check("estimate without as_of refused, exit 1",
          p.returncode == 1 and "as_of" in p.stderr, p.stderr[:200])

    # ---- 10. --self-test + 禁用措辞 --------------------------------------
    p = run("term_estimate.py", "--self-test")
    check("term_estimate --self-test passes", p.returncode == 0,
          (p.stdout + p.stderr)[:300])
    sys.path.insert(0, SCRIPTS)
    import term_estimate
    check("no forbidden wording in emitted estimate JSON",
          not term_estimate.scan_forbidden(est))

    # ---- 汇总 ------------------------------------------------------------
    n_pass = sum(1 for _, c, _ in CHECKS if c)
    print("=" * 60)
    print("SELFCHECK SUMMARY: %d/%d checks passed (fixtures: %s)"
          % (n_pass, len(CHECKS), FIXTURES))
    print("scratch outputs: %s" % tmp)
    return 0 if n_pass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
