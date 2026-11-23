#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compile_report.py — report-compiler：台账驱动的复现报告编译器。

核心主张：报告是编译产物。人只写台账（六个机器可读 JSON），报告里的每个
数字都由本脚本从台账注入，并登记进 report_map.json 供 audit_report.py 对账。

用法：
    python3 compile_report.py --ledgers <台账目录> --out <输出目录> [--svg]

退出码：
    0  编译完成（含 partial 降级：台账缺失时照常出报告并列出缺口）
    2  存在台账 schema 严重错误（JSON 解析失败、必填字段缺失/类型错误）

渲染降级链：matplotlib PNG -> 纯标准库 SVG（--svg 可强制）。
"""
import argparse
import base64
import html
import json
import os
import sys

VERSION = "1.0"

LEDGERS = ["inventory", "targets", "runs", "comparison", "attributions", "result"]
ALLOWED_STATUS = {"success", "partial", "unable", "refused"}

GRADE_LABEL = {
    "reproducible": "reproducible（可复现：全部比较项在容差内）",
    "partially_reproducible": "partially_reproducible（部分可复现：存在超差项，但均有证据归因）",
    "not_reproducible": "not_reproducible（不可复现：存在无证据归因的超差项）",
    "unable": "unable（无法判定：无有效比较项）",
}


def fmt(v):
    """数字的确定性格式化：报告文本与审计共用同一规则。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    f = float(v)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return format(f, ".6g")


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---------------------------------------------------------------- 台账读取与校验

class SchemaError(Exception):
    pass


def _need(obj, key, typ, ctx):
    if key not in obj:
        raise SchemaError("%s 缺必填字段 %s" % (ctx, key))
    v = obj[key]
    if typ is not None and not isinstance(v, typ):
        raise SchemaError("%s 字段 %s 类型错误（期望 %s）" % (ctx, key, typ))
    return v


def validate(name, data):
    """字段级 schema 校验；严重错误抛 SchemaError（退出码 2）。"""
    if not isinstance(data, dict):
        raise SchemaError("%s.json 顶层必须是对象" % name)
    if name == "inventory":
        mats = _need(data, "materials", list, "inventory")
        for i, m in enumerate(mats):
            ctx = "inventory.materials[%d]" % i
            _need(m, "id", str, ctx)
            _need(m, "kind", str, ctx)
            st = _need(m, "status", str, ctx)
            if st not in ("present", "missing"):
                raise SchemaError("%s.status 只能是 present/missing" % ctx)
    elif name == "targets":
        mets = _need(data, "metrics", list, "targets")
        seen = set()
        for i, m in enumerate(mets):
            ctx = "targets.metrics[%d]" % i
            mid = _need(m, "id", str, ctx)
            if mid in seen:
                raise SchemaError("targets 指标 id 重复：%s" % mid)
            seen.add(mid)
            _need(m, "name", str, ctx)
            if not is_num(_need(m, "paper_value", None, ctx)):
                raise SchemaError("%s.paper_value 必须是数字" % ctx)
            _need(m, "unit", str, ctx)
            tol = _need(m, "tolerance", dict, ctx)
            if tol.get("type") not in ("abs", "rel") or not is_num(tol.get("value")):
                raise SchemaError("%s.tolerance 需为 {type: abs|rel, value: 数字}" % ctx)
            _need(m, "source_locator", str, ctx)
    elif name == "runs":
        runs = _need(data, "runs", list, "runs")
        for i, r in enumerate(runs):
            ctx = "runs.runs[%d]" % i
            _need(r, "run_id", str, ctx)
            _need(r, "method", str, ctx)
            _need(r, "metric_id", str, ctx)
            vals = _need(r, "values", list, ctx)
            if not vals or not all(is_num(x) for x in vals):
                raise SchemaError("%s.values 必须是非空数字数组" % ctx)
            _need(r, "status", str, ctx)
    elif name == "comparison":
        ents = _need(data, "entries", list, "comparison")
        for i, e in enumerate(ents):
            ctx = "comparison.entries[%d]" % i
            _need(e, "metric_id", str, ctx)
            _need(e, "method", str, ctx)
            for k in ("paper_value", "reproduced_value", "abs_diff", "rel_diff"):
                if not is_num(_need(e, k, None, ctx)):
                    raise SchemaError("%s.%s 必须是数字" % (ctx, k))
            _need(e, "within", bool, ctx)
    elif name == "attributions":
        atts = _need(data, "attributions", list, "attributions")
        for i, a in enumerate(atts):
            ctx = "attributions.attributions[%d]" % i
            _need(a, "metric_id", str, ctx)
            _need(a, "method", str, ctx)
            _need(a, "cause", str, ctx)
            _need(a, "evidence", str, ctx)
    elif name == "result":
        _need(data, "case_id", str, "result")
        st = _need(data, "status", str, "result")
        if st not in ALLOWED_STATUS:
            raise SchemaError("result.status 必须是 %s 之一" % "/".join(sorted(ALLOWED_STATUS)))
        oc = _need(data, "output_contract", dict, "result")
        if not oc:
            raise SchemaError("result.output_contract 不能为空（须含 output_contract 全部字段）")
        _need(data, "sources", list, "result")
        _need(data, "uncertainties", list, "result")
        _need(data, "changelog", list, "result")


def load_ledgers(d):
    """返回 (ledgers, gaps)。缺文件 -> gaps；schema 严重错误 -> SchemaError。"""
    ledgers, gaps = {}, []
    for name in LEDGERS:
        p = os.path.join(d, name + ".json")
        if not os.path.isfile(p):
            gaps.append("缺少台账文件 %s.json" % name)
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise SchemaError("%s.json 解析失败：%s" % (name, e))
        validate(name, data)
        ledgers[name] = data
    # 交叉引用：comparison 的 metric_id 必须能在 targets 找到
    if "comparison" in ledgers and "targets" in ledgers:
        known = {m["id"] for m in ledgers["targets"]["metrics"]}
        for i, e in enumerate(ledgers["comparison"]["entries"]):
            if e["metric_id"] not in known:
                raise SchemaError(
                    "comparison.entries[%d].metric_id=%s 在 targets.json 中不存在" % (i, e["metric_id"]))
    return ledgers, gaps


# ---------------------------------------------------------------- 机械判定（非科学判断）

def within_calc(entry, tol):
    """按 targets 容差机械重算 within。编译器不做科学判断，只做代数复核。"""
    diff = abs(float(entry["reproduced_value"]) - float(entry["paper_value"]))
    eps = 1e-12 * max(1.0, abs(float(tol["value"])))
    if tol["type"] == "abs":
        return diff <= float(tol["value"]) + eps
    pv = abs(float(entry["paper_value"]))
    return (diff / pv if pv else float("inf")) <= float(tol["value"]) + eps


def compute_grade(entries, attributions):
    """结论分级机械汇总规则（见 references/report_contract.md）。"""
    if not entries:
        return "unable"
    out = [e for e in entries if not e["_within_calc"]]
    if not out:
        return "reproducible"
    attr_keys = {(a["metric_id"], a["method"]) for a in attributions}
    if all((e["metric_id"], e["method"]) in attr_keys for e in out):
        return "partially_reproducible"
    return "not_reproducible"


# ---------------------------------------------------------------- 渲染：matplotlib PNG / 纯标准库 SVG

METHOD_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]


def render_figure(metric, entries, seed_points, out_base, use_mpl):
    """画一个指标的对比图：论文值点、各方法复现值（含逐种子散点）、容差带。
    返回实际写出的文件相对路径名。"""
    paper = float(metric["paper_value"])
    tol = metric["tolerance"]
    tol_abs = float(tol["value"]) if tol["type"] == "abs" else float(tol["value"]) * abs(paper)
    methods = sorted({e["method"] for e in entries})
    agg = {e["method"]: float(e["reproduced_value"]) for e in entries}
    if use_mpl:
        return _render_png(metric, paper, tol_abs, methods, agg, seed_points, out_base)
    return _render_svg(metric, paper, tol_abs, methods, agg, seed_points, out_base)


def _pick_cjk_font():
    """matplotlib PNG 路径下尽量找一个支持中文的字体；找不到返回 None（标签降级为 ASCII）。"""
    try:
        from matplotlib import font_manager
        have = {f.name for f in font_manager.fontManager.ttflist}
        for cand in ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
                     "Noto Sans SC", "SimHei", "Microsoft YaHei", "WenQuanYi Zen Hei",
                     "Arial Unicode MS"):
            if cand in have:
                return cand
    except Exception:
        pass
    return None


def _render_png(metric, paper, tol_abs, methods, agg, seed_points, out_base):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cjk = _pick_cjk_font()
    if cjk:
        matplotlib.rcParams["font.family"] = [cjk, "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
        label = "%s (%s)" % (metric["name"], metric["unit"])
    else:  # 无中文字体时标签降级为 ASCII，避免乱码方块
        label = "%s [%s]" % (metric["id"], metric["unit"])
    fig, ax = plt.subplots(figsize=(6.8, 3.8), dpi=110)
    xs = list(range(len(methods) + 1))
    ax.axhspan(paper - tol_abs, paper + tol_abs, color="#2ca02c", alpha=0.15, label="tolerance band")
    ax.axhline(paper, color="#2ca02c", lw=0.8, ls="--")
    ax.plot([0], [paper], marker="o", ms=9, color="black", label="paper value")
    for j, m in enumerate(methods):
        c = METHOD_COLORS[j % len(METHOD_COLORS)]
        for k, v in enumerate(seed_points.get(m, [])):
            ax.plot([j + 1 + (k - (len(seed_points[m]) - 1) / 2.0) * 0.08], [v],
                    marker=".", ms=6, color=c, alpha=0.6)
        ax.plot([j + 1], [agg[m]], marker="o", ms=9, color=c, label="reproduced: %s" % m)
    ax.set_xticks(xs)
    ax.set_xticklabels(["paper"] + methods)
    ax.set_ylabel(label)
    ax.set_title("comparison: %s" % metric["id"])
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()
    path = out_base + ".png"
    fig.savefig(path)
    plt.close(fig)
    return os.path.basename(path)


def _render_svg(metric, paper, tol_abs, methods, agg, seed_points, out_base):
    """纯标准库 SVG：坐标映射全部手写，不依赖任何第三方库。"""
    W, H = 680, 380
    ml, mr, mt, mb = 78, 18, 34, 62
    pw, ph = W - ml - mr, H - mt - mb
    vals = [paper - tol_abs, paper + tol_abs] + list(agg.values())
    for vs in seed_points.values():
        vals.extend(float(v) for v in vs)
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        hi, lo = hi + 1.0, lo - 1.0
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    def ymap(v):
        return mt + ph * (1.0 - (float(v) - lo) / (hi - lo))

    n = len(methods) + 1

    def xmap(i):
        return ml + pw * (i + 0.5) / n

    esc = html.escape
    parts = []
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
                 'viewBox="0 0 %d %d" font-family="Helvetica,Arial,sans-serif">' % (W, H, W, H))
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="white"/>' % (W, H))
    # 容差带
    ytop, ybot = ymap(paper + tol_abs), ymap(paper - tol_abs)
    parts.append('<rect x="%d" y="%.2f" width="%d" height="%.2f" fill="#2ca02c" fill-opacity="0.15"/>' %
                 (ml, ytop, pw, ybot - ytop))
    parts.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#2ca02c" stroke-width="1" '
                 'stroke-dasharray="5,4"/>' % (ml, ymap(paper), ml + pw, ymap(paper)))
    # 坐标轴与刻度
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (ml, mt, ml, mt + ph))
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (ml, mt + ph, ml + pw, mt + ph))
    for k in range(6):
        v = lo + (hi - lo) * k / 5.0
        y = ymap(v)
        parts.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#333"/>' % (ml - 5, y, ml, y))
        parts.append('<text x="%d" y="%.2f" font-size="11" text-anchor="end" fill="#333">%s</text>' %
                     (ml - 8, y + 4, esc(fmt(v))))
        parts.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#ddd"/>' % (ml, y, ml + pw, y))
    # 标题与轴标签
    parts.append('<text x="%d" y="20" font-size="14" text-anchor="middle" fill="#111">comparison: %s'
                 '（%s, 单位 %s）</text>' % (W // 2, esc(metric["id"]), esc(metric["name"]), esc(metric["unit"])))
    parts.append('<text x="%d" y="%d" font-size="11" text-anchor="middle" fill="#333">method</text>' %
                 (ml + pw // 2, H - 8))
    # 论文值点
    px, py = xmap(0), ymap(paper)
    parts.append('<circle cx="%.2f" cy="%.2f" r="7" fill="black"/>' % (px, py))
    parts.append('<text x="%.2f" y="%d" font-size="11" text-anchor="middle" fill="#333">paper</text>' %
                 (px, H - mb + 18))
    parts.append('<text x="%.2f" y="%.2f" font-size="10" text-anchor="middle" fill="black">%s</text>' %
                 (px, py - 11, esc(fmt(paper))))
    # 各方法：种子散点 + 聚合大点
    for j, m in enumerate(methods):
        c = METHOD_COLORS[j % len(METHOD_COLORS)]
        cx = xmap(j + 1)
        vs = seed_points.get(m, [])
        for k, v in enumerate(vs):
            off = (k - (len(vs) - 1) / 2.0) * 10.0
            parts.append('<circle cx="%.2f" cy="%.2f" r="3.5" fill="%s" fill-opacity="0.55"/>' %
                         (cx + off, ymap(v), c))
        parts.append('<circle cx="%.2f" cy="%.2f" r="7" fill="%s"/>' % (cx, ymap(agg[m]), c))
        parts.append('<text x="%.2f" y="%.2f" font-size="10" text-anchor="middle" fill="%s">%s</text>' %
                     (cx, ymap(agg[m]) - 11, c, esc(fmt(agg[m]))))
        parts.append('<text x="%.2f" y="%d" font-size="11" text-anchor="middle" fill="#333">%s</text>' %
                     (cx, H - mb + 18, esc(m)))
    # 图例
    ly = mt + 6
    parts.append('<rect x="%d" y="%d" width="12" height="12" fill="#2ca02c" fill-opacity="0.15"/>' % (ml + 6, ly - 9))
    parts.append('<text x="%d" y="%d" font-size="10" fill="#333">容差带 tolerance band</text>' % (ml + 22, ly))
    parts.append('<circle cx="%d" cy="%d" r="4" fill="black"/>' % (ml + 150, ly - 3))
    parts.append('<text x="%d" y="%d" font-size="10" fill="#333">论文值 paper value</text>' % (ml + 158, ly))
    parts.append('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (ml + 268, ly - 3, METHOD_COLORS[0]))
    parts.append('<text x="%d" y="%d" font-size="10" fill="#333">复现值 reproduced</text>' % (ml + 276, ly))
    parts.append('</svg>')
    path = out_base + ".svg"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return os.path.basename(path)


# ---------------------------------------------------------------- 编译主流程

def build(ledgers, gaps, out_dir, use_mpl):
    os.makedirs(out_dir, exist_ok=True)
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    partial = bool(gaps)
    entries_map = []   # report_map.json 的数字登记
    figures = []
    warnings = []

    def reg(location, value, pointer=None, derivation=None):
        entries_map.append({"location": location, "value": value,
                            **({"pointer": pointer} if pointer else {}),
                            **({"derivation": derivation} if derivation else {})})
        return fmt(value) if is_num(value) else str(value)

    inv = ledgers.get("inventory")
    tgt = ledgers.get("targets")
    runs = ledgers.get("runs")
    cmp_ = ledgers.get("comparison")
    att = ledgers.get("attributions")
    res = ledgers.get("result")

    tol_by_metric = {m["id"]: m["tolerance"] for m in tgt["metrics"]} if tgt else {}
    metric_by_id = {m["id"]: m for m in tgt["metrics"]} if tgt else {}
    cmp_entries = cmp_["entries"] if cmp_ else []
    att_list = att["attributions"] if att else []
    run_list = runs["runs"] if runs else []

    # 机械复核 within 标记
    for i, e in enumerate(cmp_entries):
        tol = tol_by_metric.get(e["metric_id"])
        e["_within_calc"] = within_calc(e, tol) if tol else bool(e["within"])
        if tol and e["_within_calc"] != e["within"]:
            warnings.append("comparison.entries[%d] 的 within 与按 targets 容差重算结果不一致，"
                            "报告采用重算值" % i)

    grade = compute_grade(cmp_entries, att_list) if cmp_ else "unable"
    n_all = len(cmp_entries)
    n_in = sum(1 for e in cmp_entries if e["_within_calc"])
    n_out = n_all - n_in
    attr_keys = {(a["metric_id"], a["method"]) for a in att_list}
    n_out_att = sum(1 for e in cmp_entries if not e["_within_calc"]
                    and (e["metric_id"], e["method"]) in attr_keys)

    # ---------------- report.md ----------------
    L = []
    case_id = res["case_id"] if res else "（result.json 缺失）"
    L.append("# 复现报告：%s" % case_id)
    L.append("")
    L.append("> 本报告由 report-compiler v%s 从机器可读台账自动编译生成，禁止手工修改；" % VERSION)
    L.append("> 报告中每个关键数字均可在 report_map.json 中追溯到台账 JSON 指针。")
    L.append("> 渲染器：%s。" % ("matplotlib PNG" if use_mpl else "纯标准库 SVG（无 matplotlib，已降级）"))
    if partial:
        L.append(">")
        L.append("> **PARTIAL 报告**：台账不完整，缺口如下（编译不中断，内容以现有台账为限）：")
        for g in gaps:
            L.append("> - %s" % g)
    L.append("")

    # 1 材料定位
    L.append("## 材料定位")
    L.append("")
    if inv:
        L.append("| 材料ID | 类型 | 状态 | 定位 | 备注 |")
        L.append("| --- | --- | --- | --- | --- |")
        for m in inv["materials"]:
            L.append("| %s | %s | %s | %s | %s |" % (
                m["id"], m["kind"], m["status"],
                m.get("locator") or "（无）", m.get("note", "")))
    else:
        L.append("（inventory.json 缺失，本节无法生成）")
    L.append("")

    # 2 环境与参数
    L.append("## 环境与参数")
    L.append("")
    if run_list:
        envs = sorted({r.get("env", "（未记录）") for r in run_list})
        L.append("运行环境：")
        for e_ in envs:
            L.append("- %s" % e_)
    else:
        L.append("运行环境：（runs.json 缺失或未记录）")
    L.append("")
    if tgt:
        L.append("| 指标ID | 指标名 | 论文值 | 单位 | 容差 | 来源定位 |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for i, m in enumerate(tgt["metrics"]):
            tol = m["tolerance"]
            L.append("| %s | %s | %s | %s | %s %s | %s |" % (
                m["id"], m["name"],
                reg("环境与参数/targets[%d]/paper_value" % i, m["paper_value"],
                    "targets.json#/metrics/%d/paper_value" % i),
                m["unit"], tol["type"],
                reg("环境与参数/targets[%d]/tolerance" % i, tol["value"],
                    "targets.json#/metrics/%d/tolerance/value" % i),
                m["source_locator"]))
    else:
        L.append("（targets.json 缺失，指标与容差未知）")
    L.append("")

    # 3 运行记录
    L.append("## 运行记录")
    L.append("")
    if run_list:
        L.append("| 运行ID | 方法 | 指标 | 种子 | 观测值 | 命令 | 状态 |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for i, r in enumerate(run_list):
            vals = " ".join(reg("运行记录/runs[%d]/values[%d]" % (i, k), v,
                                "runs.json#/runs/%d/values/%d" % (i, k))
                            for k, v in enumerate(r["values"]))
            L.append("| %s | %s | %s | %s | %s | `%s` | %s |" % (
                r["run_id"], r["method"], r["metric_id"],
                ",".join(fmt(s) for s in r.get("seeds", [])),
                vals, r.get("command", "（未记录）"), r["status"]))
    else:
        L.append("（runs.json 缺失，无运行记录）")
    L.append("")

    # 4 指标比较
    L.append("## 指标比较")
    L.append("")
    if cmp_:
        L.append("| 指标 | 方法 | 论文值 | 复现值 | 绝对差 | 相对差 | 容差 | 判定 |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for i, e in enumerate(cmp_entries):
            tol = tol_by_metric.get(e["metric_id"], {"type": "?", "value": 0})
            tol_s = "%s %s" % (tol["type"], fmt(tol["value"]))
            mark = "✓ 在容差内" if e["_within_calc"] else "✗ 超差"
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                e["metric_id"], e["method"],
                reg("指标比较/row%d/paper_value" % i, e["paper_value"],
                    "comparison.json#/entries/%d/paper_value" % i),
                reg("指标比较/row%d/reproduced_value" % i, e["reproduced_value"],
                    "comparison.json#/entries/%d/reproduced_value" % i),
                reg("指标比较/row%d/abs_diff" % i, e["abs_diff"],
                    "comparison.json#/entries/%d/abs_diff" % i),
                reg("指标比较/row%d/rel_diff" % i, e["rel_diff"],
                    "comparison.json#/entries/%d/rel_diff" % i),
                tol_s, mark))
        L.append("")
        # 对比图
        by_metric = {}
        for e in cmp_entries:
            by_metric.setdefault(e["metric_id"], []).append(e)
        seed_by = {}
        for r in run_list:
            seed_by.setdefault((r["metric_id"], r["method"]), []).extend(r["values"])
        L.append("对比图：")
        for mid in sorted(by_metric):
            metric = metric_by_id.get(mid)
            if not metric:
                continue
            sp = {e["method"]: seed_by.get((mid, e["method"]), []) for e in by_metric[mid]}
            base = os.path.join(fig_dir, "comparison_%s" % mid)
            fname = render_figure(metric, by_metric[mid], sp, base, use_mpl)
            rel = "figures/%s" % fname
            figures.append({"metric_id": mid, "path": rel})
            L.append("- %s：%s" % (mid, rel))
    else:
        L.append("（comparison.json 缺失，无法生成比较表与对比图）")
    L.append("")

    # 5 差异归因
    L.append("## 差异归因")
    L.append("")
    if att is not None:
        if att_list:
            for a in att_list:
                L.append("- **%s / %s**（置信度 %s）：%s" % (
                    a["metric_id"], a["method"], a.get("confidence", "未标注"), a["cause"]))
                L.append("  - 证据：%s" % a["evidence"])
        else:
            L.append("（无差异归因记录；若存在超差项则必须在 attributions.json 中登记）")
    else:
        L.append("（attributions.json 缺失）")
    L.append("")

    # 6 复现结论（只允许登记过的数字出现）
    L.append("## 复现结论")
    L.append("")
    s_all = reg("复现结论/n_entries", n_all, derivation="count:comparison.json#/entries")
    s_in = reg("复现结论/n_within", n_in, derivation="count_within:comparison.json#/entries")
    s_out = reg("复现结论/n_out", n_out, derivation="count_out:comparison.json#/entries")
    s_att = reg("复现结论/n_out_attributed", n_out_att,
                derivation="count_out_attributed:comparison.json#/entries")
    entries_map.append({"location": "复现结论/grade", "value": grade, "derivation": "grade"})
    L.append("按 comparison.json 机械汇总：共 %s 条比较，%s 条在容差内，%s 条超差"
             "（其中 %s 条已有证据归因）。结论分级：**%s**。" % (
                 s_all, s_in, s_out, s_att, GRADE_LABEL[grade]))
    if grade == "partially_reproducible":
        L.append("")
        L.append("注意：组织方合成代码 ≠ 作者原代码，合成数据上的达标不能表述为论文数值复现。")
    L.append("")

    # 7 不确定性
    L.append("## 不确定性")
    L.append("")
    if res:
        for u in res["uncertainties"]:
            L.append("- %s" % u)
        if not res["uncertainties"]:
            L.append("（未登记不确定性——通常这意味着登记不完整）")
    else:
        L.append("（result.json 缺失）")
    L.append("")

    # 8 缺失材料
    L.append("## 缺失材料")
    L.append("")
    missing = [m for m in inv["materials"] if m["status"] == "missing"] if inv else []
    if missing:
        for m in missing:
            L.append("- **%s**（%s）：%s" % (m["id"], m["kind"], m.get("note", "")))
    elif inv:
        L.append("（无缺失材料登记）")
    else:
        L.append("（inventory.json 缺失，无法确认材料完整性）")
    L.append("")

    # 9 变更记录
    L.append("## 变更记录")
    L.append("")
    if res:
        for c in res["changelog"]:
            L.append("- %s：%s" % (c.get("time", "（无时间）"), c.get("change", "")))
        if not res["changelog"]:
            L.append("（无变更记录）")
    else:
        L.append("（result.json 缺失）")
    L.append("")

    md = "\n".join(L)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)

    # ---------------- report.html（自包含） ----------------
    html_doc = _build_html(case_id, md, figures, out_dir, use_mpl, partial, gaps)
    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as f:
        f.write(html_doc)

    # ---------------- report_map.json ----------------
    rmap = {
        "generator": "report-compiler %s" % VERSION,
        "partial": partial,
        "gaps": gaps,
        "warnings": warnings,
        "renderer": "matplotlib-png" if use_mpl else "stdlib-svg",
        "entries": entries_map,
        "conclusion": {"grade": grade},
        "figures": figures,
        "number_whitelist": [],
    }
    with open(os.path.join(out_dir, "report_map.json"), "w", encoding="utf-8") as f:
        json.dump(rmap, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return rmap


def _build_html(case_id, md, figures, out_dir, use_mpl, partial, gaps):
    """自包含 HTML：内联 CSS；图以 base64 PNG 或内联 SVG 嵌入。"""
    esc = html.escape
    # 轻量 md -> html（只处理本编译器生成的结构：标题/引用/表格/列表/代码/普通段）
    body = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            body.append(_md_table(rows))
            continue
        if ln.startswith("# "):
            body.append("<h1>%s</h1>" % esc(ln[2:]))
        elif ln.startswith("## "):
            body.append("<h2>%s</h2>" % esc(ln[3:]))
        elif ln.startswith("> "):
            body.append('<p class="note">%s</p>' % _inline(ln[2:]))
        elif ln.startswith("- "):
            body.append("<ul>")
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  - ")):
                sub = lines[i].startswith("  - ")
                body.append('<li class="%s">%s</li>' % ("sub" if sub else "", _inline(lines[i].lstrip(" -"))))
                i += 1
            body.append("</ul>")
            continue
        elif ln.strip():
            body.append("<p>%s</p>" % _inline(ln))
        i += 1
    fig_html = []
    for fg in figures:
        p = os.path.join(out_dir, fg["path"])
        if not os.path.isfile(p):
            continue
        if p.endswith(".png"):
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            fig_html.append('<h3>%s</h3><img alt="%s" src="data:image/png;base64,%s"/>' %
                            (esc(fg["metric_id"]), esc(fg["metric_id"]), b64))
        else:
            with open(p, encoding="utf-8") as f:
                fig_html.append("<h3>%s</h3>%s" % (esc(fg["metric_id"]), f.read()))
    banner = ('<div class="partial">PARTIAL 报告：台账缺口 —— %s</div>' % esc("；".join(gaps))) if partial else ""
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>复现报告：%s</title>
<style>
body{font-family:-apple-system,"Helvetica Neue",Arial,"PingFang SC",sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#222;line-height:1.6}
h1{border-bottom:2px solid #444;padding-bottom:.2em}
h2{border-bottom:1px solid #ccc;margin-top:1.8em}
table{border-collapse:collapse;width:100%%;font-size:.92em}
th,td{border:1px solid #bbb;padding:.35em .6em;text-align:left}
th{background:#f0f0f0}
tr:nth-child(even){background:#fafafa}
.note{color:#555;background:#f7f7f7;border-left:3px solid #999;padding:.2em .8em;margin:.2em 0}
.partial{background:#fff3cd;border:1px solid #ffc107;padding:.8em;font-weight:bold}
code{background:#f0f0f0;padding:.1em .3em;border-radius:3px}
li.sub{margin-left:1.5em;list-style:circle}
img{max-width:100%%;border:1px solid #ddd}
</style></head><body>
%s
%s
<h2>对比图（内嵌）</h2>
%s
</body></html>
""" % (esc(case_id), banner, "\n".join(body), "\n".join(fig_html))


def _inline(s):
    s = html.escape(s)
    out, in_code, buf = [], False, ""
    for ch in s:
        if ch == "`":
            out.append(("<code>" if not in_code else "</code>"))
            in_code = not in_code
        else:
            out.append(ch)
    s = "".join(out)
    s = s.replace("**", "\x00")
    parts = s.split("\x00")
    res = []
    for k, p in enumerate(parts):
        res.append("<strong>%s</strong>" % p if k % 2 == 1 else p)
    return "".join(res)


def _md_table(rows):
    out = ["<table>"]
    for k, r in enumerate(rows):
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if k == 1 and all(set(c) <= set("-: ") for c in cells):
            continue
        tag = "th" if k == 0 else "td"
        out.append("<tr>%s</tr>" % "".join("<%s>%s</%s>" % (tag, _inline(c), tag) for c in cells))
    out.append("</table>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="台账驱动的复现报告编译器（report-compiler）")
    ap.add_argument("--ledgers", required=True, help="六个台账 JSON 所在目录")
    ap.add_argument("--out", required=True, help="编译产物输出目录")
    ap.add_argument("--svg", action="store_true", help="强制使用纯标准库 SVG 渲染（跳过 matplotlib）")
    args = ap.parse_args()

    try:
        ledgers, gaps = load_ledgers(args.ledgers)
    except SchemaError as e:
        print("SCHEMA ERROR：%s" % e, file=sys.stderr)
        return 2

    use_mpl = False
    if not args.svg:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot  # noqa: F401
            use_mpl = True
        except Exception:
            use_mpl = False
            print("提示：matplotlib 不可用，渲染降级为纯标准库 SVG。", file=sys.stderr)

    rmap = build(ledgers, gaps, args.out, use_mpl)
    print("编译完成：%s" % args.out)
    print("  渲染器：%s" % rmap["renderer"])
    print("  结论分级：%s" % rmap["conclusion"]["grade"])
    if rmap["partial"]:
        print("  PARTIAL：台账缺口 %d 项" % len(rmap["gaps"]))
        for g in rmap["gaps"]:
            print("    - %s" % g)
    for w in rmap["warnings"]:
        print("  警告：%s" % w)
    print("下一步：python3 audit_report.py --ledgers %s --report %s" % (args.ledgers, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
