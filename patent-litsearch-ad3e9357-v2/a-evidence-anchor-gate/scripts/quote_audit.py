#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quote_audit.py — 逐字引用锚点确定性审计器（上游数据真实性门控·裁决步）。

输入：--result result.json + --registry 登记表 JSON。

规则：
  1. 递归收集 result.json 中所有"锚点"：任何同时含字符串字段 `quote`
     以及 `source_sha256`（或 `source_path`）的字典。这天然覆盖
     evidence_records[].quote 以及嵌套在 candidates / extracted_fields
     等任意层级中的引用。
  2. 锚点以 source_sha256 定位登记表条目；若给出 source_path，则其
     basename 必须与登记条目一致，否则判 path/hash 不匹配。
  3. 对 quote 与源文本做空白归一化（连续空白折叠为单个空格、去首尾），
     要求 quote 是源文本的【精确子串】。
  4. 容差模式（容忍 OCR 噪声，允许小编辑距离）仅当两条同时满足才可用：
       a. 登记条目携带预声明 `tolerance: "ocr"`；
       b. 锚点携带 `tolerance_used: true`。
     任何未声明的容差匹配一律判 FAIL。
  5. 文件哈希缺失、quote 找不到、或未声明容差 → 打印失败锚点与原因，exit 1。
     全部通过 → 打印汇总，exit 0。用法/输入错误 → exit 2。

仅使用 Python 标准库。
"""
import argparse
import json
import os
import re
import sys

TOLERANT_SEARCH_TEXT_CAP = 200_000  # 容差滑窗搜索的文本长度上限（超出拒绝容差）


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def iter_anchors(obj, loc="$"):
    if isinstance(obj, dict):
        if isinstance(obj.get("quote"), str) and (
                obj.get("source_sha256") or obj.get("source_path")):
            yield loc, obj
        for k, v in obj.items():
            yield from iter_anchors(v, "%s.%s" % (loc, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_anchors(v, "%s[%d]" % (loc, i))


def lev_within(a, b, maxd):
    """带限编辑距离：len 差超限或距离>maxd 时返回 False。"""
    la, lb = len(a), len(b)
    if abs(la - lb) > maxd:
        return False
    INF = maxd + 1
    prev = {j: j for j in range(0, min(lb, maxd) + 1)}
    for i in range(1, la + 1):
        lo = max(1, i - maxd)
        hi = min(lb, i + maxd)
        cur = {}
        if lo == 1 and i <= maxd:
            cur[0] = i
        ca = a[i - 1]
        for j in range(lo, hi + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev.get(j, INF) + 1,
                         cur.get(j - 1, INF) + 1,
                         prev.get(j - 1, INF) + cost)
        prev = cur
    return prev.get(lb, INF) <= maxd


def tolerant_found(quote, src, maxd):
    """在 src 中滑动窗口寻找与 quote 编辑距离 <= maxd 的子串。"""
    if len(src) > TOLERANT_SEARCH_TEXT_CAP:
        return None  # 文本过大，不做容差判定（返回 None 表示"无法判定"）
    lq = len(quote)
    if lq == 0:
        return False
    first = quote[0]
    for start in range(len(src)):
        if src[start] != first:
            continue
        for wlen in range(max(1, lq - maxd), min(len(src) - start, lq + maxd) + 1):
            if lev_within(quote, src[start:start + wlen], maxd):
                return True
    return False


def entry_text(entry):
    if entry.get("text") is not None:
        return entry["text"]
    tp = entry.get("text_path")
    if tp and os.path.exists(tp):
        with open(tp, "rb") as f:
            return f.read().decode("utf-8", errors="replace")
    return None


def fail(loc, reason, failures):
    failures.append((loc, reason))
    print("FAIL %s: %s" % (loc, reason))


def main(argv=None):
    p = argparse.ArgumentParser(
        description="审计 result.json 中全部引用锚点是否为登记源文件的逐字子串。")
    p.add_argument("--result", required=True, metavar="RESULT_JSON")
    p.add_argument("--registry", required=True, metavar="REGISTRY_JSON")
    args = p.parse_args(argv)

    for path, what in ((args.result, "result"), (args.registry, "registry")):
        if not os.path.exists(path):
            print("错误：%s 文件不存在: %s" % (what, path), file=sys.stderr)
            return 2
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(args.registry, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("错误：JSON 读取失败: %s" % e, file=sys.stderr)
        return 2

    by_hash = {}
    for e in registry.get("entries", []):
        by_hash.setdefault(e.get("sha256"), []).append(e)

    anchors = list(iter_anchors(result))
    if not anchors:
        print("警告：result.json 中未发现任何锚点（含 quote+source_sha256 的对象）。"
              "审计空置通过，但请确认结果确实不含字段级事实声明。")
        print("汇总：0 个锚点，0 失败。")
        return 0

    failures = []
    n_exact = n_tolerant = 0
    for loc, a in anchors:
        quote = a["quote"]
        sha = a.get("source_sha256")
        spath = a.get("source_path")
        if not sha:
            fail(loc, "锚点缺少 source_sha256（无法定位登记文件）", failures)
            continue
        entries = by_hash.get(sha)
        if not entries:
            fail(loc, "登记表中不存在 sha256=%s 的文件（missing file hash）" % sha,
                 failures)
            continue
        entry = entries[0]
        if spath:
            base = os.path.basename(spath)
            if not any(os.path.basename(e.get("path", "")) == base or
                       os.path.basename(e.get("abspath", "")) == base
                       for e in entries):
                fail(loc, "source_path=%s 与 sha256 对应登记条目的路径不匹配" % spath,
                     failures)
                continue
            entry = next(e for e in entries
                         if os.path.basename(e.get("path", "")) == base or
                         os.path.basename(e.get("abspath", "")) == base)
        text = entry_text(entry)
        if text is None:
            fail(loc, "登记条目无可用文本（text_extraction=%s），无法核验引用"
                 % entry.get("text_extraction"), failures)
            continue
        q = norm(quote)
        t = norm(text)
        if q in t:
            n_exact += 1
            continue
        # 精确匹配失败：只有双方均已声明才允许容差匹配
        declared = entry.get("tolerance") == "ocr" and a.get("tolerance_used") is True
        if not declared:
            maxd = max(2, len(q) // 20)
            near = tolerant_found(q, t, maxd) if len(q) >= 4 else False
            if near:
                missing = []
                if entry.get("tolerance") != "ocr":
                    missing.append("源文件未预声明 tolerance=ocr")
                if a.get("tolerance_used") is not True:
                    missing.append("锚点未声明 tolerance_used:true")
                fail(loc, "quote 非逐字子串，存在疑似 OCR 噪声的近似匹配，但容差未声明"
                          "（%s）—— 未声明的容差匹配一律判失败（undeclared tolerance）"
                     % "；".join(missing), failures)
            else:
                fail(loc, "quote 不是源文件 %s 的逐字子串（quote not found）"
                     % os.path.basename(entry.get("path", "?")), failures)
            continue
        maxd = max(2, len(q) // 20)
        verdict = tolerant_found(q, t, maxd)
        if verdict is True:
            n_tolerant += 1
        elif verdict is None:
            fail(loc, "源文本超过容差搜索上限（%d 字符），无法执行容差匹配"
                 % TOLERANT_SEARCH_TEXT_CAP, failures)
        else:
            fail(loc, "已声明容差，但 quote 与源文本任何窗口的编辑距离仍 > %d"
                 % maxd, failures)

    total = len(anchors)
    if failures:
        print("汇总：%d 个锚点，%d 失败（精确通过 %d，容差通过 %d）。审计不通过。"
              % (total, len(failures), n_exact, n_tolerant))
        return 1
    print("汇总：%d 个锚点全部通过（精确 %d，声明式容差 %d）。审计通过。"
          % (total, n_exact, n_tolerant))
    return 0


if __name__ == "__main__":
    sys.exit(main())
