#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selfcheck.py — 合成夹具端到端自测

正例：examples/fixtures/ 下 5 条虚构记录（2 件同族专利 + 2 篇论文 + 1 条无法判定），
      跑 build → search → screen → scaffold 全链应 exit 0；
      断言同族去重生效、双轨分类正确、PRISMA 重算一致、命中带定位与词项明细。
负例：检索式缺 intent（R6）、裸 NOT（R4）→ build 必须 exit 非 0；
      PRISMA 自报数不一致 → screen 必须 exit 非 0。
全部断言通过 exit 0，任一失败 exit 1。仅依赖标准库。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(SCRIPTS)
FIX = os.path.join(SKILL, "examples", "fixtures")

FAILS = []


def check(cond, label, detail=""):
    if cond:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s  %s" % (label, detail))
        FAILS.append(label)


def run(script, args, cwd):
    cmd = [sys.executable, os.path.join(SCRIPTS, script)] + args
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main():
    tmp = tempfile.mkdtemp(prefix="selfcheck_")
    try:
        corpus = os.path.join(tmp, "corpus")
        out = os.path.join(tmp, "out")
        os.makedirs(corpus)
        os.makedirs(out)
        for fn in ("records_patents.json", "records_npl.jsonl", "notes_unclassified.txt"):
            shutil.copy(os.path.join(FIX, fn), os.path.join(corpus, fn))
        qjson = os.path.join(out, "query.json")
        hitsjson = os.path.join(out, "hits.json")
        scrjson = os.path.join(out, "screening.json")
        resjson = os.path.join(out, "result.json")

        # 1) 正例：build
        r = run("build_query.py", ["build", "--spec", os.path.join(FIX, "query_spec_valid.json"),
                                   "--out", qjson], tmp)
        check(r.returncode == 0, "正例 build(valid) exit 0", r.stderr)
        q = json.load(open(qjson, encoding="utf-8"))
        check("AND" in q["boolean"] and "OR" in q["boolean"], "布尔表达式含 AND/OR", q.get("boolean", ""))
        check(all(t.get("intent") for b in q["blocks"] for t in b["terms"]), "全部词项带 intent")

        # 2) 负例：缺 intent → R6
        r = run("build_query.py", ["build", "--spec", os.path.join(FIX, "query_spec_bad_no_intent.json")], tmp)
        check(r.returncode != 0 and "R6" in (r.stderr + r.stdout),
              "负例 build(缺 intent) exit 非 0 且报 R6", "rc=%s %s" % (r.returncode, r.stderr))

        # 3) 负例：裸 NOT → R4
        r = run("build_query.py", ["build", "--spec", os.path.join(FIX, "query_spec_bad_bare_not.json")], tmp)
        check(r.returncode != 0 and "R4" in (r.stderr + r.stdout),
              "负例 build(裸 NOT) exit 非 0 且报 R4", "rc=%s %s" % (r.returncode, r.stderr))

        # 4) 正例：search
        r = run("search_corpus.py", ["--query", qjson, "--corpus", corpus, "--out", hitsjson], tmp)
        check(r.returncode == 0, "正例 search exit 0", r.stderr)
        h = json.load(open(hitsjson, encoding="utf-8"))
        check(h["corpus"]["records_total"] == 5, "识别 5 条记录", str(h["corpus"]["records_total"]))
        tr = h["corpus"]["tracks"]
        check(tr.get("patent") == 2 and tr.get("npl") == 2 and tr.get("unclassified") == 1,
              "双轨分类正确（专利 2 / 论文 2 / 无法判定 1）", str(tr))
        check(h["dedup"]["duplicates_removed"] == 1, "同族去重生效（合并 1 条）", str(h["dedup"]))
        tracks_hit = [x["track"] for x in h["hits"]]
        check(tracks_hit.count("patent") == 1 and tracks_hit.count("npl") == 1,
              "去重后命中 1 件专利 + 1 篇论文", str(tracks_hit))
        check(all(x.get("loc") and x.get("blocks_matched") for x in h["hits"]),
              "每条命中带定位与匹配词项明细")
        check(len(h["unclassified"]) == 1, "无法判定记录被如实列出")
        kept_patent = [x for x in h["hits"] if x["track"] == "patent"][0]
        check(len(kept_patent.get("duplicates", [])) == 1, "保留专利记录附带同族重复条目")

        # 5) 正例：screen（PRISMA 重算一致、逐条理由、score 分解、遗漏说明）
        r = run("screen_rank.py", ["--query", qjson, "--hits", hitsjson, "--out", scrjson], tmp)
        check(r.returncode == 0, "正例 screen exit 0", r.stderr)
        s = json.load(open(scrjson, encoding="utf-8"))
        p = s["prisma"]
        check(p["identified"] == 5 and p["duplicates_removed"] == 1 and p["screened"] == 2
              and p["included"] + p["excluded"] == 2,
              "PRISMA 重算一致（5/1/2/纳入+排除=2）", str(p))
        check(all(d.get("reason_codes") for d in s["decisions"]), "逐条决定带理由代码")
        inc = [d for d in s["decisions"] if d["decision"] == "include"]
        exc = [d for d in s["decisions"] if d["decision"] == "exclude"]
        check(len(inc) == 1 and len(exc) == 1 and exc[0]["reason_codes"] == ["E7"],
              "纳入 1 条（专利）/ 排除 1 条（E7 块覆盖不足）", str(s["decisions"]))
        check(all("breakdown" in x for x in s["ranking"]), "排序输出 score 分解")
        check("zero_hit_blocks" in s.get("omissions", {}), "遗漏说明存在")

        # 6) 负例：PRISMA 自报数不一致 → exit 非 0
        expect = os.path.join(out, "expect_bad.json")
        with open(expect, "w", encoding="utf-8") as f:
            json.dump({"included": 99}, f)
        r = run("screen_rank.py", ["--query", qjson, "--hits", hitsjson, "--expect", expect], tmp)
        check(r.returncode != 0, "负例 screen(PRISMA 自报不一致) exit 非 0", "rc=%s" % r.returncode)

        # 7) 正例：scaffold（镜像 output_contract）
        r = run("scaffold_result.py", ["--case", os.path.join(FIX, "case_illustrative.json"),
                                       "--query", qjson, "--hits", hitsjson,
                                       "--screening", scrjson, "--out", resjson], tmp)
        check(r.returncode == 0, "正例 scaffold exit 0", r.stderr)
        res = json.load(open(resjson, encoding="utf-8"))
        check(res.get("case_id") == "illustrative-demo-000", "result.json 含 case_id")
        contract = json.load(open(os.path.join(FIX, "case_illustrative.json"), encoding="utf-8"))["output_contract"]
        missing = [k for k in contract if k not in res]
        check(not missing, "output_contract 全部字段被镜像", str(missing))
        check(res.get("status") in ("ok", "partial", "failed"), "status 诚实取值", str(res.get("status")))
        check(res.get("uncertainty"), "uncertainty 非空（如实标注）")

        # 8) 号码模式冒烟：单块检索式精确匹配虚构公开号
        numspec = os.path.join(out, "num_spec.json")
        with open(numspec, "w", encoding="utf-8") as f:
            json.dump({"topic": "号码查询冒烟（虚构）", "version": "1.0", "mode": "number_lookup",
                       "blocks": [{"name": "公开号", "terms": [
                           {"term": "XX1000002", "intent": "按公开号定位文献（不带 kind code 也应命中 B1）"}]}],
                       "facets": {}}, f, ensure_ascii=False)
        r = run("build_query.py", ["build", "--spec", numspec, "--out", qjson + ".num"], tmp)
        check(r.returncode == 0, "号码模式 build exit 0", r.stderr)
        r = run("search_corpus.py", ["--query", qjson + ".num", "--corpus", corpus,
                                     "--out", hitsjson + ".num"], tmp)
        hn = json.load(open(hitsjson + ".num", encoding="utf-8"))
        check(r.returncode == 0 and len(hn["hits"]) >= 1,
              "号码模式精确匹配命中（kind code 感知）", r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILS:
        print("SELF-CHECK FAILED: %d 项未通过 -> %s" % (len(FAILS), FAILS))
        return 1
    print("SELF-CHECK PASSED: 全部断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
