#!/usr/bin/env python3
"""selfcheck.py — 方向 A 全链路自测（正例 + 负例）。全部夹具为虚构示例数据
（illustrative，非正式案例结果）。幂等：夹具写入 examples/fixtures/。
运行：python3 selfcheck.py ；全部断言通过 exit 0，任一失败 exit 1。
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, "examples", "fixtures")
PY = sys.executable

FAILURES = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print("PASS  %s" % name)
    else:
        FAILURES.append(name)
        print("FAIL  %s  %s" % (name, detail))


def run(script, args, cwd=None):
    return subprocess.run([PY, os.path.join(HERE, script)] + args,
                          capture_output=True, text=True, cwd=cwd)


def write_fixtures():
    os.makedirs(FIX, exist_ok=True)
    corpus = {"note": "合成示例语料（illustrative，非正式案例结果）",
              "records": [
                  {"id": "rec1",
                   "numbers": ["US 10,293,847 B2", "US 2018/0293847 A1",
                               "US 15/654,321"],
                   "priorities": ["US 15/654,321"],
                   "title": "示例涂层装置（虚构）", "locator": "$.records[0]"},
                  {"id": "rec2",
                   "numbers": ["WO 2019/123456 A1"],
                   "priorities": ["US 15/654,321", "US 16/000,111"],
                   "title": "示例涂层装置（虚构）- 国际申请",
                   "locator": "$.records[1]"},
                  {"id": "rec3",
                   "numbers": ["CN 110123456 A"],
                   "priorities": ["CN 201810123456.7"],
                   "title": "示例涂层方法（虚构，无关联族）",
                   "locator": "$.records[2]"},
              ]}
    with open(os.path.join(FIX, "corpus.json"), "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    facsimile = """United States Patent (illustrative sample, not a real patent)
(10) Patent No.: US 10,293,847 B2
(45) Date of Patent: Jun. 15, 2021
(54) EXAMPLE COATING APPARATUS (ILLUSTRATIVE)
(21) Appl. No.: 15/654,321
(22) Filed: Mar. 1, 2018
(72) Inventors: Doe, Jane (72) Example City, CA (US)
(73) Assignee: EXAMPLE CORP (ILLUSTRATIVE)
(57) ABSTRACT
An illustrative coating apparatus for self-check only.
"""
    with open(os.path.join(FIX, "facsimile_page1.txt"), "w", encoding="utf-8") as f:
        f.write(facsimile)

    case = {"case_id": "EX-ILLUSTRATIVE-001",
            "output_contract": {"candidates": "候选专利列表",
                                "family_scope": "同族归并口径",
                                "status_note": "状态说明"}}
    with open(os.path.join(FIX, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    no_inid = "This text contains no INID codes at all, illustrative only.\n"
    with open(os.path.join(FIX, "no_inid.txt"), "w", encoding="utf-8") as f:
        f.write(no_inid)


def main():
    write_fixtures()
    tmp = tempfile.mkdtemp(prefix="selfcheck_a_")

    sys.path.insert(0, HERE)
    import patent_numbers as pn

    # ---- P1 号码规范化正例 ----
    p = pn.normalize("US 2020/0123456 A1")
    check("P1a US 公开号规范化", p["ok"] and p["ntype"] == "pub"
          and p["key"] == "US-pub-20200123456" and p["kind"] == "A1", str(p))
    p = pn.normalize("WO2019/123456")
    check("P1b WO 公开号规范化", p["ok"] and p["key"] == "WO-pub-2019123456", str(p))
    p = pn.normalize("US 10,293,847 B2")
    check("P1c US 授权号带 kind 无歧义", p["ok"] and p["ntype"] == "grant"
          and not p["alternatives"], str(p))
    p = pn.normalize("US 15/654,321")
    check("P1d US 裸 8 位歧义有警告", p["ok"] and p["warnings"]
          and p["alternatives"], str(p))

    # ---- P2 OCR 粘连拆分（直接单测 try_split_merged）----
    parts, event = pn.try_split_merged("EP1234567A1EP7654321B1")
    check("P2a 唯一边界粘连拆分成功", parts is not None and event
          and "核对" in event["warning"], str(event))
    parts, event = pn.try_split_merged("EP12345677654321")
    check("P2b 无可靠边界不猜测", parts is None and event
          and event["type"] == "ocr_split_failed", str(event))

    # ---- P3 语料索引与号码查询 ----
    idx_path = os.path.join(tmp, "idx.json")
    r = run("scan_corpus.py", ["index", "--roots", FIX, "--out", idx_path])
    check("P3a 索引构建 exit0", r.returncode == 0, r.stderr[-300:])
    idx = json.load(open(idx_path, encoding="utf-8"))
    check("P3b 索引条目数 >= 7", len(idx["entries"]) >= 7,
          str(len(idx["entries"])))
    q_path = os.path.join(tmp, "q.json")
    r = run("scan_corpus.py", ["query", "--index", idx_path,
                               "--numbers", "US 10,293,847 B2",
                               "--out", q_path])
    qres = json.load(open(q_path, encoding="utf-8"))
    nq = qres["number_queries"][0]
    check("P3c 精确命中授权号", len(nq["exact_hits"]) >= 1
          and any(h["file"].endswith("corpus.json") for h in nq["exact_hits"]),
          str(nq)[:200])
    r = run("scan_corpus.py", ["query", "--index", idx_path,
                               "--numbers", "US10293847"])
    nq2 = json.loads(r.stdout)["number_queries"][0]
    check("P3d 裸号歧义走 related_hits", not nq2["exact_hits"]
          and nq2["related_hits"] and nq2["parsed"]["warnings"], str(nq2)[:200])

    # ---- P4 传真件 INID 抽取 ----
    fx_path = os.path.join(tmp, "fx.json")
    r = run("extract_facsimile.py",
            ["--text", os.path.join(FIX, "facsimile_page1.txt"), "--out", fx_path])
    check("P4a 传真抽取 exit0", r.returncode == 0, r.stderr[-300:])
    fx = json.load(open(fx_path, encoding="utf-8"))
    doc = fx["fields"]["document_id"]["value"][0]
    check("P4b 文献号解析", doc["key"] == "US-grant-10293847", str(doc))
    check("P4c 授权日 ISO", fx["fields"]["grant_date"]["value"]["iso"]
          == "2021-06-15", str(fx["fields"]["grant_date"]))
    app = fx["fields"]["application_number"]["value"][0]
    check("P4d 无国别码申请号回退", app["key"] == "US-app-15654321"
          and any(e["type"] == "cc_fallback" for e in fx["evidence_events"]),
          str(app)[:200])
    check("P4e 重复 INID 记录事件", any(e["type"] == "inid_duplicate"
          for e in fx["evidence_events"]), str(fx["evidence_events"]))

    # ---- P5 同族归并双口径 ----
    fam_path = os.path.join(tmp, "fam.json")
    r = run("merge_family.py", ["--records", os.path.join(FIX, "corpus.json"),
                                "--out", fam_path])
    check("P5a 归并 exit0", r.returncode == 0, r.stderr[-300:])
    fam = json.load(open(fam_path, encoding="utf-8"))
    ext_sets = [set(x) for x in fam["extended_families"]]
    check("P5b 扩展族 rec1+rec2 连通", any({"rec1", "rec2"} <= s for s in ext_sets)
          and any(s == {"rec3"} for s in ext_sets), str(ext_sets))
    simple_sets = [set(x) for x in fam["simple_families"]]
    check("P5c 简单族各自独立", {"rec1"} in simple_sets
          and {"rec2"} in simple_sets, str(simple_sets))
    check("P5d 口径说明存在", "simple" in fam["scope_note"]
          and "完整同族" in fam["scope_note"]["limitation"])

    # ---- P6 result.json 骨架 ----
    r = run("scaffold_result.py", ["--case", os.path.join(FIX, "case.json"),
                                   "--out", tmp])
    check("P6a 骨架 exit0", r.returncode == 0, r.stderr[-300:])
    res = json.load(open(os.path.join(tmp, "result.json"), encoding="utf-8"))
    check("P6b case_id 与契约镜像", res["case_id"] == "EX-ILLUSTRATIVE-001"
          and set(res["output_contract"]) ==
          {"candidates", "family_scope", "status_note"}, str(res)[:200])
    check("P6c 未填充字段入 uncertainty", any("candidates" in u for u in
          res["uncertainty"]), str(res["uncertainty"]))

    # ---- N1 非法号码 ----
    p = pn.normalize("GARBAGE-123")
    check("N1 非法号码不猜测", not p["ok"] and "不猜测" in p["warnings"][0], str(p))

    # ---- N2 空语料 ----
    empty = os.path.join(tmp, "empty")
    os.makedirs(empty)
    r = run("scan_corpus.py", ["index", "--roots", empty,
                               "--out", os.path.join(tmp, "e.json")])
    eidx = json.load(open(os.path.join(tmp, "e.json"), encoding="utf-8"))
    check("N2 空语料 exit2 + 警告", r.returncode == 2
          and eidx["files_scanned"] == 0 and eidx["warnings"], r.stdout[-200:])

    # ---- N3 无 INID 文本降级 ----
    r = run("extract_facsimile.py",
            ["--text", os.path.join(FIX, "no_inid.txt"),
             "--out", os.path.join(tmp, "noidx.json")])
    nd = json.load(open(os.path.join(tmp, "noidx.json"), encoding="utf-8"))
    check("N3 无 INID 降级不伪造字段", nd["extraction_status"] == "degraded"
          and any(e["type"] == "no_inid" for e in nd["evidence_events"]),
          str(nd)[:200])

    print("\n%d 项检查，%d 通过，%d 失败" % (CHECKS[0],
          CHECKS[0] - len(FAILURES), len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
