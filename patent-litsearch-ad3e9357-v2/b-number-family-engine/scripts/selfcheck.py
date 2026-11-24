#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 端到端自查：在 examples/fixtures 上验证全链路。

覆盖：
  1. 合法号码规范化电池（US/WO/EP/CN/JP/KR/XX 各类型，含真实格式样例
     如 "US 10,293,847 B2"——仅作格式测试，不代表任何真实专利）；
  2. 歧义号码（8 位裸号）→ ok=true + alternatives + 歧义 warning；
  3. 非法号码 → ok=false，不猜测；
  4. OCR 粘连切分：唯一边界成功；多解/无解 → 不拆分 + warning；
  5. 语料索引 + 号码查询（精确命中 + related_hits 同号不同种类）+
     关键词召回；
  6. 双口径族合并：fixture 设计上 simple=3 族、extended=1 族，
     无优先权记录单列；
  7. scaffold 骨架镜像 output_contract + 深合并填充；
  8. CLI 冒烟测试（真实子进程调用 patent_numbers.py normalize）。

退出码：0 全部通过；1 存在失败断言；2 用法/输入错误。
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
FIX = os.path.join(SKILL_ROOT, "examples", "fixtures")
sys.path.insert(0, HERE)

import patent_numbers as pn
import corpus_scan
import family_merge
import scaffold_result

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print("[%s] %s%s" % (status, name, (" — %s" % detail) if detail else ""))
    if not cond:
        FAILURES.append(name)


def warn_text(res):
    return " ".join(res.get("warnings", []))


# ---------------------------------------------------------- 1. 合法号码电池
VALID_CASES = [
    # (输入, 期望 normalized, 期望 kind, 期望 country)
    ("US 10,293,847 B2", "US10293847B2", "grant", "US"),
    ("US2019/0123456 A1", "US20190123456A1", "publication", "US"),
    ("US 16/123,456", "US16123456", "application", "US"),
    ("WO2019/123456 A1", "WO2019123456A1", "publication", "WO"),
    ("PCT/US2019/012345", "PCT/US2019/012345", "application", "WO"),
    ("EP 3 456 789 A1", "EP3456789A1", "publication", "EP"),
    ("EP 19 123 456.7", "EP19123456.7", "application", "EP"),
    ("CN 110123456 A", "CN110123456A", "publication", "CN"),
    ("CN201910123456.7", "CN201910123456.7", "application", "CN"),
    ("JP 2019-123456 A", "JP2019123456A", "publication", "JP"),
    ("JP H01-123456 A", "JPH01123456A", "publication", "JP"),
    ("JP6123456B2", "JP6123456B2", "grant", "JP"),
    ("KR 10-2019-0012345 A", "KR1020190012345A", "publication", "KR"),
    ("KR 10-1234567 B1", "KR101234567B1", "grant", "KR"),
    ("XX1000001A1", "XX1000001A1", "publication", "XX"),
    ("XX1000001B2", "XX1000001B2", "grant", "XX"),
    ("XX2019/000001", "XX2019/000001", "application", "XX"),
]

print("== 1. 合法号码规范化电池 ==")
for raw, exp_norm, exp_kind, exp_cty in VALID_CASES:
    r = pn.normalize_token(raw)
    check("normalize %r" % raw,
          r["ok"] and r["normalized"] == exp_norm
          and r["kind"] == exp_kind and r["country"] == exp_cty,
          "got %s/%s/%s ok=%s" % (r["normalized"], r["kind"],
                                  r["country"], r["ok"]))

# ---------------------------------------------------------- 2. 歧义号码
print("== 2. 歧义号码 ==")
r = pn.normalize_token("16123456")
check("裸 8 位号歧义", r["ok"] and len(r["alternatives"]) >= 1
      and "AMBIGUOUS" in warn_text(r),
      "alternatives=%d" % len(r["alternatives"]))
check("裸 8 位号主解读为 US 授权号",
      r["normalized"] == "US16123456" and r["kind"] == "grant",
      r["normalized"])
r = pn.normalize_token("JP 2019-123456")
check("JP 无种类代码歧义（公开号 vs 申请号）",
      r["ok"] and len(r["alternatives"]) >= 1
      and "AMBIGUOUS" in warn_text(r),
      "alternatives=%d" % len(r["alternatives"]))

# ---------------------------------------------------------- 3. 非法号码
print("== 3. 非法号码 ==")
for bad in ["NOT_A_NUMBER", "US12345", "", "##"]:
    r = pn.normalize_token(bad)
    check("拒绝 %r" % bad, not r["ok"] and r["normalized"] is None,
          warn_text(r)[:60])

# ---------------------------------------------------------- 4. OCR 粘连切分
print("== 4. OCR 粘连切分 ==")
r = pn.split_glued("WO2019/123456US10293847B2")
check("唯一边界切分成功", r["ok"] and r["split"] is not None
      and r["split"][0]["normalized"] == "WO2019123456"
      and r["split"][1]["normalized"] == "US10293847B2",
      "boundary=%s" % r.get("boundary"))
r = pn.split_glued("123456789123456")  # 7+8 与 8+7 两个合法边界
check("多解粘连保持原文", (not r["ok"]) and r["split"] is None
      and r["kept"] == "123456789123456"
      and "歧义切分" in warn_text(r),
      "boundaries=%s" % r.get("candidate_boundaries"))
r = pn.split_glued("GARBAGE!!")
check("无解粘连保持原文", (not r["ok"]) and r["kept"] == "GARBAGE!!"
      and "切分失败" in warn_text(r), "")

# ---------------------------------------------------------- 5. 语料索引与查询
print("== 5. 语料索引与查询 ==")
tmpdir = tempfile.mkdtemp(prefix="pfe_selfcheck_")
index_path = os.path.join(tmpdir, "index.json")
index = corpus_scan.build_index([os.path.join(FIX, "corpus")], index_path)
check("索引含 4 个可用文本文件",
      sum(1 for f in index["files"] if f["status"] == "ok") == 4,
      "files=%d" % len(index["files"]))
check("索引抽取到 XX1000001A1 与 XX1000001B2",
      {e["normalized"] for e in index["entries"]}
      >= {"XX1000001A1", "XX1000001B2"},
      "entries=%d" % len(index["entries"]))

hits_path = os.path.join(tmpdir, "hits.json")
res = corpus_scan.run_query(index_path, numbers=["XX1000001B2"],
                            keywords=["示例催化剂ZX-1"], out_path=hits_path)
q = res["queries"][0]
hit_files = {os.path.basename(h["file"]) for h in q["hits"]}
check("授权号精确命中 EX1001 与 EX2001（非专利文献）",
      hit_files == {"rec_EX1001.txt", "rec_EX2001.txt"},
      str(sorted(hit_files)))
check("related_hits 含同号公开号 XX1000001A1",
      any(h["normalized"] == "XX1000001A1" for h in q["related_hits"]),
      "related=%d" % len(q["related_hits"]))
check("related_hits 附核对书目字段提示",
      all("note" in h for h in q["related_hits"]), "")
kw_hits = res["keyword_hits"]["示例催化剂ZX-1"]
check("关键词召回 ≥2 条且带定位符",
      len(kw_hits) >= 2 and all("line" in h for h in kw_hits),
      "kw_hits=%d" % len(kw_hits))
bad = corpus_scan.run_query(index_path, numbers=["NOT_A_NUMBER"])
check("无法解析查询号不猜测", not bad["queries"][0]["ok"], "")

# ---------------------------------------------------------- 6. 双口径族合并
print("== 6. 双口径族合并 ==")
records = [
    {"record_id": "EX1001",
     "numbers": ["XX1000001A1", "XX1000001B2"],
     "priorities": ["XX2018/000001", "XX2018/000002"],
     "source_locator": "examples/fixtures/corpus/rec_EX1001.txt"},
    {"record_id": "EX1002",
     "numbers": ["XX1000002A1", "XX1000002B2"],
     "priorities": ["XX2018/000002", "XX2018/000003"],
     "source_locator": "examples/fixtures/corpus/rec_EX1002.txt"},
    {"record_id": "EX1003",
     "numbers": ["XX1000003A1"],
     "priorities": ["XX2018/000003", "XX2018/000004"],
     "source_locator": "examples/fixtures/corpus/rec_EX1003.txt"},
    {"record_id": "EX2001",
     "numbers": ["XX1000001B2"],
     "priorities": [],
     "source_locator": "examples/fixtures/corpus/rec_EX2001.txt"},
]
fam_path = os.path.join(tmpdir, "family.json")
fam = family_merge.merge(records)
with open(fam_path, "w", encoding="utf-8") as fh:
    json.dump(fam, fh, ensure_ascii=False, indent=2)
check("simple 族 = 3（优先权集合两两不同）",
      len(fam["simple_families"]) == 3,
      "simple=%d" % len(fam["simple_families"]))
check("extended 族 = 1（共享优先权连通）",
      len(fam["extended_families"]) == 1,
      "extended=%d" % len(fam["extended_families"]))
ext_members = {m["record_id"] for m in fam["extended_families"][0]["members"]} \
    if fam["extended_families"] else set()
check("extended 成员 = {EX1001,EX1002,EX1003}",
      ext_members == {"EX1001", "EX1002", "EX1003"}, str(sorted(ext_members)))
check("simple 与 extended 口径确不同", len(fam["simple_families"])
      != len(fam["extended_families"]), "")
check("无优先权记录单列并带警示",
      len(fam["records_without_priorities"]) == 1
      and fam["records_without_priorities"][0]["record_id"] == "EX2001"
      and "族归属不确定" in fam["records_without_priorities"][0]["warning"],
      "")
check("scope_note 声明观察链接纪律",
      "不保证穷尽" in fam["scope_note"], "")

# ---------------------------------------------------------- 7. scaffold
print("== 7. scaffold 骨架 ==")
with open(os.path.join(FIX, "case_fixture.json"), encoding="utf-8") as fh:
    case = json.load(fh)
skel = scaffold_result.build_skeleton(case, "partial")
check("骨架 case_id 正确", skel["case_id"] == "SYNTH-EXAMPLE-002",
      str(skel["case_id"]))
check("骨架镜像 output_contract 全部字段",
      set(case["output_contract"].keys()) <= set(skel.keys()),
      "missing=%s" % (set(case["output_contract"].keys()) - set(skel.keys())))
check("未填充字段以 null 占位并列入 uncertainty",
      skel["families"] is None
      and any("families" in u for u in skel["uncertainty"]), "")
filled = scaffold_result.deep_merge(skel, {"families": {"note": "test"},
                                           "status": "ok"})
check("深合并填充生效", filled["families"] == {"note": "test"}
      and filled["status"] == "ok"
      and filled["case_id"] == "SYNTH-EXAMPLE-002", "")
skel_bad = scaffold_result.build_skeleton({"unexpected": 1}, "partial")
check("异常形状 case 防御性生成", skel_bad["status"] == "partial"
      and "uncertainty" in skel_bad, "")
out_dir = os.path.join(tmpdir, "out")
rc = scaffold_result.main(["--case", os.path.join(FIX, "case_fixture.json"),
                           "--out", out_dir])
check("scaffold CLI 写出 result.json",
      rc == 0 and os.path.exists(os.path.join(out_dir, "result.json")), "")

# ---------------------------------------------------------- 8. CLI 冒烟
print("== 8. CLI 冒烟测试 ==")
proc = subprocess.run(
    [sys.executable, os.path.join(HERE, "patent_numbers.py"), "normalize",
     "US 10,293,847 B2"],
    capture_output=True, text=True)
cli_ok = proc.returncode == 0
if cli_ok:
    try:
        cli_out = json.loads(proc.stdout)
        cli_ok = cli_out[0]["normalized"] == "US10293847B2"
    except (ValueError, IndexError, KeyError):
        cli_ok = False
check("patent_numbers.py normalize CLI", cli_ok,
      "rc=%d" % proc.returncode)
proc = subprocess.run([sys.executable,
                       os.path.join(HERE, "patent_numbers.py")],
                      capture_output=True, text=True)
check("缺参数退出码 2", proc.returncode == 2, "rc=%d" % proc.returncode)

# ---------------------------------------------------------- 汇总
print("== 汇总 ==")
if FAILURES:
    print("SELF-CHECK FAILED: %d 项失败：%s" % (len(FAILURES),
                                                ", ".join(FAILURES)))
    sys.exit(1)
print("SELF-CHECK PASSED: 全部断言通过")
sys.exit(0)
