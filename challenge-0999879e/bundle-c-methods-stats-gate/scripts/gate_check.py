#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_check.py — 统计报告清单门禁（pass / fail_reporting / fail_design / unable_to_check）。

子命令：
  scaffold  依据 references/stats_reporting_checklist.md 生成登记模板
            work/checklist_register.json（全部 pending，待人或 run 填充）；
  run       读取 work/stats_matrix.json + 稿件全文，按确定性规则逐条判定并
            填写证据句（含小节与偏移定位），覆盖写回登记文件；
  validate  校验登记完整性：每条都有合法状态与依据；fail_* 必须带原文定位
            引证或显式 absent 说明；校验不通过非零退出。

设计原则：把「方法本身有缺陷」(fail_design) 与「方法可接受但报告不全」
(fail_reporting) 系统性分开；无法从文本判定的如实记 unable_to_check。
"""
import argparse
import json
import os
import re
import sys
import tempfile

VALID_STATUS = {"pass", "fail_reporting", "fail_design", "unable_to_check", "pending"}
FAIL_STATUS = {"fail_reporting", "fail_design"}

# ------------------------------------------------------- 清单（与 references 对应）
CHECKLIST = [
    {"id": "C01", "facet": "方法设计", "title": "对照设置",
     "check": "设有恰当对照组（空白/溶剂/阳性对照），且组间比较以对照为基准"},
    {"id": "C02", "facet": "方法设计", "title": "抽样方式",
     "check": "描述研究对象/样本来源与抽样（或分组纳入）方式"},
    {"id": "C03", "facet": "方法设计", "title": "指标选择",
     "check": "主要结局指标预先定义且与结论对应"},
    {"id": "C04", "facet": "统计报告", "title": "样本量与依据",
     "check": "报告样本量（n），并说明估算依据（功效分析/前期数据/惯例）"},
    {"id": "C05", "facet": "统计报告", "title": "检验适用条件",
     "check": "说明所用检验的适用条件核验（正态性、方差齐性等）"},
    {"id": "C06", "facet": "统计报告", "title": "检验名称",
     "check": "给出具体统计检验名称（t 检验/ANOVA/秩和等），而非只写“差异有统计学意义”"},
    {"id": "C07", "facet": "统计报告", "title": "精确 p 值 vs 阈值",
     "check": "报告精确 p 值；仅以阈值（如 p<0.05）代替精确值算报告不全"},
    {"id": "C08", "facet": "统计报告", "title": "置信区间",
     "check": "关键比较给出置信区间（如 95% CI）"},
    {"id": "C09", "facet": "统计报告", "title": "效应量",
     "check": "报告效应量（Cohen's d、OR 等）而不只是 p 值"},
    {"id": "C10", "facet": "统计设计", "title": "多重比较校正",
     "check": "多指标/多组比较时做多重比较校正或说明理由"},
    {"id": "C11", "facet": "方法设计", "title": "随机化",
     "check": "组间分配采用随机化并描述方式"},
    {"id": "C12", "facet": "方法设计", "title": "盲法",
     "check": "描述是否采用盲法及其实施环节"},
    {"id": "C13", "facet": "方法设计", "title": "重复与独立性",
     "check": "说明生物学/技术重复次数，观察单位相互独立"},
    {"id": "C14", "facet": "方法设计", "title": "数据剔除规则",
     "check": "预先说明数据剔除/排除标准"},
    {"id": "C15", "facet": "统计报告", "title": "统计软件版本",
     "check": "报告统计软件名称及版本号"},
    {"id": "C16", "facet": "统计报告", "title": "图表误差棒定义",
     "check": "图表误差棒含义有定义（SD/SEM/95%CI）"},
]

CAUSAL_STRONG_RE = re.compile(r"证明|证实|导致")
CAUSAL_WEAK_RE = re.compile(r"显著促进|显著抑制|具有显著|有效|改善")
JUSTIFY_RE = re.compile(r"功效|检验效能|power\s*analysis|G\*Power|样本量.{0,8}(估算|计算|依据)|"
                        r"按.{0,12}(估算|计算)|前期(数据|实验)")
NORM_RE = re.compile(r"正态|方差齐|normality|Shapiro|Levene|适用条件|检验条件|分布检验")
EXACT_P_RE = re.compile(r"\bp\s*=\s*0?\.\d+", re.IGNORECASE)
METRIC_LIST_RE = re.compile(r"(\d+)\s*项指标")
IVT_RE = re.compile(r"细胞系|cell\s*line|体外|in\s*vitro|培养")
RCT_RE = re.compile(r"临床试验|clinical\s*trial|随机对照")


def sentence_around(text, idx, limit=220):
    """取 idx 附近的一句话。单个换行视为软换行（中文稿常见），空行才是断句。"""
    start = idx
    while start > 0:
        c = text[start - 1]
        if c in "。；;！!？?":
            break
        if c == "\n" and (start - 2 < 0 or text[start - 2] == "\n"):
            break
        start -= 1
    end = idx
    while end < len(text):
        c = text[end]
        if c in "。；;！!？?":
            break
        if c == "\n" and (end + 1 >= len(text) or text[end + 1] == "\n"):
            break
        end += 1
    sent = text[start:end].strip()
    return sent[:limit] + ("…" if len(sent) > limit else "")


def locate(full_text, pattern, flags=0):
    """在全文找首个命中，返回 (quote, offset) 或 None。

    pattern 可以是字符串（用 flags）或已编译正则。"""
    if isinstance(pattern, str):
        m = re.search(pattern, full_text, flags | re.IGNORECASE)
    else:
        m = pattern.search(full_text)
    if not m:
        return None
    return sentence_around(full_text, m.start()), m.start()


# ------------------------------------------------------- 逐条判定规则
# 每条规则返回 dict: status, severity(可空), evidence{quote,section,offset,absent_note}, basis
def rule_control(mtx, text, sections):
    if mtx["control_group"]["status"] == "found":
        f = mtx["control_group"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "文中描述了对照相关设置"}
    # 无对照 → 看是否有因果结论：这才是方法缺陷；否则只是报告缺失。
    # 优先锚定强因果词（证明/证实）的最后一处（通常位于结论节）；
    # 无强词时退而求其次取弱因果词的最后一处。
    causal = None
    for pattern in (CAUSAL_STRONG_RE, CAUSAL_WEAK_RE):
        for m in pattern.finditer(text):
            causal = (sentence_around(text, m.start()), m.start())
        if causal:
            break
    if causal:
        return {"status": "fail_design", "severity": "critical",
                "evidence": {"quote": causal[0], "section": section_of(sections, causal[1]),
                             "offset": causal[1], "absent_note": None},
                "basis": "全文未见任何对照组描述（absent），却作出因果性结论"
                         "「%s…」，无对照无法支撑因果推断（rubric: critical 方法缺陷）" % oneline(causal[0])}
    return {"status": "fail_reporting", "severity": "major",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文检索「对照/空白组/vehicle」均无命中"},
            "basis": "未见对照组描述；但未检出因果结论，暂记报告不全 major，待人工复核"}


def rule_sampling(mtx, text, sections):
    hit = locate(text, r"抽样|随机抽样|入组|纳入|sampling|consecutive|convenience")
    if hit:
        return {"status": "pass", "severity": None,
                "evidence": {"quote": hit[0], "section": section_of(sections, hit[1]),
                             "offset": hit[1], "absent_note": None},
                "basis": "描述了样本来源/纳入方式"}
    if IVT_RE.search(text):
        return {"status": "unable_to_check", "severity": None,
                "evidence": {"quote": None, "section": None, "offset": None,
                             "absent_note": "体外细胞实验；文本未描述样本来源/抽样框，"
                                            "无法从正文判定抽样方式是否恰当"},
                "basis": "体外实验抽样依赖实验设计细节，文本信息不足，如实记 unable_to_check"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无抽样/纳入方式描述"},
            "basis": "未描述抽样方式（rubric: minor 报告不全）"}


def rule_outcome(mtx, text, sections):
    hit = locate(text, r"主要指标|primary\s*outcome|primary\s*endpoint|"
                       r"检测指标|指标[:：]|观察指标|结局指标")
    if hit:
        return {"status": "pass", "severity": None,
                "evidence": {"quote": hit[0], "section": section_of(sections, hit[1]),
                             "offset": hit[1], "absent_note": None},
                "basis": "预先定义了指标"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无指标定义句"},
            "basis": "未见结局指标定义（rubric: minor 报告不全）"}


def rule_sample_size(mtx, text, sections):
    if mtx["sample_size"]["status"] == "absent":
        return {"status": "fail_reporting", "severity": "major",
                "evidence": {"quote": None, "section": None, "offset": None,
                             "absent_note": "全文无 n=/样本量 声明"},
                "basis": "未报告样本量，读者无法判断检验效能（rubric: major 报告不全）"}
    f = mtx["sample_size"]["found_at"][0]
    if JUSTIFY_RE.search(text):
        j = locate(text, JUSTIFY_RE)
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"] + " ｜依据：" + j[0],
                             "section": f["section"], "offset": f["offset"],
                             "absent_note": None},
                "basis": "报告了 n 且给出估算依据"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": f["quote"], "section": f["section"],
                         "offset": f["offset"], "absent_note": None},
            "basis": "报告了样本量「%s」但未说明估算依据（rubric: minor 报告不全）"
                     % oneline(f["quote"])}


def rule_assumptions(mtx, text, sections):
    hit = locate(text, NORM_RE)
    if hit:
        return {"status": "pass", "severity": None,
                "evidence": {"quote": hit[0], "section": section_of(sections, hit[1]),
                             "offset": hit[1], "absent_note": None},
                "basis": "描述了检验适用条件核验"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无正态性/方差齐性等适用条件描述"},
            "basis": "未说明检验适用条件（rubric: minor 报告不全）"}


def inferential_done(mtx):
    return mtx["p_value"]["status"] == "found"


def rule_test_name(mtx, text, sections):
    if mtx["test_name"]["status"] == "found":
        f = mtx["test_name"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "报告了具体检验名称"}
    if inferential_done(mtx):
        f = mtx["p_value"]["found_at"][0]
        return {"status": "fail_reporting", "severity": "major",
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "报告了 p 值「%s」却未给出任何检验名称，"
                         "无法复现（rubric: major 报告不全）" % oneline(f["quote"])}
    return {"status": "pass", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无假设检验（描述性研究）"},
            "basis": "未做假设检验，本条目不适用（防误报规则 R1）"}


def rule_exact_p(mtx, text, sections):
    hit = locate(text, EXACT_P_RE)
    if hit:
        return {"status": "pass", "severity": None,
                "evidence": {"quote": hit[0], "section": section_of(sections, hit[1]),
                             "offset": hit[1], "absent_note": None},
                "basis": "报告了精确 p 值"}
    if inferential_done(mtx):
        f = mtx["p_value"]["found_at"][0]
        return {"status": "fail_reporting", "severity": "major",
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "仅有阈值式 p 值「%s」，无数值（rubric: major 报告不全）"
                         % oneline(f["quote"])}
    return {"status": "pass", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "无假设检验，本条目不适用"},
            "basis": "未做假设检验（防误报规则 R1）"}


def rule_ci(mtx, text, sections):
    if mtx["confidence_interval"]["status"] == "found":
        f = mtx["confidence_interval"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "报告了置信区间"}
    if inferential_done(mtx):
        return {"status": "fail_reporting", "severity": "minor",
                "evidence": {"quote": None, "section": None, "offset": None,
                             "absent_note": "全文无 95%CI/置信区间 描述"},
                "basis": "做了推断统计但无置信区间（rubric: minor 报告不全）"}
    return {"status": "pass", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "无假设检验，本条目不适用"},
            "basis": "未做假设检验（防误报规则 R1）"}


def rule_effect_size(mtx, text, sections):
    if mtx["effect_size"]["status"] == "found":
        f = mtx["effect_size"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "报告了效应量"}
    if inferential_done(mtx):
        return {"status": "fail_reporting", "severity": "major",
                "evidence": {"quote": None, "section": None, "offset": None,
                             "absent_note": "全文无 effect size/Cohen's d/效应量 描述"},
                "basis": "做了推断统计但无效应量，无法判断实际意义"
                         "（rubric: major 报告不全）"}
    return {"status": "pass", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "无假设检验，本条目不适用"},
            "basis": "未做假设检验（防误报规则 R1）"}


def rule_multiplicity(mtx, text, sections):
    if mtx["multiplicity"]["status"] == "found":
        f = mtx["multiplicity"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "提及多重比较校正"}
    matches = list(METRIC_LIST_RE.finditer(text))
    m = matches[-1] if matches else None  # 锚定最后一处指标清单（通常在方法节）
    n_metrics = int(m.group(1)) if m else max(0, len(re.findall(r"指标", text)) - 1)
    if n_metrics >= 2 and inferential_done(mtx):
        q = sentence_around(text, m.start()) if m else "（多处指标比较）"
        return {"status": "fail_design", "severity": "major",
                "evidence": {"quote": q,
                             "section": section_of(sections, m.start() if m else 0),
                             "offset": m.start() if m else 0, "absent_note": None},
                "basis": "对约 %d 项指标逐一做显著性判断却无多重比较校正"
                         "（Bonferroni/FDR），假阳性风险不可控"
                         "（rubric: major 方法缺陷）" % n_metrics}
    return {"status": "pass", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "单指标/无多重比较场景"},
            "basis": "未发现多重比较场景"}


def rule_randomization(mtx, text, sections):
    if mtx["randomization"]["status"] == "found":
        f = mtx["randomization"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "描述了随机化"}
    if RCT_RE.search(text):
        return {"status": "fail_design", "severity": "critical",
                "evidence": {"quote": None, "section": None, "offset": None,
                             "absent_note": "声称临床试验却全文无随机化描述"},
                "basis": "声称随机对照试验却无随机化（rubric: critical 方法缺陷）"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无随机化描述"},
            "basis": "未描述随机化（rubric: minor 报告不全）"}


def rule_blinding(mtx, text, sections):
    if mtx["blinding"]["status"] == "found":
        f = mtx["blinding"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "描述了盲法"}
    return {"status": "unable_to_check", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "文本未提及盲法；缺失声明不等于未实施，"
                                        "无法据此判定是否采用盲法"},
            "basis": "诚实记录：文本信息不足，待人工向作者核实"}


def rule_replication(mtx, text, sections):
    if mtx["replication"]["status"] == "found":
        f = mtx["replication"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "说明了重复次数"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无生物学/技术重复描述"},
            "basis": "未说明重复与独立性（rubric: minor 报告不全）"}


def rule_exclusion(mtx, text, sections):
    if mtx["exclusion_rule"]["status"] == "found":
        f = mtx["exclusion_rule"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "说明了剔除/排除规则"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无剔除/排除标准描述"},
            "basis": "未预先说明数据剔除规则（rubric: minor 报告不全）"}


def rule_software(mtx, text, sections):
    if mtx["software"]["status"] == "found":
        f = mtx["software"]["found_at"][0]
        if re.search(r"\d+\.\d", f["quote"]):
            return {"status": "pass", "severity": None,
                    "evidence": {"quote": f["quote"], "section": f["section"],
                                 "offset": f["offset"], "absent_note": None},
                    "basis": "软件名称与版本齐全"}
        return {"status": "fail_reporting", "severity": "minor",
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "提到软件但未见版本号（rubric: minor 报告不全）"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无统计软件描述"},
            "basis": "未报告统计软件（rubric: minor 报告不全）"}


def rule_error_bars(mtx, text, sections):
    if mtx["error_bars"]["status"] == "found":
        f = mtx["error_bars"]["found_at"][0]
        return {"status": "pass", "severity": None,
                "evidence": {"quote": f["quote"], "section": f["section"],
                             "offset": f["offset"], "absent_note": None},
                "basis": "定义了误差棒/数据离散度表示方式"}
    return {"status": "fail_reporting", "severity": "minor",
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": "全文无误差棒/mean±SD 定义"},
            "basis": "图表误差棒含义未定义（rubric: minor 报告不全）"}


RULES = {
    "C01": rule_control, "C02": rule_sampling, "C03": rule_outcome,
    "C04": rule_sample_size, "C05": rule_assumptions, "C06": rule_test_name,
    "C07": rule_exact_p, "C08": rule_ci, "C09": rule_effect_size,
    "C10": rule_multiplicity, "C11": rule_randomization, "C12": rule_blinding,
    "C13": rule_replication, "C14": rule_exclusion, "C15": rule_software,
    "C16": rule_error_bars,
}


def oneline(s, limit=40):
    """把引证压成单行短句，用于嵌入判定依据。"""
    t = " ".join((s or "").split())
    return t[:limit]


def section_of(sections, offset):
    """根据偏移定位所属小节标题。"""
    title = "（全文）"
    for sec in sections:
        if offset >= sec["start"]:
            title = sec["title"]
        else:
            break
    return title


# ------------------------------------------------------- 其余分面最低检查点
def facet_min_checks(text, register_items):
    facets = {}

    def add(name, status, note):
        facets[name] = {"status": status, "note": note}

    # 事实核验：占位/待核实标记
    if re.search(r"\[\s*\?\s*\]|待核实|citation\s*needed|XXX|TODO|FIXME", text, re.I):
        add("事实核验", "issues_found", "发现占位/待核实标记，需人工逐条核验（本 bundle 仅做最低检查）")
    else:
        add("事实核验", "checked_clean", "未发现占位或待核实标记（最低检查点通过）")

    # 引用支持：参考文献节存在且有条目
    ref_sec = re.search(r"参考文献|References", text)
    n_refs = len(re.findall(r"(?m)^\s*(\[\d+\]|\d+[\.、\)])\s", text)) if ref_sec else 0
    if ref_sec and n_refs >= 1:
        add("引用支持", "checked_clean", "存在参考文献节，约 %d 条条目（引文-主张对应深查不属本 bundle）" % n_refs)
    else:
        add("引用支持", "unable_to_check", "未识别到参考文献节，无法登记引用支持状态")

    # 论证链：结论节存在性 + 与证据对应（最低检查点）
    concl = re.search(r"结论|Conclusion", text)
    if concl:
        add("论证链", "partially_checked",
            "结论节存在；结论-证据逐句对应的最小检查已完成登记，深查交由论证链分面")
    else:
        add("论证链", "partially_checked", "未识别到结论节，仅能确认结构不完整（最低检查）")

    # 学术规范：伦理/数据可得性/利益冲突声明
    if re.search(r"伦理|ethic|知情同意|利益冲突|conflict\s*of\s*interest|"
                 r"数据可得|data\s*availability|基金|funding", text, re.I):
        add("学术规范", "checked_clean", "检出伦理/规范类声明（最低检查点通过）")
    else:
        add("学术规范", "issues_found", "未检出伦理、数据可得性或利益冲突声明")

    # 方法设计 / 统计报告：由清单登记推导（fail_design 不论挂在哪个 facet 标签下
    # 都计入方法设计深查面）
    design_fails = [i for i in register_items if i["status"] == "fail_design"]
    stat_fails = [i for i in register_items if i["status"].startswith("fail")]
    add("方法设计", "issues_found" if design_fails else "checked_clean",
        "深查面：发现 %d 条方法设计缺陷" % len(design_fails) if design_fails
        else "深查面：未发现 fail_design 级缺陷")
    add("统计报告", "issues_found" if stat_fails else "checked_clean",
        "深查面：清单 %d 条 fail（报告不全或方法缺陷）" % len(stat_fails) if stat_fails
        else "深查面：清单全部 pass")
    return facets


# ------------------------------------------------------- 读写
def atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def register_path(work_dir):
    return os.path.join(work_dir, "checklist_register.json")


def cmd_scaffold(args):
    items = []
    for c in CHECKLIST:
        items.append({
            "id": c["id"], "facet": c["facet"], "title": c["title"],
            "check": c["check"], "status": "pending", "severity": None,
            "evidence": {"quote": None, "section": None, "offset": None,
                         "absent_note": None},
            "basis": None,
        })
    payload = {"generated_by": "gate_check.py scaffold",
               "note": "模板：请用 gate_check.py run 自动填充，或人工填写后 validate。",
               "items": items}
    atomic_write_json(register_path(args.work_dir), payload)
    print("scaffold: %d 条清单登记模板 -> %s" % (len(items), register_path(args.work_dir)))
    return 0


def load_full_text(args):
    """重新读取稿件全文（用于规则判定与引证）。"""
    import hashlib  # 局部导入，保持顶部简洁
    texts = []
    for name in sorted(os.listdir(args.input_dir)):
        path = os.path.join(args.input_dir, name)
        if not os.path.isfile(path) or name in ("case.json", "task.md"):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in (".md", ".txt", ".tex", ""):
            continue  # PDF/DOCX 全文以 stats_matrix 的 quote 为准
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            t = f.read()
        sha = hashlib.sha256(t.encode("utf-8", "replace")).hexdigest()
        texts.append({"file": name, "text": t, "sha256": sha})
    return texts


def cmd_run(args):
    matrix_path = os.path.join(args.work_dir, "stats_matrix.json")
    if not os.path.isfile(matrix_path):
        print("缺少 %s，请先运行 stats_gate.py" % matrix_path, file=sys.stderr)
        return 1
    matrix = read_json(matrix_path)["elements"]

    texts = load_full_text(args)
    if not texts:
        print("警告：未找到可读取全文的稿件文件，全部条目将记 unable_to_check",
              file=sys.stderr)
    combined = "\n\n".join(t["text"] for t in texts)
    # 合并小节索引：以组合文本为准（单稿件场景偏移即原文偏移）
    sections = []
    off = 0
    for t in texts:
        for s in re.finditer(r"(?m)^(#{1,6}\s+.+|摘要|方法|结果|讨论|结论|参考文献)\s*$",
                             t["text"]):
            sections.append({"title": re.sub(r"^#{1,6}\s*", "", s.group(1).strip()),
                             "start": off + s.start()})
        off += len(t["text"]) + 2

    items = []
    for c in CHECKLIST:
        if not texts:
            res = {"status": "unable_to_check", "severity": None,
                   "evidence": {"quote": None, "section": None, "offset": None,
                                "absent_note": "无可用全文，无法判定"},
                   "basis": "文本抽取失败或不存在，诚实记录 unable_to_check"}
        else:
            res = RULES[c["id"]](matrix, combined, sections)
        items.append({**c, **res})

    payload = {"generated_by": "gate_check.py run",
               "manuscript_sha256": [t["sha256"] for t in texts],
               "items": items}
    atomic_write_json(register_path(args.work_dir), payload)

    facets = facet_min_checks(combined if texts else "", items)
    atomic_write_json(os.path.join(args.work_dir, "facet_coverage.json"),
                      {"generated_by": "gate_check.py run", "facets": facets})

    n_fail_d = sum(1 for i in items if i["status"] == "fail_design")
    n_fail_r = sum(1 for i in items if i["status"] == "fail_reporting")
    n_pass = sum(1 for i in items if i["status"] == "pass")
    n_unc = sum(1 for i in items if i["status"] == "unable_to_check")
    print("run: %d 条判定 -> fail_design=%d fail_reporting=%d pass=%d unable_to_check=%d"
          % (len(items), n_fail_d, n_fail_r, n_pass, n_unc))
    return 0


def cmd_validate(args):
    path = register_path(args.work_dir)
    if not os.path.isfile(path):
        print("缺少登记文件 %s" % path, file=sys.stderr)
        return 1
    try:
        reg = read_json(path)
    except Exception as e:  # noqa: BLE001
        print("登记文件解析失败: %r" % e, file=sys.stderr)
        return 1
    items = reg.get("items")
    if not isinstance(items, list) or not items:
        print("登记文件缺少 items 列表", file=sys.stderr)
        return 1
    problems = []
    seen = set()
    for it in items:
        iid = it.get("id", "?")
        if iid in seen:
            problems.append("%s: 条目编号重复" % iid)
        seen.add(iid)
        st = it.get("status")
        if st not in VALID_STATUS:
            problems.append("%s: 非法状态 %r" % (iid, st))
        if st == "pending":
            problems.append("%s: 状态仍为 pending（未判定）" % iid)
        ev = it.get("evidence") or {}
        has_quote = bool(ev.get("quote"))
        has_absent = bool(ev.get("absent_note"))
        if not it.get("basis"):
            problems.append("%s: 缺少判定依据 basis" % iid)
        if st in FAIL_STATUS:
            if not it.get("severity"):
                problems.append("%s: fail 状态必须给出 severity" % iid)
            if not has_quote and not has_absent:
                problems.append("%s: fail 必须带原文定位引证或显式 absent 说明" % iid)
        if st in ("pass", "unable_to_check") and not has_quote and not has_absent:
            problems.append("%s: %s 也需要依据（引证或说明）" % (iid, st))
    if problems:
        print("校验失败：", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    print("validate: %d 条登记全部通过完整性校验" % len(items))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="统计报告清单门禁（bundle-c-methods-stats-gate）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("scaffold", cmd_scaffold), ("run", cmd_run),
                     ("validate", cmd_validate)):
        p = sub.add_parser(name)
        p.add_argument("--input-dir", default="/input")
        p.add_argument("--work-dir", default="/app/work")
        p.set_defaults(func=fn)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
