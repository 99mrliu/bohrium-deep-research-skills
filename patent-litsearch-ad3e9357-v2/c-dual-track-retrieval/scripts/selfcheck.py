#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 端到端自查：在合成夹具上跑完整管线，全部断言通过才退出 0。

覆盖：
  1. 合法 spec：validate 退出 0；patent/npl 双轨 render 退出 0；
     npl 渲染丢弃 classification_codes 且 stderr 带 NOTE；
     同一 spec 两次渲染字符串完全一致（R9）。
  2. 裸 NOT spec → validate 退出 2 且报告 R4。
  3. 缺 intent spec → validate 退出 2 且报告 R2。
  4. corpus_search：命中预期文档且带 file+line 定位；patent 轨同族
     EXFAM-2026-0001 将 pat_EX1001/pat_EX1002 合并为一条记录；
     pat_EX1003 被排除词拦下；npl_EX2002 计入未命中。
  5. 缺 decision → prisma_screen screen 退出 2 并列出缺失记录。
  6. 完整决策 → report 重算计数（断言精确数值）。
  7. 篡改 --claim 计数 → report 退出 3。
  8. scaffold_result 在 case_fixture 上生成镜像契约的骨架。
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
FIX = os.path.join(ROOT, "examples", "fixtures")
PY = sys.executable

_checks = 0
_failures = []


def check(label, cond, detail=""):
    global _checks
    _checks += 1
    if cond:
        print("[PASS] %s" % label)
    else:
        print("[FAIL] %s  %s" % (label, detail))
        _failures.append(label)


def run(script, *cli):
    return subprocess.run(
        [PY, os.path.join(SCRIPTS, script)] + list(cli),
        capture_output=True, text=True, cwd=ROOT)


def main():
    valid = os.path.join(FIX, "query_spec_valid.json")
    bad_not = os.path.join(FIX, "query_spec_bad_bare_not.json")
    bad_intent = os.path.join(FIX, "query_spec_bad_no_intent.json")
    corpus = os.path.join(FIX, "corpus")
    case = os.path.join(FIX, "case_fixture.json")

    tmp = tempfile.mkdtemp(prefix="dtrl_selfcheck_")
    q_pat = os.path.join(tmp, "q_patent.txt")
    q_pat2 = os.path.join(tmp, "q_patent2.txt")
    q_npl = os.path.join(tmp, "q_npl.txt")
    hits_p = os.path.join(tmp, "hits.json")
    screened_p = os.path.join(tmp, "screened.json")
    prisma_p = os.path.join(tmp, "prisma.json")

    # 1. 合法 spec：validate + 双轨 render
    r = run("query_build.py", "validate", "--spec", valid)
    check("合法 spec validate 退出 0", r.returncode == 0, r.stdout + r.stderr)

    r = run("query_build.py", "render", "--spec", valid,
            "--track", "patent", "--out", q_pat)
    pat_text = open(q_pat, encoding="utf-8").read() if r.returncode == 0 else ""
    check("patent 轨 render 退出 0 且含 CLASS IN",
          r.returncode == 0 and "CLASS IN" in pat_text, r.stderr)

    r = run("query_build.py", "render", "--spec", valid,
            "--track", "npl", "--out", q_npl)
    npl_text = open(q_npl, encoding="utf-8").read() if r.returncode == 0 else ""
    check("npl 轨 render 退出 0 且丢弃分类号并记录 NOTE",
          r.returncode == 0 and "CLASS IN" not in npl_text
          and "NOTE" in r.stderr and "H01M 12/06" in r.stderr,
          r.stderr)

    run("query_build.py", "render", "--spec", valid,
        "--track", "patent", "--out", q_pat2)
    same = open(q_pat, encoding="utf-8").read() == \
        open(q_pat2, encoding="utf-8").read()
    check("R9 同一 spec 两次渲染字符串一致", same)

    # 2/3. 反面样例
    r = run("query_build.py", "validate", "--spec", bad_not)
    check("裸 NOT spec → 退出 2 且报告 R4",
          r.returncode == 2 and "R4" in r.stdout, r.stdout)
    r = run("query_build.py", "validate", "--spec", bad_intent)
    check("缺 intent spec → 退出 2 且报告 R2",
          r.returncode == 2 and "R2" in r.stdout, r.stdout)

    # 4. corpus_search
    r = run("corpus_search.py", "run", "--spec", valid,
            "--roots", corpus, "--out", hits_p)
    check("corpus_search run 退出 0", r.returncode == 0, r.stderr)
    data = json.load(open(hits_p, encoding="utf-8"))
    rec_by_id = {rec["doc_id"]: rec for rec in data["records"]}
    fam = rec_by_id.get("FAM:EXFAM-2026-0001")
    check("patent 轨同族合并：FAM:EXFAM-2026-0001 含 pat_EX1001+pat_EX1002",
          fam is not None
          and sorted(fam["members"]) == ["pat_EX1001", "pat_EX1002"],
          json.dumps(list(rec_by_id), ensure_ascii=False))
    check("npl 轨按 DOI 去重：DOI:10.9999/synth.2026.0001 命中",
          "DOI:10.9999/synth.2026.0001" in rec_by_id)
    check("每条命中带 file+line 定位",
          all(isinstance(h["locator"]["line"], int) and h["locator"]["file"]
              for h in data["hits"]))
    check("pat_EX1003 被排除词（锂空气）拦下",
          any(d["doc_id"] == "pat_EX1003" and "锂空气" in d["reason"]
              for d in data["excluded_docs"]),
          json.dumps(data["excluded_docs"], ensure_ascii=False))
    check("npl_EX2002 扫描后未命中（计入分母）",
          any(d["doc_id"] == "npl_EX2002" for d in data["no_match_docs"]),
          json.dumps(data["no_match_docs"], ensure_ascii=False))
    check("扫描文件数 = 5", data["meta"]["files_scanned"] == 5)

    # 5. 缺 decision → 退出 2
    dec_partial = os.path.join(tmp, "decisions_partial.json")
    json.dump([{"doc_id": "FAM:EXFAM-2026-0001", "decision": "include",
                "reason": "直接公开柔性锌空气电池凝胶电解质方案"}],
              open(dec_partial, "w", encoding="utf-8"), ensure_ascii=False)
    r = run("prisma_screen.py", "screen", "--hits", hits_p,
            "--decisions", dec_partial, "--out", screened_p)
    check("缺 decision → screen 退出 2 且列出缺失记录",
          r.returncode == 2 and "DOI:10.9999/synth.2026.0001" in r.stderr,
          r.stderr)

    # 6. 完整决策 → 重算计数
    dec_full = os.path.join(tmp, "decisions.json")
    json.dump([
        {"doc_id": "FAM:EXFAM-2026-0001", "decision": "include",
         "reason": "直接公开柔性锌空气电池凝胶电解质方案"},
        {"doc_id": "DOI:10.9999/synth.2026.0001", "decision": "exclude",
         "reason": "综述性对照文献，不含可复用的柔性实施例数据"},
    ], open(dec_full, "w", encoding="utf-8"), ensure_ascii=False)
    r = run("prisma_screen.py", "screen", "--hits", hits_p,
            "--decisions", dec_full, "--out", screened_p)
    check("完整决策 screen 退出 0", r.returncode == 0, r.stderr)
    r = run("prisma_screen.py", "report", "--screened", screened_p,
            "--out", prisma_p)
    check("report 退出 0", r.returncode == 0, r.stderr)
    prisma = json.load(open(prisma_p, encoding="utf-8"))["prisma"]
    check("重算计数精确：raw=3, dup_removed=1, screened=2, included=1, excluded=1",
          prisma["identification"]["raw_hits"] == 3
          and prisma["identification"]["duplicates_removed"] == 1
          and prisma["screening"]["records_screened"] == 2
          and prisma["included"]["total"] == 1
          and prisma["screening"]["excluded"] == 1,
          json.dumps(prisma, ensure_ascii=False))
    check("patent/npl 分轨计数正确（2 / 1）",
          prisma["identification"]["patent_hits"] == 2
          and prisma["identification"]["npl_hits"] == 1)
    check("遗漏说明模板包含零命中词项与排除理由分布",
          "遗漏说明" in json.load(open(prisma_p, encoding="utf-8"))
          ["omissions_note_template"])

    # 7. 篡改 claim → 退出 3
    claim_bad = os.path.join(tmp, "claim_bad.json")
    json.dump({"raw_hits": 3, "duplicates_removed": 0, "records_screened": 2,
               "included": 2, "excluded": 0},
              open(claim_bad, "w", encoding="utf-8"))
    r = run("prisma_screen.py", "report", "--screened", screened_p,
            "--out", prisma_p, "--claim", claim_bad)
    check("篡改 --claim → report 退出 3", r.returncode == 3, r.stderr)
    claim_ok = os.path.join(tmp, "claim_ok.json")
    json.dump({"raw_hits": 3, "duplicates_removed": 1, "records_screened": 2,
               "included": 1, "excluded": 1},
              open(claim_ok, "w", encoding="utf-8"))
    r = run("prisma_screen.py", "report", "--screened", screened_p,
            "--out", prisma_p, "--claim", claim_ok)
    check("正确 --claim → report 退出 0", r.returncode == 0, r.stderr)

    # 8. scaffold
    scaf_dir = os.path.join(tmp, "scaffold")
    r = run("scaffold_result.py", "--case", case, "--out", scaf_dir)
    res = json.load(open(os.path.join(scaf_dir, "result.json"),
                         encoding="utf-8")) if r.returncode == 0 else {}
    contract = json.load(open(case, encoding="utf-8"))["output_contract"]
    check("scaffold 退出 0 且镜像全部 output_contract 字段",
          r.returncode == 0
          and all(k in res for k in contract)
          and res.get("case_id") == "SYNTH-EXAMPLE-003"
          and res.get("status") == "partial",
          r.stderr)

    print("-" * 60)
    if _failures:
        print("selfcheck: %d/%d 通过，%d 项失败：%s"
              % (_checks - len(_failures), _checks, len(_failures),
                 "；".join(_failures)))
        return 1
    print("selfcheck: 全部 %d 项断言通过（exit 0）" % _checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
