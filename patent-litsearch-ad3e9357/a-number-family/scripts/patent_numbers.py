#!/usr/bin/env python3
"""patent_numbers.py — 专利号规范化库与 CLI（仅标准库）。

覆盖 US/WO/EP/CN/JP/KR 的公开号、授权号、申请号、优先权号；
处理分隔符、kind code、年代零填充；识别并尝试拆分 OCR 粘连号码。

用法：
  python3 patent_numbers.py normalize "US 2020/0123456 A1" ["WO2020/123456" ...]
  python3 patent_numbers.py find <text_file>            # 从文本抽取全部疑似号码
库接口：
  normalize(raw) -> dict(ok, key, country, ntype, serial, kind, confidence, warnings)
  find_numbers(text) -> list[dict(raw, span, parsed, split_event)]
"""
import json
import re
import sys

COUNTRIES = ("US", "WO", "EP", "CN", "JP", "KR")

# (名称, 国家, 类型, 已去分隔符大写串的正则, 规范键构造函数)
# ntype: grant=授权/专利号, pub=公开号, app=申请/优先权号
def _key(cc, nt, serial):
    return "%s-%s-%s" % (cc, nt, serial)

PATTERNS = [
    # 顺序即歧义时的优先解释；US 8 位纯数字优先按申请号并给出歧义警告，
    # 因为裸 8 位串在优先权/申请语境更常见，授权语境通常带 kind code
    ("US 申请(series/6位)", "US", "app",
     re.compile(r"^US(0[1-9]|1[0-8])(\d{6})$"),
     lambda m: (_key("US", "app", m.group(1) + m.group(2)), None)),
    ("US 授权(7-8位+kind)", "US", "grant",
     re.compile(r"^US(\d{7,8})(B1|B2|A|E|H|P1)?$"),
     lambda m: (_key("US", "grant", m.group(1).zfill(8)), m.group(2))),
    ("US 再颁/设计/植物", "US", "grant",
     re.compile(r"^US(RE\d{5}|D\d{6,7}|PP\d{5,6})(E\d?|P\d?)?$"),
     lambda m: (_key("US", "grant", m.group(1)), m.group(2))),
    ("US 公开(年+7位+kind)", "US", "pub",
     re.compile(r"^US(\d{4})(\d{7})(A1|A2|A9)$"),
     lambda m: (_key("US", "pub", m.group(1) + m.group(2)), m.group(3))),
    ("WO 公开(年+5-6位)", "WO", "pub",
     re.compile(r"^WO(\d{4})(\d{5,6})(A1?|A2|A3|A8|A9)?$"),
     lambda m: (_key("WO", "pub", m.group(1) + m.group(2).zfill(6)), m.group(3))),
    ("EP 公开(7位+kind)", "EP", "pub",
     re.compile(r"^EP(\d{7})(A1|A2|A3|A8|B1|B2|B8)?$"),
     lambda m: (_key("EP", "pub", m.group(1)), m.group(2))),
    ("EP 申请(8位.校验)", "EP", "app",
     re.compile(r"^EP(\d{8})(?:\.(\d))?$"),
     lambda m: (_key("EP", "app", m.group(1) + ("." + m.group(2) if m.group(2) else "")), None)),
    ("CN 公开/授权(8-9位+kind)", "CN", "pub",
     re.compile(r"^CN(\d{8,9})(A|B|C|U|Y|S)?$"),
     lambda m: (_key("CN", "pub", m.group(1)), m.group(2))),
    ("CN 申请(年+8位.校验)", "CN", "app",
     re.compile(r"^CN(\d{4})(\d{7,8})(?:\.(\d|X))?$"),
     lambda m: (_key("CN", "app", m.group(1) + m.group(2) + ("." + m.group(3) if m.group(3) else "")), None)),
    ("JP 公开(年+6位+kind)", "JP", "pub",
     re.compile(r"^JP(\d{4})(\d{6})(A|U|T)?$"),
     lambda m: (_key("JP", "pub", m.group(1) + m.group(2)), m.group(3))),
    ("JP 授权(7位+kind)", "JP", "grant",
     re.compile(r"^JP(\d{7})(B2?|U|Y2)?$"),
     lambda m: (_key("JP", "grant", m.group(1)), m.group(2))),
    ("KR 公开/授权(10-13位)", "KR", "pub",
     re.compile(r"^KR(10|20)(\d{4})(\d{5,7})(A|B1|U|Y1)?$"),
     lambda m: (_key("KR", "pub", m.group(1) + m.group(2) + m.group(3).zfill(7)), m.group(4))),
]

SEP_RE = re.compile(r"[\s.,/\-'’()]")
# 原始文本候选：国家码 + 数字/分隔符主体 + 可选 kind 后缀
CANDIDATE_RE = re.compile(
    r"\b(US|WO|EP|CN|JP|KR)\s*[A-Z]{0,2}\d[\d\s.,/\-]{2,24}\d(?:\s?[A-Z]\d?)?")


def _strip(raw):
    return SEP_RE.sub("", raw.upper())


def normalize(raw):
    """规范化单个号码串。永远返回 dict；ok=False 时不猜测。"""
    warnings = []
    if not raw or not raw.strip():
        return {"ok": False, "raw": raw, "warnings": ["空输入"]}
    compact = _strip(raw)
    matches = []
    for name, cc, nt, rx, build in PATTERNS:
        m = rx.match(compact)
        if m:
            key, kind = build(m)
            matches.append({"name": name, "country": cc, "ntype": nt,
                            "key": key, "kind": kind})
    if not matches:
        return {"ok": False, "raw": raw, "normalized": compact,
                "warnings": ["未匹配任何已知号码模式；不猜测格式"]}
    # 歧义处理：典型为 US 8 位纯数字同时命中授权与申请
    if len(matches) > 1:
        warnings.append("歧义格式，命中多个模式：%s；按所列第一解释，需人工核对著录项"
                        % ";".join(x["name"] for x in matches))
    best = matches[0]
    serial = best["key"].rsplit("-", 1)[1]
    return {"ok": True, "raw": raw, "normalized": compact,
            "key": best["key"], "country": best["country"],
            "ntype": best["ntype"], "serial": serial, "kind": best["kind"],
            "confidence": "low" if warnings else ("high" if best["kind"] else "medium"),
            "pattern": best["name"], "warnings": warnings,
            "alternatives": [x["key"] for x in matches[1:]]}


def _max_serial_len(cc):
    return {"US": 11, "WO": 10, "EP": 8, "CN": 13, "JP": 10, "KR": 12}.get(cc, 13)


def try_split_merged(compact):
    """尝试把粘连串拆成两个合法号码。返回 (parts, event)；无法可靠拆分返回 (None, event)。"""
    cc = compact[:2]
    body = compact[2:]
    if cc not in COUNTRIES or len(body) <= _max_serial_len(cc):
        return None, None
    # 仅在内部国家码边界或 kind-code 边界尝试拆分
    cuts = set()
    for i in range(2, len(compact) - 4):
        if compact[i:i + 2] in COUNTRIES:
            cuts.add(i)
        elif compact[i] in "ABCUYST" and compact[i + 1:i + 2].isdigit():
            cuts.add(i + 2)
    cuts = sorted(cuts)
    valid = []
    for i in cuts:
        left, right = compact[:i], compact[i:]
        lp, rp = normalize(left), normalize(right)
        if lp["ok"] and rp["ok"]:
            valid.append((lp, rp))
    if len(valid) == 1:
        event = {"type": "ocr_split", "input": compact, "method": "边界唯一拆分",
                 "warning": "OCR 粘连已按唯一可行边界拆分，需人工核对原文影像"}
        return valid[0], event
    if valid:
        return None, {"type": "ocr_split_failed", "input": compact,
                      "warning": "OCR 粘连存在多个可行拆分(%d 种)，保留原样不猜测" % len(valid)}
    return None, {"type": "ocr_split_failed", "input": compact,
                  "warning": "OCR 粘连无法可靠拆分，保留原样不猜测"}


def find_numbers(text):
    """从文本抽取全部疑似专利号；对超长候选做粘连拆分尝试。"""
    out = []
    for m in CANDIDATE_RE.finditer(text):
        raw = m.group(0)
        compact = _strip(raw)
        parsed = normalize(raw)
        event = None
        if not parsed["ok"] or len(compact[2:]) > _max_serial_len(compact[:2]):
            parts, event = try_split_merged(compact)
            if parts:
                for p in parts:
                    p2 = dict(p)
                    p2["raw"] = raw
                    out.append({"raw": raw, "span": list(m.span()), "parsed": p2,
                                "split_event": event})
                continue
        entry = {"raw": raw, "span": list(m.span()), "parsed": parsed}
        if event:
            entry["split_event"] = event
            entry.setdefault("warnings", []).append(event["warning"])
        out.append(entry)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "normalize":
        raws = argv[2:]
        if not raws:
            print("用法: patent_numbers.py normalize <号码...>", file=sys.stderr)
            return 2
        results = [normalize(x) for x in raws]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(r["ok"] for r in results) else 1
    if cmd == "find":
        if len(argv) < 3:
            print("用法: patent_numbers.py find <文本文件>", file=sys.stderr)
            return 2
        with open(argv[2], encoding="utf-8") as f:
            found = find_numbers(f.read())
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    print("未知命令: %s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
