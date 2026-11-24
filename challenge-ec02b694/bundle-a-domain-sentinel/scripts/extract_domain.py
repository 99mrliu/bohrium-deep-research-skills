#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_domain.py — 可行域约束抽取器（domain-sentinel 第 1 步）

输入：
  --case      case.json 路径（显式字段 parameter_domains/constraints/targets/parameters 优先）
  --materials 材料路径（可多次；可为文件或目录；仅扫描 .txt/.md/.csv/.json；目录递归）
  --out       domain.json 输出路径（默认 /app/work/domain.json）

行为契约：
  - 仅 Python 3 标准库，无网络。
  - 任何输入不得 traceback 崩溃；失败时仍尽量写出（可能是空的）domain.json，
    并在 extraction_log.errors / uncertainty 中记录。
  - 只记录有原文证据（file/line/quote）的约束；任务提及但找不到依据的参数
    列入 ungrounded_parameters，绝不编造数值。
退出码：0 = 正常完成（含部分抽取）；1 = 参数级致命错误（仍尝试落盘）。
"""
import argparse
import json
import os
import re
import sys

SCHEMA_VERSION = "1.0"

NUM = r"(\d+(?:\.\d+)?)"
# 单位：长单位在前，避免 "mL/min" 被 "mL" 截断、"°C/min" 被 "°C" 截断
UNIT = (
    r"(°C/min|℃/min|K/min|mL/min|ml/min|L/min|sccm|slm|"
    r"MPa|kPa|Pa|mbar|bar|atm|°C|℃|K|rpm|r/min|wt%|vol%|mol/L|mmol|"
    r"mA|mV|kV|V|kW|W|mg|g|kg|mL|L|mm|cm|min|h|s|%)"
)

UNIT_CANON = {u"℃": u"°C", u"℃/min": u"°C/min", u"ml/min": u"mL/min", u"r/min": u"rpm"}

DASH = r"(?:[–—\-~～]|至|到)"

P_AMBIENT_RANGE = re.compile(
    r"(?:室温|常温|环境温度|ambient)\s*" + DASH + r"\s*" + NUM + r"\s*" + UNIT, re.I)
P_RANGE = re.compile(NUM + r"\s*" + DASH + r"\s*" + NUM + r"\s*" + UNIT)
P_TEMP_LIMIT = re.compile(
    r"耐温(?:上限|极限|温度)?\s*[:：]?\s*[≤>=<~～\s]*" + NUM + r"\s*" + UNIT)
P_UPPER = re.compile(
    r"(?:≤|<=|≦|不超过|不得超过|未超过|不高于|上限|最大值|最大|低于|max)\s*[:：]?\s*[≤>=<~～\s]*"
    + NUM + r"\s*" + UNIT, re.I)
P_LOWER = re.compile(
    r"(?:≥|>=|≧|不低于|不少于|下限|最小值|最小|高于)\s*[:：]?\s*[≤>=<~～\s]*"
    + NUM + r"\s*" + UNIT, re.I)
P_STEP = re.compile(r"(?:步进|步长|step)\s*[:：]?\s*" + NUM + r"\s*" + UNIT, re.I)
P_MUTEX_GROUP = re.compile(r"互斥组\s*[:：]?\s*[（(]?\s*([A-Za-z0-9_\-一-鿿]+)\s*[）)]?")
P_MUTEX_PAIR = re.compile(
    r"([一-鿿A-Za-z0-9_（）()]{2,24}?)\s*(?:与|和|、)\s*([一-鿿A-Za-z0-9_（）()]{2,24}?)\s*"
    r"(?:不能同时|不可同时|互斥)")

STRIP_WORDS = [u"量程", u"范围", u"上限", u"下限", u"耐温极限", u"耐温", u"步进", u"步长",
               u"最大值", u"最小值", u"最大", u"最小", u"控制", u"参数", u"说明", u"备注"]
TRAILING_ADVERBS = u"均都应需须请"

SAFETY_HINTS = [u"耐温", u"安全", u"危险", u"失活", u"爆炸", u"safety", u"hazard"]

EXPLICIT_KEYS = ["parameter_domains", "constraints", "domain", "parameter_constraints"]
TARGET_KEYS = ["targets", "target_values", "objectives"]
MENTION_KEYS = ["parameters", "expected_parameters", "parameters_of_interest"]
TEXT_EXTS = (".txt", ".md", ".csv", ".json")

LOWER_KEYS = ("lower", "min", "low", "minimum")
UPPER_KEYS = ("upper", "max", "high", "maximum")


def canon_unit(u):
    if not u:
        return None
    u = u.strip()
    return UNIT_CANON.get(u, u)


def to_float(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def normalize_name(name):
    if not name:
        return ""
    return re.sub(r"[\s_]+", "", str(name)).lower()


def clean_param(prefix, safety=False):
    """从数值模式之前的文本中清理出参数名；清理不掉则返回 None。"""
    if not prefix:
        return None
    parts = [seg for seg in re.split(r"[:：]", prefix) if seg.strip()]
    p = parts[-1] if parts else ""
    p = re.sub(r"^[\s\d\.、·•\-*\)）\(（#>]+", "", p)
    for w in STRIP_WORDS:
        p = p.replace(w, "")
    p = p.strip(u" ：:，,。.；;（）()【】[]")
    p = p.rstrip(TRAILING_ADVERBS)
    if len(p) > 30:
        p = p[-30:]
    if safety and p and u"温度" not in p:
        p += u"温度"
    return p if p else None


def make_constraint(parameter, unit, lower, upper, step, mutex_group,
                    fname, lineno, quote, safety=False, origin="text"):
    return {
        "parameter": parameter,
        "unit": unit,
        "lower": lower,
        "upper": upper,
        "step": step,
        "mutex_group": mutex_group,
        "safety_related": bool(safety),
        "origin": origin,
        "source": {"file": fname, "line": lineno, "quote": (quote or "").strip()[:300]},
    }


def is_safety_quote(text):
    t = (text or "").lower()
    return any(h.lower() in t for h in SAFETY_HINTS)


def extract_from_line(line, fname, lineno):
    """对单行文本按优先级匹配，返回约束列表。绝不抛出异常。"""
    out = []
    text = line.strip()
    if len(text) < 4:
        return out
    try:
        bound_found = False
        m = P_AMBIENT_RANGE.search(text)
        if m:
            name = clean_param(text[:m.start()])
            if name:
                out.append(make_constraint(name, canon_unit(m.group(2)), None,
                                           to_float(m.group(1)), None, None,
                                           fname, lineno, text,
                                           safety=is_safety_quote(text)))
                bound_found = True
        if not bound_found:
            m = P_RANGE.search(text)
            if m:
                name = clean_param(text[:m.start()])
                if name:
                    out.append(make_constraint(name, canon_unit(m.group(3)),
                                               to_float(m.group(1)), to_float(m.group(2)),
                                               None, None, fname, lineno, text,
                                               safety=is_safety_quote(text)))
                    bound_found = True
        if not bound_found:
            m = P_TEMP_LIMIT.search(text)
            if m:
                name = clean_param(text[:m.start()], safety=True)
                if name:
                    out.append(make_constraint(name, canon_unit(m.group(2)), None,
                                               to_float(m.group(1)), None, None,
                                               fname, lineno, text, safety=True))
                    bound_found = True
        if not bound_found:
            m = P_UPPER.search(text)
            if m:
                name = clean_param(text[:m.start()])
                if name:
                    out.append(make_constraint(name, canon_unit(m.group(2)), None,
                                               to_float(m.group(1)), None, None,
                                               fname, lineno, text,
                                               safety=is_safety_quote(text)))
                    bound_found = True
        if not bound_found:
            m = P_LOWER.search(text)
            if m:
                name = clean_param(text[:m.start()])
                if name:
                    out.append(make_constraint(name, canon_unit(m.group(2)),
                                               to_float(m.group(1)), None, None, None,
                                               fname, lineno, text,
                                               safety=is_safety_quote(text)))
                    bound_found = True
        # 步进：可与界限在同一行共存
        for m in P_STEP.finditer(text):
            name = clean_param(text[:m.start()])
            if name:
                out.append(make_constraint(name, canon_unit(m.group(2)), None, None,
                                           to_float(m.group(1)), None,
                                           fname, lineno, text,
                                           safety=is_safety_quote(text)))
        # 互斥
        if (u"互斥" in text) or (u"不能同时" in text) or (u"不可同时" in text):
            gm = P_MUTEX_GROUP.search(text)
            group = gm.group(1) if gm else u"mutex_%s_%d" % (os.path.basename(fname), lineno)
            pm = P_MUTEX_PAIR.search(text)
            members = []
            if pm:
                for raw in pm.groups():
                    c = clean_param(raw)
                    if c:
                        members.append(c)
            if not members:
                out.append(make_constraint(u"__mutex_note__", None, None, None, None,
                                           group, fname, lineno, text))
            else:
                for mem in members:
                    out.append(make_constraint(mem, None, None, None, None, group,
                                               fname, lineno, text))
    except Exception:
        return out
    return out


def read_text(path):
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def gather_files(materials, exclude_path):
    files, skipped = [], []
    seen = set()

    def add(p):
        ap = os.path.abspath(p)
        if ap in seen:
            return
        seen.add(ap)
        if exclude_path and ap == os.path.abspath(exclude_path):
            skipped.append({"path": p, "reason": "case file itself"})
            return
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                for n in sorted(names):
                    add(os.path.join(root, n))
            return
        if not os.path.isfile(p):
            skipped.append({"path": p, "reason": "not a file / missing"})
            return
        if not p.lower().endswith(TEXT_EXTS):
            skipped.append({"path": p, "reason": "unsupported extension (PDF 等需先 pdftotext)"})
            return
        files.append(p)

    for m in materials or []:
        add(m)
    return files, skipped


def parse_explicit_constraints(case_data, case_path):
    """从 case.json 显式字段解析约束；容忍 dict 与 list 两种形态。"""
    cons, mentioned, targets = [], [], {}
    if not isinstance(case_data, dict):
        return cons, mentioned, targets
    quote_src = {"file": case_path, "line": None}

    def entry_to_constraint(name, e):
        if not isinstance(e, dict):
            return None
        lower = next((to_float(e.get(k)) for k in LOWER_KEYS if to_float(e.get(k)) is not None), None)
        upper = next((to_float(e.get(k)) for k in UPPER_KEYS if to_float(e.get(k)) is not None), None)
        step = to_float(e.get("step"))
        unit = e.get("unit")
        mutex = e.get("mutex_group") or e.get("mutex")
        param = e.get("parameter") or e.get("name") or name
        if not param:
            return None
        return make_constraint(str(param), unit, lower, upper, step, mutex,
                               case_path, None,
                               json.dumps(e, ensure_ascii=False)[:300],
                               safety=bool(e.get("safety_related")) or is_safety_quote(str(e)),
                               origin="case_explicit")

    for key in EXPLICIT_KEYS:
        block = case_data.get(key)
        if isinstance(block, dict):
            for name, e in block.items():
                c = entry_to_constraint(name, e)
                if c:
                    cons.append(c)
        elif isinstance(block, list):
            for e in block:
                c = entry_to_constraint(None, e)
                if c:
                    cons.append(c)
    for key in TARGET_KEYS:
        block = case_data.get(key)
        if isinstance(block, dict):
            for k, v in block.items():
                fv = to_float(v)
                if fv is not None:
                    targets[str(k)] = fv
    for key in MENTION_KEYS:
        block = case_data.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, str):
                    mentioned.append(item)
                elif isinstance(item, dict):
                    nm = item.get("parameter") or item.get("name")
                    if nm:
                        mentioned.append(str(nm))
    return cons, mentioned, targets


def main(argv=None):
    parser = argparse.ArgumentParser(description="domain-sentinel: 可行域约束抽取")
    parser.add_argument("--case", required=True, help="case.json 路径")
    parser.add_argument("--materials", action="append", default=[],
                        help="材料文件或目录，可多次指定；缺省时读取 case.json 的 materials 字段")
    parser.add_argument("--out", default="/app/work/domain.json", help="domain.json 输出路径")
    args = parser.parse_args(argv)

    log = {"files_scanned": [], "files_skipped": [], "errors": [], "warnings": [],
           "constraints_extracted": 0}
    uncertainty = []
    constraints, mentioned, targets = [], [], {}
    case_data = None

    # 1) 读取 case.json
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case_data = json.load(f)
    except Exception as e:
        log["errors"].append("case.json 读取/解析失败: %s: %s" % (args.case, e))
        uncertainty.append("case.json 不可用，显式约束与任务提及参数均无法解析；可行域可能不完整")

    if isinstance(case_data, dict):
        try:
            c_exp, mentioned, targets = parse_explicit_constraints(case_data, args.case)
            constraints.extend(c_exp)
        except Exception as e:
            log["errors"].append("显式约束解析失败: %s" % e)

    # 2) 确定材料清单
    materials = list(args.materials)
    if not materials and isinstance(case_data, dict):
        raw = case_data.get("materials")
        if isinstance(raw, list):
            base = os.path.dirname(os.path.abspath(args.case))
            for m in raw:
                if isinstance(m, str):
                    cand = m if os.path.isabs(m) else os.path.join(base, m)
                    materials.append(cand)
    if not materials:
        log["warnings"].append("未提供任何材料路径")
        uncertainty.append("无材料可扫描，可行域仅来自 case.json 显式字段（若有）")

    files, skipped = gather_files(materials, args.case)
    log["files_skipped"].extend(skipped)

    # 3) 逐文件逐行规则抽取
    for path in files:
        content = read_text(path)
        if content is None:
            log["files_skipped"].append({"path": path, "reason": "read failed"})
            continue
        log["files_scanned"].append(path)
        rel = os.path.relpath(path) if os.path.exists(path) else path
        for i, line in enumerate(content.splitlines(), start=1):
            try:
                constraints.extend(extract_from_line(line, rel, i))
            except Exception as e:
                log["warnings"].append("行抽取异常 %s:%d: %s" % (rel, i, e))

    # 4) ungrounded：任务提及但无任何约束依据
    constrained = {normalize_name(c["parameter"]) for c in constraints
                   if c.get("parameter") and c["parameter"] != u"__mutex_note__"}
    ungrounded = []
    for name in mentioned:
        if normalize_name(name) not in constrained:
            ungrounded.append(name)
    if ungrounded:
        uncertainty.append(
            u"以下任务提及的参数未找到任何约束依据，已列入 ungrounded_parameters；"
            u"不得为其编造数值，相关建议须降级或请求人工确认: " + u", ".join(ungrounded))
    if not constraints:
        uncertainty.append(u"未抽取到任何约束；任何参数推荐都将是 ungrounded，"
                           u"最终 status 不得为 success")

    log["constraints_extracted"] = len(constraints)
    domain = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "extract_domain.py",
        "source_case": args.case,
        "case_id": case_data.get("case_id") if isinstance(case_data, dict) else None,
        "targets": targets,
        "constraints": constraints,
        "ungrounded_parameters": ungrounded,
        "uncertainty": uncertainty,
        "extraction_log": log,
    }

    # 5) 落盘：任何情况下都尝试写出
    try:
        outdir = os.path.dirname(os.path.abspath(args.out))
        if outdir and not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(domain, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write("extract_domain: 无法写出 %s: %s\n" % (args.out, e))
        return 1

    sys.stderr.write("extract_domain: %d 条约束, %d 个 ungrounded 参数 -> %s\n"
                     % (len(constraints), len(ungrounded), args.out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # 兜底：绝不 traceback 崩溃
        sys.stderr.write("extract_domain: 未捕获异常（已抑制 traceback）: %s\n" % e)
        sys.exit(1)
