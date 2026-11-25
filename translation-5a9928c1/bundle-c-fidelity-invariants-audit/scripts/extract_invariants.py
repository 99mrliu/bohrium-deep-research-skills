#!/usr/bin/env python3
"""extract_invariants.py — 从文本确定性抽取保真不变量。

用法: extract_invariants.py --text FILE --out invariants.json
类别: quantity(数值+单位) | statistic(p/n/CI/效应量) | citation([n]/[n–m]) |
      ref(图表/公式/章节编号) | negation(否定标记) | qualifier(限定/情态标记)
归一化: 全角数字→半角；千分位逗号去除；负号统一；×10^n→e记法；单位小写。
"""
import argparse, json, re

UNITS = (r'%|°C|°|eV|keV|MeV|Ω|cm²|cm2|cm³|m²|mm²|nm²|nm|μm|µm|mm|cm|m|km|'
         r'g|kg|mg|μg|µg|ng|pg|M|mM|μM|µM|nM|pM|mol|mmol|'
         r's|ms|μs|µs|min|h|hr|d|wk|yr|mL|μL|µL|L|'
         r'Pa|kPa|MPa|GPa|J|kJ|cal|W|kW|mW|V|mV|kV|A|mA|rpm|fold|bp|kDa|Da|weeks?|days?|hours?|minutes?|seconds?|years?|months?|'
         r'个百分点|percentage\s*points?|'
         r'毫摩尔|微摩尔|千帕|兆帕|千瓦|毫伏|毫克|微克|纳米|微米|毫米|厘米|千米|摩尔|纳克|千克|毫升|'
         r'毫米汞柱|焦耳|星期|小时|分钟|个|秒|年|月|天|日|升|克|帕|度|瓦|伏|米|周')

CJK_UNIT = {'周': 'weeks', '星期': 'weeks', '天': 'd', '日': 'd', '小时': 'h', '分钟': 'min',
            '秒': 's', '年': 'yr', '个月': 'months', '月': 'months', '毫升': 'ml', '升': 'l',
            '毫克': 'mg', '微克': 'μg', '克': 'g', '千克': 'kg', '纳克': 'ng', '摩尔': 'mol',
            '毫摩尔': 'mmol', '微摩尔': 'μm'.replace('m','mol'), '纳米': 'nm', '微米': 'μm',
            '毫米': 'mm', '厘米': 'cm', '米': 'm', '千米': 'km', '千帕': 'kpa', '兆帕': 'mpa',
            '帕': 'pa', '度': 'deg', '瓦': 'w', '千瓦': 'kw', '伏': 'v', '毫伏': 'mv', '焦耳': 'j',
            '个百分点': 'pctpt', 'percentage points': 'pctpt', 'percentage point': 'pctpt'}

def norm_unit(u):
    if not u:
        return None
    u = u.strip().lower().replace('µ', 'μ')
    u = re.sub(r'\s+', ' ', u)
    return CJK_UNIT.get(u, u)

NUM = r'[−–-]?\d+(?:,\d{3})*(?:\.\d+)?'

def norm_digits(s):
    trans = str.maketrans('０１２３４５６７８９．，', '0123456789.,')
    return s.translate(trans)

def norm_number(tok):
    t = norm_digits(tok).replace(',', '')
    t = t.replace('−', '-').replace('–', '-').replace('—', '-').lstrip('~')
    return t

def extract(text):
    inv = []
    def add(kind, surface, normalized, offset, unit=None):
        inv.append({"kind": kind, "surface": surface.strip(), "normalized": normalized,
                    "unit": unit, "offset": offset})

    t = text
    # quantity: number (+range/±) + optional unit；×10^n
    sci = re.compile(r'(\d+(?:\.\d+)?)\s*[×x]\s*10\^?(-?\d+)')
    for m in sci.finditer(t):
        add("quantity", m.group(0), f"{m.group(1)}e{m.group(2)}", m.start())
    for m in re.finditer(r'(' + NUM + r')(\s*(?:' + UNITS + r')(?![A-Za-z0-9]))?', t):
        num, unit = m.group(1), (m.group(2) or "").strip()
        before = t[max(0, m.start()-1):m.start()]
        after = t[m.end():m.end()+1]
        if before == '[' or after == ']':   # 引用编号不当数值
            continue
        add("quantity", (num + ' ' + unit).strip(), norm_number(num),
            m.start(), norm_unit(unit))
    # ranges: a–b with same unit → 记录为 range
    for m in re.finditer(r'(' + NUM + r')\s*[–—-]\s*(' + NUM + r')(\s*(?:' + UNITS + r')(?![A-Za-z0-9]))?', t):
        add("range", m.group(0).strip(), f"{norm_number(m.group(1))}-{norm_number(m.group(2))}",
            m.start(), norm_unit((m.group(3) or "").strip()))
    # statistics
    for m in re.finditer(r'\bp\s*(<|<=|=|>|>=)\s*(0?\.\d+)', t, flags=re.IGNORECASE):
        add("statistic", m.group(0), f"p{m.group(1)}{norm_number(m.group(2))}", m.start())
    for m in re.finditer(r'\b(n|N)\s*=\s*(\d+)', t):
        add("statistic", m.group(0), f"n={m.group(2)}", m.start())
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\s*%\s*CI', t, flags=re.IGNORECASE):
        add("statistic", m.group(0), f"ci{m.group(1)}", m.start())
    for m in re.finditer(r'\b(HR|OR|RR)\s*=\s*(\d+(?:\.\d+)?)', t):
        add("statistic", m.group(0), f"{m.group(1).lower()}={m.group(2)}", m.start())
    # citations [1], [1, 2], [1–3]
    for m in re.finditer(r'\[(\d+(?:\s*[,，]\s*\d+)*)\]', t):
        nums = sorted({int(x) for x in re.split(r'\s*[,，]\s*', m.group(1))})
        add("citation", m.group(0), ",".join(map(str, nums)), m.start())
    for m in re.finditer(r'\[(\d+)\s*[–—-]\s*(\d+)\]', t):
        lo, hi = int(m.group(1)), int(m.group(2))
        add("citation", m.group(0), ",".join(str(i) for i in range(lo, hi + 1)), m.start())
    # refs
    for m in re.finditer(r'\b(Fig(?:ure)?s?\.?|Table|Tab\.?|Eq(?:uation)?\.?|Section|Sec\.?)\s*\(?([0-9]+(?:\.[0-9]+)?)\)?', t):
        add("ref", m.group(0).strip(), f"{m.group(1).lower()}{m.group(2)}", m.start())
    for m in re.finditer(r'(图|表)\s*([0-9]+(?:\.[0-9]+)?)', t):
        add("ref", m.group(0).strip(),
            f"{'figure' if m.group(1) == '图' else 'table'}{m.group(2)}", m.start())
    # negation / qualifier
    NEG_EN = r'\b(no|not|never|without|neither|nor|nor|fail(?:ed|s|ing)? to|lacks? of|absence of|free of)\b|did not|does not|do not|cannot|can not'
    NEG_ZH = r'未|无|不|没有|沒有|缺乏|未能|并非|并不|绝非|忌'
    for m in re.finditer(NEG_EN, t, flags=re.IGNORECASE):
        add("negation", m.group(0).strip().lower(), "neg", m.start())
    for m in re.finditer(NEG_ZH, t):
        add("negation", m.group(0), "neg", m.start())
    Q_EN = r'\b(may|might|could|suggest(?:s|ed|ing)?|indicat(?:e|es|ed|ing)|appear(?:s|ed|ing)?|seem(?:s|ed|ing)?|approximately|about|roughly|likely|presumably)\b'
    Q_ZH = r'可能|或许|提示|约|大约|大致|倾向于'
    for m in re.finditer(Q_EN, t, flags=re.IGNORECASE):
        add("qualifier", m.group(0).strip().lower(), "qual", m.start())
    for m in re.finditer(Q_ZH, t):
        add("qualifier", m.group(0), "qual", m.start())

    inv.sort(key=lambda x: x["offset"])
    return inv

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    text = open(a.text, encoding="utf-8", errors="replace").read()
    inv = extract(text)
    json.dump({"text_chars": len(text), "invariants": inv},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    from collections import Counter
    c = Counter(i["kind"] for i in inv)
    print(f"{len(inv)} invariants {dict(c)} -> {a.out}")

if __name__ == "__main__":
    main()
