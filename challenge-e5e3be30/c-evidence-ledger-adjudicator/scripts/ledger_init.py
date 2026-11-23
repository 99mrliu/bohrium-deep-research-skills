#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_init.py — 从 claims.json 生成每条论断的证据台账骨架（含锚点预提取）。

用法:
    python3 ledger_init.py CLAIMS_JSON --outdir DIR [--prefix ledger-] [--force]

CLAIMS_JSON 接受两种形态:
    {"claims": [{"claim_id": "C1", "claim": "..."}, ...]}
    [{"claim_id": "C1", "claim": "..."}, ...]

锚点预提取（启发式，模型可在台账中增删修正）:
    number      数值（含 30% / 0.3 / thirty percent / 百分之三十 等变体）
    comparator  比较词及反义对（higher<->lower / 提升<->降低 / 显著 等）
    negation    否定词（no/not/never/without/无/没有/未/不）
    condition   条件短语（在...中/下、对于...、...患者/成人、in/among ... patients 等）
    causal      因果词（导致/引起/由于/causes/leads to/due to 等）
    quantifier  范围量词（all/only/any/every/none/所有/任何/仅/只/都）

退出码: 0 成功; 1 输入结构错误; 2 IO/用法错误。
纯 Python3 标准库。
"""
import argparse
import json
import os
import re
import sys

SCHEMA_VERSION = "1.0"
CORE_TYPES = {"number", "comparator", "negation"}

# ---------------------------------------------------------------- 数字词转换
CN_DIGITS = "零一二三四五六七八九"
EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
           "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
           "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
           "eighty", "ninety"]


def int_to_cn(n):
    """0..999 的整数转中文数词（简化实现）。"""
    if n < 0 or n > 999:
        return str(n)
    if n < 10:
        return CN_DIGITS[n]
    if n < 20:
        return "十" + (CN_DIGITS[n % 10] if n % 10 else "")
    if n < 100:
        return CN_DIGITS[n // 10] + "十" + (CN_DIGITS[n % 10] if n % 10 else "")
    return ("一百" if n < 200 else CN_DIGITS[n // 100] + "百") + (
        "" if n % 100 == 0 else
        ("零" + CN_DIGITS[n % 10] if n % 100 < 10 else int_to_cn(n % 100)))


def int_to_en(n):
    """0..99 的整数转英文数词。"""
    if n < 20:
        return EN_ONES[n]
    if n < 100:
        return EN_TENS[n // 10] + ("-" + EN_ONES[n % 10] if n % 10 else "")
    return str(n)


def cn_to_int(s):
    """简化中文数词解析：八 / 十五 / 三十 / 三十五 / 一百。"""
    s = s.strip().replace("两", "二")
    if not s:
        return None
    if s == "十":
        return 10
    if "百" in s:
        head, _, tail = s.partition("百")
        h = CN_DIGITS.find(head) if head else 1
        t = cn_to_int(tail) if tail else 0
        if h < 0 or t is None:
            return None
        return h * 100 + t
    if "十" in s:
        head, _, tail = s.partition("十")
        h = CN_DIGITS.find(head) if head else 1
        t = CN_DIGITS.find(tail) if tail else 0
        if h < 0 or t < 0:
            return None
        return h * 10 + t
    idx = CN_DIGITS.find(s)
    return idx if idx >= 0 else None


EN_WORD2NUM = {w: i for i, w in enumerate(EN_ONES)}
EN_WORD2NUM.update({w: i * 10 for i, w in enumerate(EN_TENS) if w})


def number_variants(raw):
    """为一个数值锚点生成等价变体（30% <-> 0.3 <-> thirty percent <-> 百分之三十）。"""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([%％])?\s*$", raw)
    if not m:
        return [raw]
    val = float(m.group(1))
    is_pct = bool(m.group(2))
    variants = []

    def add(x):
        if x and x not in variants:
            variants.append(x)

    add(raw.strip())
    pct = None
    if is_pct:
        pct = val
    elif 0 < val < 1:
        pct = val * 100.0
    if pct is not None:
        frac = pct / 100.0
        add("%g%%" % pct)
        add("%g％" % pct)
        add("%g" % frac)
        if abs(pct - round(pct)) < 1e-9 and 0 <= pct <= 100:
            p = int(round(pct))
            add("%s percent" % int_to_en(p).replace("-", " "))
            add("百分之%s" % int_to_cn(p))
    if abs(val - round(val)) < 1e-9 and 0 <= val <= 99:
        n = int(round(val))
        add("%g" % val)
        add(int_to_en(n).replace("-", " "))
        add(int_to_cn(n))
    return variants


# ---------------------------------------------------------------- 词表
# (词, 反义词)；反义词为 None 表示无直接反义对
COMPARATORS = [
    ("significantly", None), ("higher", "lower"), ("lower", "higher"),
    ("greater", "less"), ("less", "greater"), ("more", "fewer"),
    ("fewer", "more"), ("increased", "decreased"), ("decreased", "increased"),
    ("increase", "decrease"), ("decrease", "increase"),
    ("reduced", "increased"), ("reduce", "increase"),
    ("improved", "worsened"), ("improve", "worsen"),
    ("better", "worse"), ("worse", "better"),
    ("提升", "降低"), ("降低", "提升"), ("高于", "低于"), ("低于", "高于"),
    ("增加", "减少"), ("减少", "增加"), ("改善", "恶化"), ("恶化", "改善"),
    ("升高", "下降"), ("下降", "升高"), ("显著", None), ("优于", "劣于"),
]
NEGATIONS_EN = ["no", "not", "never", "without"]
NEGATIONS_CN = ["没有", "无", "未", "不"]
CAUSAL = ["导致", "引起", "由于", "因为", "causes", "leads to", "due to",
          "results in", "because"]
QUANTIFIERS_EN = ["all", "only", "any", "every", "none"]
QUANTIFIERS_CN = ["所有", "任何", "仅", "只", "都"]

CONDITION_PATTERNS = [
    r"在([^，。；,.;]{1,30}?)(?:中|下|后)(?=[，。；,.; ]|$)",
    r"对于([^，。；,.;]{1,30}?)[，。；,.;]",
    r"(?<![\w一-鿿])([\w一-鿿（）() ]{1,20}?(?:患者|成人|儿童|人群|女性|男性|老年人))",
    r"\b(?:in|among)\s+([A-Za-z0-9 \-]{2,40}?(?:patients|adults|subjects|women|men|children))\b",
]

# 数值前后若是 ASCII 字母/数字则视为标识符内部（如 HbA1c 中的 "1"），不提取
RE_NUMBER = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?\s*[%％]?(?![A-Za-z])")
RE_PCT_EN = re.compile(r"\b([A-Za-z]+(?:-[A-Za-z]+)?)\s+percent\b", re.I)
RE_PCT_CN = re.compile(r"百分之([零一二三四五六七八九十百]+)")


def extract_anchors(text):
    """返回锚点列表，按在原文中出现位置排序并赋 id A1..An。"""
    found = []  # (pos, type, text, extra)

    for m in RE_NUMBER.finditer(text):
        raw = m.group(0).strip()
        found.append((m.start(), "number", raw,
                      {"variants": number_variants(raw)}))
    for m in RE_PCT_EN.finditer(text):
        word = m.group(1).lower().replace("-", " ")
        n = EN_WORD2NUM.get(word)
        if n is None and " " in word:
            a, b = word.split(" ", 1)
            if a in EN_WORD2NUM and b in EN_WORD2NUM:
                n = EN_WORD2NUM[a] + EN_WORD2NUM[b]
        if n is not None:
            found.append((m.start(), "number", m.group(0),
                          {"variants": number_variants("%d%%" % n)}))
    for m in RE_PCT_CN.finditer(text):
        n = cn_to_int(m.group(1))
        if n is not None:
            found.append((m.start(), "number", m.group(0),
                          {"variants": number_variants("%d%%" % n)}))

    lower = text.lower()
    for word, ant in COMPARATORS:
        if re.search(r"[a-z]", word):
            m = re.search(r"\b%s\b" % re.escape(word), lower)
        else:
            m = re.search(re.escape(word), text)
        if m:
            found.append((m.start(), "comparator", m.group(0),
                          {"antonym": ant}))

    for w in NEGATIONS_EN:
        m = re.search(r"\b%s\b" % w, lower)
        if m:
            found.append((m.start(), "negation", m.group(0), {}))
    for w in NEGATIONS_CN:
        i = text.find(w)
        if i >= 0:
            found.append((i, "negation", w, {}))

    for pat in CONDITION_PATTERNS:
        m = re.search(pat, text)
        if m:
            frag = m.group(0).strip().strip("，。；,.; ")
            found.append((m.start(), "condition", frag, {}))

    lower_full = lower
    for w in CAUSAL:
        if re.search(r"[a-z]", w):
            m = re.search(r"\b%s\b" % re.escape(w), lower_full)
        else:
            m = re.search(re.escape(w), text)
        if m:
            found.append((m.start(), "causal", m.group(0), {}))

    for w in QUANTIFIERS_EN:
        m = re.search(r"\b%s\b" % w, lower)
        if m:
            found.append((m.start(), "quantifier", m.group(0), {}))
    for w in QUANTIFIERS_CN:
        i = text.find(w)
        if i >= 0:
            found.append((i, "quantifier", w, {}))

    found.sort(key=lambda x: (x[0], -len(x[2])))
    anchors, seen = [], set()
    for pos, atype, atext, extra in found:
        key = (atype, atext.lower())
        if key in seen:
            continue
        # 同类型锚点若已是已接受锚点文本的子串，则视为重复（如条件长短两式）
        if any(atype == a["type"] and atext != a["text"]
               and atext.lower() in a["text"].lower() for a in anchors):
            continue
        seen.add(key)
        anchor = {"id": "A%d" % (len(anchors) + 1), "type": atype,
                  "text": atext, "core": atype in CORE_TYPES}
        anchor.update(extra)
        anchors.append(anchor)
    return anchors


def build_ledger(claim_id, claim_text):
    return {
        "schema_version": SCHEMA_VERSION,
        "claim_id": claim_id,
        "claim_text": claim_text,
        "anchors": extract_anchors(claim_text),
        "evidence": [],
        "adjudication": None,
    }


def load_claims(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: 无法读取 claims 文件 %s: %s" % (path, e), file=sys.stderr)
        sys.exit(2)
    items = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        print("ERROR: claims 文件结构错误：应为非空列表或含 'claims' 列表的对象",
              file=sys.stderr)
        sys.exit(1)
    out = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or "claim" not in it:
            print("ERROR: 第 %d 条论断缺少 'claim' 字段" % (i + 1), file=sys.stderr)
            sys.exit(1)
        cid = str(it.get("claim_id") or "C%d" % (i + 1))
        out.append((cid, str(it["claim"])))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从 claims.json 生成每条论断的证据台账骨架（含锚点预提取）。")
    ap.add_argument("claims", help="claims.json 路径")
    ap.add_argument("--outdir", default=".", help="台账输出目录（默认当前目录）")
    ap.add_argument("--prefix", default="ledger-", help="输出文件名前缀")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的台账文件")
    args = ap.parse_args(argv)

    claims = load_claims(args.claims)
    try:
        os.makedirs(args.outdir, exist_ok=True)
    except OSError as e:
        print("ERROR: 无法创建输出目录 %s: %s" % (args.outdir, e), file=sys.stderr)
        return 2

    rc = 0
    for cid, ctext in claims:
        ledger = build_ledger(cid, ctext)
        path = os.path.join(args.outdir, "%s%s.json" % (args.prefix, cid))
        if os.path.exists(path) and not args.force:
            print("ERROR: %s 已存在（用 --force 覆盖）" % path, file=sys.stderr)
            rc = 1
            continue
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(ledger, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print("ERROR: 写入 %s 失败: %s" % (path, e), file=sys.stderr)
            return 2
        print("已生成 %s（锚点 %d 个：%s）" % (
            path, len(ledger["anchors"]),
            ", ".join("%s:%s" % (a["id"], a["type"]) for a in ledger["anchors"])
            or "无"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
