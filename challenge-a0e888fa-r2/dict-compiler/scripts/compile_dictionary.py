#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compile_dictionary.py — 把案例自带的数据字典/清洗工单文本机械编译为可执行规则草稿。

输入 : 数据字典文本（Markdown 表格 / 条目列表 / 键值行）+ 清洗工单文本
输出 : draft_rules.json  （每条规则带 source 文件+行号+原文）
       parse_report.md   （逐行登记：已解析 / 未解析 / 歧义 / 跳过）

仅识别 references/dictionary_grammar.md 所列写法；无法解析的行一律登记为
未解析项（U 编号），交由人工在 resolutions.json 中裁决，编译器自身不做任何猜测。

退出码: 0 = 正常；3 = 无可执行产物（字典与工单均未编译出任何规则或工单条目）。

确定性: 同一输入必得同一输出；不记录时间戳；不访问网络；仅使用标准库。
"""
import argparse
import json
import re
import sys
from pathlib import Path

VERSION = "1.0"

# ---------------------------------------------------------------- 语法模式 ----
RANGE_BRACKET_RE = re.compile(
    r'^\s*([\[\(])\s*(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)\s*([\]\)])\s*$')
RANGE_ENDASH_RE = re.compile(
    r'^\s*(-?\d+(?:\.\d+)?)\s*[–—]\s*(-?\d+(?:\.\d+)?)\s*$')
LOD_RE = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*(\S.*)?$')
ENTRY_RE = re.compile(r'^([A-Za-z_]\w*)\s*[:：]\s*(.+)$')
SEG_KV_RE = re.compile(
    r'^(单位|哨兵值|哨兵|有效范围|范围|物理界|检出限|检出下限|unit|sentinel|range|lod)'
    r'\s*[=：:]\s*(.+)$', re.IGNORECASE)
SEG_KW_RE = re.compile(
    r'^(单位|哨兵值|哨兵|有效范围|范围|物理界|检出限|检出下限|unit|sentinel|range|lod)'
    r'\s+(.+)$', re.IGNORECASE)
WO_LINE_RE = re.compile(
    r'^\s*(?:[-*]\s+)?(?:(\d+)\s*[.、\)]\s*)?'
    r'(?:\[\s*(WO-?\d+)\s*\]\s*)?(?:(WO-?\d+)\s*[:：]\s*)?(.+?)\s*$')
UNIT_CONV_RE = re.compile(
    r'([A-Za-z_]\w*)\s*(?:由|从)\s*([^\s，。；,、]+?)\s*'
    r'(?:换算为|转换为|→|->)\s*([^\s，。；,、（(]+)')
FACTOR_RE_1 = re.compile(r'[×xX]\s*(\d+(?:\.\d+)?)')
FACTOR_RE_2 = re.compile(r'(\d+(?:\.\d+)?)\s*倍')
DEDUP_KEY_RE = re.compile(r'按\s*([A-Za-z_]\w*)')

# 常见单位对的内置换算系数（确定性查表；查不到即交人工裁决）
UNIT_FACTORS = {
    ("mg/L", "μg/L"): 1000.0, ("mg/L", "ug/L"): 1000.0,
    ("μg/L", "mg/L"): 0.001, ("ug/L", "mg/L"): 0.001,
    ("μg/mL", "mg/L"): 1.0, ("ug/mL", "mg/L"): 1.0,
    ("mg/L", "μg/mL"): 1.0, ("mg/L", "ug/mL"): 1.0,
    ("g/L", "mg/L"): 1000.0, ("mg/L", "g/L"): 0.001,
    ("ng/mL", "μg/L"): 1.0, ("ng/mL", "ug/L"): 1.0,
}

# 工单动作关键词 → 规则类别
ACTION_KEYWORDS = [
    (("缺失", "哨兵", "missing"), "sentinel_missing"),
    (("换算", "单位", "convert", "unit"), "unit_scale"),
    (("去重", "重复", "dedup"), "dedup"),
    (("物理界", "范围", "质控", "越界", "qc"), "range_qc"),
    (("检出限", "检出下限", "lod"), "lod_below"),
]

KW_MAP = {
    "单位": "unit", "unit": "unit",
    "哨兵": "sentinel", "哨兵值": "sentinel", "sentinel": "sentinel",
    "范围": "range", "有效范围": "range", "range": "range",
    "物理界": "physical",
    "检出限": "lod", "检出下限": "lod", "lod": "lod",
}

HEADER_MAP = {
    "字段": "field", "字段名": "field", "名称": "field",
    "field": "field", "column": "field",
    "单位": "unit", "unit": "unit",
    "哨兵": "sentinel", "哨兵值": "sentinel", "缺失标记": "sentinel",
    "sentinel": "sentinel",
    "有效范围": "range", "范围": "range", "range": "range",
    "检出限": "lod", "检出下限": "lod", "lod": "lod",
    "说明": "desc", "备注": "desc", "描述": "desc",
    "desc": "desc", "description": "desc",
}

BLANK_TOKENS = {"blank", "空", "空格", "空字符串"}
NONE_CELLS = {"", "-", "—", "–", "/", "无"}


def num(s):
    """字符串→数值；整数值返回 int 以保证 JSON 输出确定性。"""
    f = float(s)
    return int(f) if f.is_integer() else f


def parse_range_value(val):
    """解析范围写法；不支持则返回 None（交由人工裁决，不猜测）。"""
    m = RANGE_BRACKET_RE.match(val)
    if m:
        return {"lo": num(m.group(2)), "hi": num(m.group(3)),
                "lo_inclusive": m.group(1) == "[",
                "hi_inclusive": m.group(4) == "]"}
    m = RANGE_ENDASH_RE.match(val)
    if m:
        return {"lo": num(m.group(1)), "hi": num(m.group(2)),
                "lo_inclusive": True, "hi_inclusive": True}
    return None


def parse_sentinel_tokens(raw):
    """哨兵 token 列表；blank/空/空格/空字符串 归一为空串。"""
    toks = [t.strip() for t in re.split(r'[,，、/]', raw) if t.strip()]
    return ["" if t.lower() in BLANK_TOKENS else t for t in toks]


class Compiler:
    def __init__(self):
        self.rules = []
        self.unparsed = []
        self.fields = {}          # field -> {"unit":..., "unit_line":...}
        self.workorder_items = []
        self.line_register = []   # 逐行登记（覆盖矩阵与解析报告共用）
        self.sources = []

    # ------------------------------------------------------------ 登记 ----
    def add_rule(self, kind, field, params, path, lineno, raw):
        rid = "R%03d" % (len(self.rules) + 1)
        rule = {"rule_id": rid, "kind": kind, "field": field, "params": params,
                "source": {"file": path, "line": lineno, "text": raw.strip()},
                "origin": "compiler"}
        self.rules.append(rule)
        return rid

    def add_unparsed(self, path, lineno, raw, reason):
        uid = "U%03d" % (len(self.unparsed) + 1)
        self.unparsed.append({"unparsed_id": uid, "file": path, "line": lineno,
                              "text": raw.strip(), "reason": reason})
        return uid

    def register(self, path, lineno, raw, category, detail, rule_ids=None,
                 unparsed_id=None):
        self.line_register.append({
            "file": path, "line": lineno, "text": raw.strip(),
            "category": category, "detail": detail,
            "rule_ids": rule_ids or [], "unparsed_id": unparsed_id})

    # -------------------------------------------------- 单元格/段 级解析 ----
    def handle_cell(self, role, field, val, path, lineno, raw, notes, rule_ids):
        """解析一个单元格/段；返回 None。失败时登记未解析项。"""
        if role == "unit":
            self.fields.setdefault(field, {})
            self.fields[field]["unit"] = val
            self.fields[field]["unit_line"] = lineno
            notes.append("登记单位 %s" % val)
            return
        if role == "sentinel":
            tokens = parse_sentinel_tokens(val)
            if not tokens:
                notes.append("哨兵单元格无可识别 token")
                return
            rid = self.add_rule("sentinel_missing", field,
                                {"tokens": tokens}, path, lineno, raw)
            rule_ids.append(rid)
            notes.append("哨兵 %s → %s" % (val, rid))
            return
        if role in ("range", "physical"):
            rng = parse_range_value(val)
            if rng is None:
                uid = self.add_unparsed(
                    path, lineno, raw,
                    "范围写法无法解析（支持 [a,b] / (a,b) / a–b）：单元格「%s」" % val)
                notes.append("范围单元格「%s」未解析 → %s" % (val, uid))
                self.register(path, lineno, raw, "unparsed",
                              "字段 %s 的范围/物理界单元格未解析" % field,
                              unparsed_id=uid)
                return
            kind = "range_qc" if role == "range" else "physical_bound"
            rid = self.add_rule(kind, field, rng, path, lineno, raw)
            rule_ids.append(rid)
            notes.append("%s %s → %s" % (role, val, rid))
            return
        if role == "lod":
            m = LOD_RE.match(val)
            if not m:
                uid = self.add_unparsed(path, lineno, raw,
                                        "检出限表述无法解析：单元格「%s」" % val)
                notes.append("检出限单元格「%s」未解析 → %s" % (val, uid))
                self.register(path, lineno, raw, "unparsed",
                              "字段 %s 的检出限单元格未解析" % field,
                              unparsed_id=uid)
                return
            params = {"lod": num(m.group(1))}
            if m.group(2):
                params["unit"] = m.group(2).strip()
            rid = self.add_rule("lod_below", field, params, path, lineno, raw)
            rule_ids.append(rid)
            notes.append("检出限 %s → %s" % (val, rid))
            return

    def parse_entry_body(self, field, body, path, lineno, raw):
        """解析 '字段: 段1；段2；…' 的段序列。"""
        notes, rule_ids = [], []
        for seg in re.split(r'[；;]', body):
            seg = seg.strip()
            if not seg:
                continue
            m = SEG_KV_RE.match(seg) or SEG_KW_RE.match(seg)
            if not m:
                notes.append("忽略描述段「%s」" % seg)
                continue
            role = KW_MAP[m.group(1).lower()]
            self.handle_cell(role, field, m.group(2).strip(),
                             path, lineno, raw, notes, rule_ids)
        if rule_ids:
            self.register(path, lineno, raw, "parsed",
                          "；".join(notes), rule_ids=rule_ids)
        else:
            self.register(path, lineno, raw, "parsed",
                          "；".join(notes) or "仅描述，无规则")

    # ------------------------------------------------------------ 字典 ----
    def parse_dictionary(self, path):
        try:
            lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
        except OSError as e:
            print("FATAL 无法读取字典文件 %s: %s" % (path, e), file=sys.stderr)
            sys.exit(3)
        self.sources.append({"file": path, "role": "dictionary",
                             "lines": len(lines)})
        mapping = None  # Markdown 表列映射
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            if not s:
                continue
            if s.startswith("#"):
                self.register(path, i, raw, "skipped", "标题行")
                continue
            if s.startswith(">"):
                self.register(path, i, raw, "skipped", "引用/说明行")
                continue
            if s.startswith("|"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if all(re.fullmatch(r':?-{2,}:?', c or "---") for c in cells):
                    self.register(path, i, raw, "skipped", "表格分隔行")
                    continue
                roles = [HEADER_MAP.get(c, HEADER_MAP.get(c.lower()))
                         for c in cells]
                if "field" in roles:
                    mapping = roles
                    self.register(path, i, raw, "skipped", "表头行")
                    continue
                if mapping is None:
                    uid = self.add_unparsed(path, i, raw, "表格数据行缺少表头")
                    self.register(path, i, raw, "unparsed", "缺少表头",
                                  unparsed_id=uid)
                    continue
                row = {role: cells[j] for j, role in enumerate(mapping)
                       if role and j < len(cells)}
                field = row.get("field", "").strip()
                if not field:
                    uid = self.add_unparsed(path, i, raw, "字段列为空")
                    self.register(path, i, raw, "unparsed", "字段列为空",
                                  unparsed_id=uid)
                    continue
                self.fields.setdefault(field, {})
                notes, rule_ids = [], []
                for role in ("unit", "sentinel", "range", "lod"):
                    val = row.get(role, "").strip()
                    if val in NONE_CELLS:
                        continue
                    self.handle_cell(role, field, val, path, i, raw,
                                     notes, rule_ids)
                if rule_ids or notes:
                    self.register(path, i, raw, "parsed",
                                  "；".join(notes) or "无规则",
                                  rule_ids=rule_ids)
                continue
            m = re.match(r'^[-*]\s+(.+)$', s)
            body = m.group(1) if m else s
            em = ENTRY_RE.match(body)
            if not em:
                uid = self.add_unparsed(
                    path, i, raw,
                    "条目/行格式无法识别（期望 '字段名: 关键字 值；…'）")
                self.register(path, i, raw, "unparsed",
                              "无法识别为 表/条目/键值行", unparsed_id=uid)
                continue
            field, rest = em.group(1), em.group(2)
            self.fields.setdefault(field, {})
            self.parse_entry_body(field, rest, path, i, raw)

    # ------------------------------------------------------------ 工单 ----
    def parse_workorder(self, path):
        try:
            lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
        except OSError as e:
            print("FATAL 无法读取工单文件 %s: %s" % (path, e), file=sys.stderr)
            sys.exit(3)
        self.sources.append({"file": path, "role": "workorder",
                             "lines": len(lines)})
        known = list(self.fields.keys())
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            if not s or s.startswith("#") or s.startswith(">"):
                continue
            m = WO_LINE_RE.match(raw)
            if not m:
                continue
            num_mark, wo1, wo2, text = m.groups()
            has_marker = bool(num_mark or wo1 or wo2
                              or s.startswith("-") or s.startswith("*"))
            if not has_marker:
                self.register(path, i, raw, "skipped", "说明性文字（无条目标记）")
                continue
            low = text.lower()
            actions = [a for kws, a in ACTION_KEYWORDS
                       if any(k in low for k in kws)]
            if not actions:
                self.register(path, i, raw, "skipped",
                              "条目中未见可识别动作关键词")
                continue
            wo_id = wo1 or wo2 or ("WO-L%d" % i)
            fields = [f for f in known
                      if re.search(r'(?<![\w])' + re.escape(f) + r'(?![\w])',
                                   text)]
            item = {"wo_id": wo_id, "file": path, "line": i, "text": text,
                    "fields": fields, "actions": sorted(set(actions))}
            self.workorder_items.append(item)
            rule_ids = []
            # 单位换算条目 → unit_scale 规则
            if "unit_scale" in actions:
                um = UNIT_CONV_RE.search(text)
                if um:
                    field, frm, to = um.groups()
                    fm = FACTOR_RE_1.search(text) or FACTOR_RE_2.search(text)
                    if fm:
                        factor = float(fm.group(1))
                    elif (frm, to) in UNIT_FACTORS:
                        factor = UNIT_FACTORS[(frm, to)]
                    else:
                        uid = self.add_unparsed(
                            path, i, raw,
                            "换算系数缺失且内置单位表无单位对 (%s→%s)" % (frm, to))
                        self.register(path, i, raw, "unparsed",
                                      "工单条目 %s 单位换算无法编译" % wo_id,
                                      unparsed_id=uid)
                        factor = None
                    if factor is not None:
                        params = {"from_unit": frm, "to_unit": to,
                                  "factor": num(str(factor))}
                        rid = self.add_rule("unit_scale", field, params,
                                            path, i, raw)
                        rule_ids.append(rid)
                        du = self.fields.get(field, {}).get("unit")
                        if du and du != frm:
                            item.setdefault("warnings", []).append(
                                "字典登记单位 %s 与工单源单位 %s 不一致" % (du, frm))
            # 去重条目 → dedup 规则
            if "dedup" in actions:
                dm = DEDUP_KEY_RE.search(text)
                if dm:
                    keep = "last" if ("末条" in text or "最后" in text) else "first"
                    rid = self.add_rule(
                        "dedup", dm.group(1),
                        {"key": dm.group(1), "normalize": ["strip", "upper"],
                         "keep": keep}, path, i, raw)
                    rule_ids.append(rid)
            self.register(path, i, raw, "workorder",
                          "工单条目 %s；动作 %s；涉及字段 %s"
                          % (wo_id, item["actions"], fields),
                          rule_ids=rule_ids)

    # ------------------------------------------------------------ 输出 ----
    def write_outputs(self, out_dir):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        draft = {"version": VERSION, "sources": self.sources,
                 "fields": self.fields, "rules": self.rules,
                 "workorder_items": self.workorder_items,
                 "unparsed": self.unparsed,
                 "line_register": self.line_register}
        (out / "draft_rules.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        self.write_parse_report(out / "parse_report.md")

    def write_parse_report(self, path):
        def esc(t):
            return t.replace("|", "\\|")
        L = []
        L.append("# 解析报告（compile_dictionary 生成）")
        L.append("")
        L.append("## 概要")
        for s in self.sources:
            L.append("- 输入（%s）: `%s`（%d 行）"
                     % (s["role"], s["file"], s["lines"]))
        L.append("- 编译规则: %d 条（R001…R%03d）"
                 % (len(self.rules), len(self.rules)))
        L.append("- 未解析/歧义: %d 条 → 须在 resolutions.json 中逐条裁决"
                 % len(self.unparsed))
        L.append("- 工单条目: %d 条" % len(self.workorder_items))
        L.append("")
        L.append("## 未解析 / 歧义项（需人工裁决）")
        L.append("")
        L.append("| 编号 | 文件 | 行号 | 原文 | 原因 |")
        L.append("| --- | --- | --- | --- | --- |")
        for u in self.unparsed:
            L.append("| %s | %s | %d | %s | %s |"
                     % (u["unparsed_id"], u["file"], u["line"],
                        esc(u["text"]), esc(u["reason"])))
        if not self.unparsed:
            L.append("| （无） | | | | |")
        L.append("")
        L.append("## 逐行登记")
        L.append("")
        L.append("| 文件 | 行号 | 分类 | 说明 | 原文 |")
        L.append("| --- | --- | --- | --- | --- |")
        for r in self.line_register:
            L.append("| %s | %d | %s | %s | %s |"
                     % (r["file"], r["line"], r["category"],
                        esc(r["detail"]), esc(r["text"])))
        L.append("")
        L.append("> 分类含义：parsed=已编译为规则；workorder=工单条目；"
                 "unparsed=未解析（需裁决）；skipped=结构性/说明性行。")
        path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="数据字典/工单 → 规则草稿编译器")
    ap.add_argument("--dictionary", action="append", required=True,
                    help="数据字典文本路径（可重复）")
    ap.add_argument("--workorder", action="append", default=[],
                    help="清洗工单文本路径（可重复）")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    c = Compiler()
    for d in args.dictionary:
        c.parse_dictionary(d)
    for w in args.workorder:
        c.parse_workorder(w)
    c.write_outputs(args.out)

    print("compile_dictionary: 规则 %d 条；未解析 %d 条；工单条目 %d 条"
          % (len(c.rules), len(c.unparsed), len(c.workorder_items)))
    if not c.rules and not c.workorder_items:
        print("EXIT 3: 字典与工单均未编译出任何规则/条目", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
