#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selfcheck.py — 本技能的合成夹具自查（仅用 Python 标准库）。

自查项：
  1. 合成 3 项权利要求（1 独立 + 2 从属）可被正确切分，独立/从属标签正确；
  2. 切分结果中每个 quote 均为源文本在对应 span 上的逐字子串；
  3. 对齐中“被收窄的要素”判为 modified，“被删除的要素”判为 removed；
  4. statistics 与按对应表现场重算的结果一致（不信任任何外部计数）；
  5. 措辞闸门对含「保护范围相同」的伪造说明返回退出码 1；对本工具渲染的
     说明返回退出码 0；
  6. 单侧（仅版本 A）情形产出 partial 状态的单侧清单；
  7. 含已声明 OCR 合并边界的文本被标记 contains_ocr_boundary 且相关权利要求
     被标记 crosses_ocr_boundary。

退出码：0 = 全部通过；非 0 = 存在失败项。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

CLAIMS_A = """SYNTHETIC SELFCHECK FIXTURE - all content fabricated; no real patent.
Publication-version claims, synthetic apparatus set.

1. A mounting bracket for a photovoltaic panel, comprising:
a frame member;
a fastener configured to secure the frame member to a rail;
and a damping pad disposed between the frame member and the rail.

2. The mounting bracket of claim 1, wherein the damping pad comprises rubber.

3. The mounting bracket of claim 1 or 2, wherein the frame member is an extruded aluminum profile.
"""

CLAIMS_B = """SYNTHETIC SELFCHECK FIXTURE - all content fabricated; no real patent.
Grant-version claims, synthetic apparatus set.

1. A mounting bracket assembly for a photovoltaic panel, the bracket comprising:
a frame member;
a titanium alloy fastener configured to secure the frame member to a rail.

2. The mounting bracket of claim 1, wherein the frame member is an extruded aluminum profile.
"""

# 说明：对齐按编号配对。版本 A 第 2 项（damping pad）与版本 B 第 2 项（frame
# member）编号相同而主题不同，其 wherein 从句相似度低于阈值，只列为候选；
# 版本 A 第 3 项在版本 B 中无对应编号，判为整项删除。"""

CLAIMS_BOUNDARY = """SYNTHETIC SELFCHECK FIXTURE - all content fabricated; no real patent.
Single observed version with a declared OCR merge boundary.

1. A sensor housing, comprising:
a shell;
===== OCR MERGE BOUNDARY (merged OCR segments, page break) =====
a cover sealingly coupled to the shell.
"""

NOTE_BAD = """# 伪造说明（自查用，故意包含违禁措辞）

经比对，两版本保护范围相同。
"""


class Failure(Exception):
    pass


def run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(HERE, script)] + list(args),
        capture_output=True,
        text=True,
    )


def check(cond, msg):
    if not cond:
        raise Failure(msg)


def assert_verbatim(node_quote, node_span, source, where):
    check(
        source[node_span[0]:node_span[1]] == node_quote,
        "逐字性失败（%s）：quote 不是 source[span] 的子串" % where,
    )


def walk_spans(seg, source):
    for c in seg["claims"]:
        assert_verbatim(c["quote"], c["span"], source, "claim %s" % c["number"])
        if c.get("preamble"):
            assert_verbatim(c["preamble"]["quote"], c["preamble"]["span"], source,
                            "claim %s preamble" % c["number"])
        if c.get("transition"):
            assert_verbatim(c["transition"]["quote"], c["transition"]["span"], source,
                            "claim %s transition" % c["number"])
        for el in c.get("elements", []):
            assert_verbatim(el["quote"], el["span"], source,
                            "claim %s element %s" % (c["number"], el["index"]))


def main() -> int:
    passed = []
    tmp = tempfile.mkdtemp(prefix="claim_differ_selfcheck_")
    pa = os.path.join(tmp, "a.txt")
    pb = os.path.join(tmp, "b.txt")
    pbd = os.path.join(tmp, "boundary.txt")
    pbad = os.path.join(tmp, "note_bad.md")
    for path, content in ((pa, CLAIMS_A), (pb, CLAIMS_B), (pbd, CLAIMS_BOUNDARY), (pbad, NOTE_BAD)):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    try:
        # 1) 切分：3 项（1 独立 + 2 从属）
        r = run("claim_segment.py", "--input", pa, "--output", os.path.join(tmp, "seg_a.json"))
        check(r.returncode == 0, "claim_segment.py 对版本 A 退出码非 0：%s" % r.stderr)
        seg_a = json.load(open(os.path.join(tmp, "seg_a.json"), encoding="utf-8"))
        check(seg_a["num_claims"] == 3, "应切分出 3 项权利要求，实际 %s" % seg_a["num_claims"])
        types = [c["type"] for c in seg_a["claims"]]
        check(types == ["independent", "dependent", "dependent"],
              "独立/从属标签错误：%s" % types)
        check(seg_a["claims"][1]["references"] == [1], "权利要求 2 引用应为 [1]")
        check(seg_a["claims"][2]["references"] == [1, 2], "权利要求 3 引用应为 [1,2]")
        check(seg_a["claims"][0]["transition"] is not None
              and seg_a["claims"][0]["transition"]["quote"].lower() == "comprising",
              "权利要求 1 过渡语应为 comprising")
        check(len(seg_a["claims"][0]["elements"]) == 3,
              "权利要求 1 应切出 3 个要素，实际 %s" % len(seg_a["claims"][0]["elements"]))
        check(not seg_a["segmentation_degraded"], "合成夹具不应降级")
        passed.append("切分：3 项权利要求（1 独立 + 2 从属）标签正确")

        # 2) 逐字性
        walk_spans(seg_a, CLAIMS_A)
        passed.append("逐字性：全部 quote 均为 source[span] 的逐字子串")

        # 3) 对齐：收窄 -> modified；丢弃 -> removed
        r = run("claim_segment.py", "--input", pb, "--output", os.path.join(tmp, "seg_b.json"))
        check(r.returncode == 0, "claim_segment.py 对版本 B 退出码非 0：%s" % r.stderr)
        seg_b = json.load(open(os.path.join(tmp, "seg_b.json"), encoding="utf-8"))
        walk_spans(seg_b, CLAIMS_B)
        r = run("claim_align.py", "--a", os.path.join(tmp, "seg_a.json"),
                "--b", os.path.join(tmp, "seg_b.json"),
                "--output", os.path.join(tmp, "corr.json"))
        check(r.returncode == 0, "claim_align.py 退出码非 0：%s" % r.stderr)
        corr = json.load(open(os.path.join(tmp, "corr.json"), encoding="utf-8"))
        check(corr["status"] == "ok", "双版本合成夹具状态应为 ok，实际 %s" % corr["status"])
        check(len(corr["claim_pairs"]) == 2, "应按编号配成 2 对权利要求，实际 %s" % len(corr["claim_pairs"]))
        pair1 = corr["claim_pairs"][0]
        narrowed = [ep for ep in pair1["element_pairs"]
                    if ep["classification"] == "modified" and ep["a"] and ep["b"]
                    and "titanium alloy fastener" in ep["b"]["quote"]]
        check(narrowed, "收窄要素（a fastener -> a titanium alloy fastener）应判为 modified")
        dropped = [ep for ep in pair1["element_pairs"]
                   if ep["classification"] == "removed" and ep["a"] and "damping pad" in ep["a"]["quote"]]
        check(dropped, "被丢弃要素（damping pad）应判为 removed")
        pair2 = corr["claim_pairs"][1]
        check(pair2["candidates"], "主题不同的同编号从属项应列出低于阈值的候选（不强制配对）")
        check(len(corr["claims_removed"]) == 1 and corr["claims_removed"][0]["number"] == 3,
              "版本 A 权利要求 3 应判为整项删除")
        check(corr["claims_added"] == [], "本夹具不应有整项新增")
        passed.append("对齐：收窄要素=modified；丢弃要素=removed；整项删除与候选策略正确")

        # 4) statistics 重算一致
        recount = {"unchanged": 0, "modified": 0, "added": 0, "removed": 0, "reordered": 0}
        for cp in corr["claim_pairs"]:
            for ep in cp["element_pairs"]:
                recount[ep["classification"]] += 1
        check(corr["statistics"]["element_pairs"] == recount,
              "statistics 与现场重算不一致：%s vs %s" % (corr["statistics"]["element_pairs"], recount))
        check(corr["statistics"]["claims_a"] == 3 and corr["statistics"]["claims_b"] == 2,
              "statistics 中权利要求计数错误")
        passed.append("统计：statistics 与按对应表现场重算结果一致")

        # 5) 渲染 + 闸门
        r = run("scope_note.py", "--table", os.path.join(tmp, "corr.json"),
                "--case-id", "SELFCHECK-SYNTH-0001",
                "--output", os.path.join(tmp, "note.md"))
        check(r.returncode == 0, "scope_note.py 渲染退出码非 0：%s" % r.stderr)
        note = open(os.path.join(tmp, "note.md"), encoding="utf-8").read()
        check("诚实性声明" in note, "渲染说明缺少固定诚实性页脚")
        r = run("scope_note.py", "--gate", os.path.join(tmp, "note.md"))
        check(r.returncode == 0, "本工具渲染的说明应通过闸门，实际退出码 %s：%s" % (r.returncode, r.stderr))
        r = run("scope_note.py", "--gate", pbad)
        check(r.returncode == 1, "含「保护范围相同」的伪造说明应被闸门拒绝（退出码 1），实际 %s" % r.returncode)
        check("保护范围相同" in r.stderr and "第 3 行" in r.stderr,
              "闸门输出应报告违禁短语与行号：%s" % r.stderr)
        passed.append("闸门：伪造说明（含「保护范围相同」）退出码 1；渲染说明退出码 0")

        # 6) 单侧清单
        r = run("claim_align.py", "--a", os.path.join(tmp, "seg_a.json"),
                "--output", os.path.join(tmp, "one.json"))
        check(r.returncode == 0, "单侧模式退出码非 0：%s" % r.stderr)
        one = json.load(open(os.path.join(tmp, "one.json"), encoding="utf-8"))
        check(one["mode"] == "one_sided_inventory" and one["status"] == "partial",
              "单侧模式应为 one_sided_inventory + partial")
        check(len(one["one_sided_claims"]) == 3, "单侧清单应含 3 项权利要求")
        check(one["limits"], "单侧模式必须给出 limits")
        passed.append("单侧：缺失版本时产出 partial 状态的单侧清单")

        # 7) OCR 合并边界
        r = run("claim_segment.py", "--input", pbd, "--output", os.path.join(tmp, "seg_bd.json"))
        check(r.returncode == 0, "边界文本切分退出码非 0：%s" % r.stderr)
        seg_bd = json.load(open(os.path.join(tmp, "seg_bd.json"), encoding="utf-8"))
        check(seg_bd["contains_ocr_boundary"], "应检出已声明的 OCR 合并边界")
        check(seg_bd["claims"][0]["crosses_ocr_boundary"],
              "跨越边界的权利要求 1 应被标记 crosses_ocr_boundary")
        check(any(el.get("crosses_ocr_boundary") for el in seg_bd["claims"][0]["elements"]),
              "跨越边界的要素应被标记")
        passed.append("边界：OCR 合并边界被检出并标记到跨越的权利要求/要素")

    except Failure as exc:
        print("SELF-CHECK FAILED: %s" % exc, file=sys.stderr)
        return 1

    print("selfcheck.py 全部通过（合成夹具，共 %d 项）：" % len(passed))
    for i, p in enumerate(passed, 1):
        print("  %d. %s" % (i, p))
    print("临时目录：%s" % tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
