#!/usr/bin/env python3
"""check_exports.py — 交付物独立回读交叉核验（不 import build_review 的任何函数）。

交付物是否合格不由构建脚本自我感觉决定，而由本脚本**重新读盘**逐件复算：

  X1 manifest.json 存在且列出全部 5 件交付物
  X2 每件交付物真实存在，sha256 与字节数与 manifest 一致（防篡改/防半截写盘）
  X3 ledger.csv 以 UTF-8-SIG 可读，数据行数与 result.json 的 screening_log 条数一致
  X4 review.html 包含全部"纳入"记录的标题（HTML 转义后比对）
  X5 flow.svg 各 stage 计数（n = N）与 ledger.csv 的处置分布逐项一致
  X6 result.json 契约完备：case_id 一致、output_contract 字段全覆盖（null 即缺失）、
     status 三值且 complete 时 uncertainty 必空

用法:
  python3 check_exports.py --case /input/case.json --out /app/output

退出码: 0 = 全部 PASS（可交付）；1 = 任一 FAIL（报告逐项指明）；2 = 输出目录/关键文件缺失。
核验报告同时写入 <out>/export-check.json（不在 manifest 内，属核验侧产物）。
"""
import argparse, csv, hashlib, html, json, os, re, sys

DELIVERABLES = ("ledger.csv", "report.md", "review.html", "flow.svg", "result.json")
STAGE_EXPECT = [  # (stage id, 由 ledger 处置分布推导期望值的函数键)
    ("identified", "total"), ("duplicates", "duplicate"), ("screened", "screened"),
    ("excluded", "exclude"), ("included", "include"), ("borderline", "borderline"),
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        for k in ("fields", "required"):
            if isinstance(c.get(k), list):
                return [str(x) for x in c[k]]
        return sorted(c.keys())
    return []


def main():
    ap = argparse.ArgumentParser(description="独立回读全部复核交付物并交叉核验，PASS/FAIL 退出")
    ap.add_argument("--case", required=True, help="/input/case.json 路径")
    ap.add_argument("--out", required=True, help="交付物目录（build_review.py 的 --out）")
    args = ap.parse_args()
    checks = []

    def check(cid, ok, detail):
        checks.append({"id": cid, "verdict": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    if not os.path.isdir(args.out):
        print(json.dumps({"verdict": "FAIL",
                          "error": "输出目录不存在: %s" % args.out}, ensure_ascii=False))
        sys.exit(2)

    # ---- X1 manifest 存在且覆盖全部交付物 ----
    mpath = os.path.join(args.out, "manifest.json")
    manifest = None
    if os.path.isfile(mpath):
        try:
            manifest = json.load(open(mpath, encoding="utf-8"))
        except Exception:
            manifest = None
    listed = set((manifest or {}).get("deliverables") or {})
    check("X1", isinstance(manifest, dict) and set(DELIVERABLES) <= listed,
          "manifest 登记的交付物: %s" % (sorted(listed) or "manifest 缺失/损坏"))
    if not isinstance(manifest, dict):
        json.dump({"verdict": "FAIL", "checks": checks},
                  open(os.path.join(args.out, "export-check.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(json.dumps({"verdict": "FAIL", "failed": ["X1"]}, ensure_ascii=False))
        sys.exit(1)

    # ---- X2 哈希与字节数逐件回核 ----
    bad = []
    for name in sorted(set(DELIVERABLES) | listed):
        p = os.path.join(args.out, name)
        if not os.path.isfile(p):
            bad.append("%s(缺失)" % name)
            continue
        want = manifest["deliverables"].get(name) or {}
        if want.get("sha256") != sha256_of(p):
            bad.append("%s(sha256)" % name)
        elif want.get("bytes") != os.path.getsize(p):
            bad.append("%s(bytes)" % name)
    check("X2", not bad, "哈希/字节不一致: %s" % (bad or "无，逐件一致"))

    # ---- X3 ledger.csv 行数 == result.json screening_log 条数 ----
    rows, result = [], None
    try:
        with open(os.path.join(args.out, "ledger.csv"),
                  encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except Exception as e:
        check("X3", False, "ledger.csv 读取失败: %s" % e)
    try:
        result = json.load(open(os.path.join(args.out, "result.json"), encoding="utf-8"))
    except Exception as e:
        result = None
        check("X3", False, "result.json 读取失败: %s" % e)
    if rows and result is not None:
        n_log = len(result.get("screening_log") or [])
        check("X3", len(rows) == n_log,
              "ledger.csv 数据行 %d vs screening_log %d" % (len(rows), n_log))
    elif not any(c["id"] == "X3" for c in checks):
        check("X3", False, "ledger.csv 或 result.json 为空")

    # 处置分布（供 X5）
    dist = {"total": len(rows), "include": 0, "exclude": 0,
            "borderline": 0, "duplicate": 0}
    for r in rows:
        d = (r.get("decision") or "").strip()
        if d in dist:
            dist[d] += 1
    dist["screened"] = dist["total"] - dist["duplicate"]

    # ---- X4 review.html 含全部纳入标题 ----
    page = ""
    try:
        page = open(os.path.join(args.out, "review.html"), encoding="utf-8").read()
    except Exception:
        pass
    missing_titles = [r.get("title", "") for r in rows
                      if (r.get("decision") or "").strip() == "include"
                      and r.get("title")
                      and html.escape(r["title"], quote=True) not in page]
    check("X4", bool(page) and not missing_titles,
          "纳入记录 %d 条，HTML 缺标题 %d 条: %s"
          % (dist["include"], len(missing_titles), missing_titles[:2] or "无"))

    # ---- X5 flow.svg 计数与台账一致 ----
    svg = ""
    try:
        svg = open(os.path.join(args.out, "flow.svg"), encoding="utf-8").read()
    except Exception:
        pass
    svg_counts = {}
    for m in re.finditer(r'<g id="stage-([a-z_]+)">(.*?)</g>', svg, re.S):
        nm = re.search(r"n\s*=\s*(\d+)", m.group(2))
        if nm:
            svg_counts[m.group(1)] = int(nm.group(1))
    mism = ["%s: svg=%s ledger=%s" % (sid, svg_counts.get(sid, "缺"), dist[key])
            for sid, key in STAGE_EXPECT if svg_counts.get(sid) != dist[key]]
    check("X5", bool(svg) and len(svg_counts) == len(STAGE_EXPECT) and not mism,
          "stage 计数 %d/6 读到；不一致: %s" % (len(svg_counts), mism or "无"))

    # ---- X6 result.json 契约完备与状态诚实 ----
    case = {}
    if os.path.isfile(args.case):
        try:
            case = json.load(open(args.case, encoding="utf-8"))
        except Exception:
            pass
    if not isinstance(result, dict):
        check("X6", False, "result.json 非 JSON 对象")
    else:
        fields = contract_fields(case)
        missing = [f for f in fields if result.get(f) is None]
        st = result.get("status")
        bad_status = st not in ("complete", "partial", "blocked") or (
            st == "complete" and result.get("uncertainty"))
        cid_ok = bool(result.get("case_id")) and result.get("case_id") == case.get("case_id")
        ok = cid_ok and not missing and not bad_status
        check("X6", ok, "case_id一致=%s；契约字段缺失=%s；status=%r（uncertainty %d 项）"
              % (cid_ok, missing or "无", st, len(result.get("uncertainty") or [])))

    verdict = "PASS" if all(c["verdict"] == "PASS" for c in checks) else "FAIL"
    report = {"verdict": verdict, "checks": checks,
              "note": "PASS 才可交付；FAIL 时按失败项修复后重跑 build_review.py 与本脚本"}
    with open(os.path.join(args.out, "export-check.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"verdict": verdict,
                      "failed": [c["id"] for c in checks if c["verdict"] == "FAIL"]},
                     ensure_ascii=False))
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
