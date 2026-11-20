#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Machine-readable domain & signaling-question specifications.

Mirrors the human-readable definitions in domains/*.md. Both
select_domains.py and collect_signals.py import this so the recall
keywords and the documented scales never drift apart.

Structure per domain:
  id            stable domain id
  name          human-readable name
  core          True if a 'present' here alone maps overall risk to high
  applies_to    list of doc types (rct/observational/diagnostic/
                systematic_review/other); 'all' means every type
  questions     list of signaling questions, each:
      id        stable question id
      text      the signaling question
      p_keywords  channel-P recall keywords (affirmative evidence hunt)
      n_keywords  channel-N recall keywords (omission/contradiction hunt)
      positive  what affirmative (bias-mitigating) evidence looks like
      negative  what evidence of the bias looks like
      insufficient_when  when to abstain with 'insufficient'
"""
import re

DOMAINS = [
    # ------------------------- common (all types) -------------------------
    {
        "id": "selective_reporting",
        "name": "结果选择性报告",
        "core": True,
        "applies_to": ["all"],
        "questions": [
            {
                "id": "sr_q1",
                "text": "是否存在预设结局/分析计划，且报告结局与之一致？",
                "p_keywords": ["primary outcome", "secondary outcome",
                               "pre-registered", "preregistered",
                               "registration", "protocol", "trial registration",
                               "NCT", "primary endpoint", "预设", "主要结局",
                               "注册"],
                "n_keywords": ["not reported", "post hoc", "post-hoc",
                               "exploratory", "changed outcome", "未报告",
                               "事后", "not pre-specified", "not prespecified"],
                "positive": "明确声明主要结局并有注册号/方案引用，报告结局与注册一致。",
                "negative": "结局定义在结果段才出现、注册结局未报告、标注 post hoc 更换结局。",
                "insufficient_when": "无注册信息且方法段未预设任何结局优先级。",
            },
            {
                "id": "sr_q2",
                "text": "是否所有测量结局均被完整报告（无选择性遗漏）？",
                "p_keywords": ["all outcomes", "complete data",
                               "as specified", "表", "Table", "所有结局"],
                "n_keywords": ["data not shown", "not shown",
                               "available on request", "selective",
                               "未列出", "数据未展示", "omitted"],
                "positive": "方法列出的每个结局在结果/表格中均有对应数据。",
                "negative": "'data not shown'、'available on request'、方法提及而结果缺失。",
                "insufficient_when": "方法段结局清单本身不完整，无法核对。",
            },
        ],
    },
    {
        "id": "statistical_methods",
        "name": "统计方法适用性",
        "core": False,
        "applies_to": ["all"],
        "questions": [
            {
                "id": "st_q1",
                "text": "统计方法是否与数据类型/研究设计匹配且有足够细节？",
                "p_keywords": ["statistical analysis", "regression",
                               "adjusted", "confidence interval", "p value",
                               "p-value", "sample size", "power", "ITT",
                               "intention-to-treat", "统计", "校正", "置信区间"],
                "n_keywords": ["inappropriate", "not adjusted", "unclear",
                               "no statistical", "multiple testing",
                               "多重比较", "未校正"],
                "positive": "方法段列出检验/模型、校正变量、显著性阈值与样本量依据。",
                "negative": "使用与设计不匹配的方法（如对非正态小样本用参数检验且不说明）、多重比较未校正。",
                "insufficient_when": "统计方法仅一句话带过，无法判断适用性。",
            },
        ],
    },
    {
        "id": "funding_coi",
        "name": "资助与利益冲突",
        "core": False,
        "applies_to": ["all"],
        "questions": [
            {
                "id": "fc_q1",
                "text": "资助来源与作者利益冲突是否披露，资助方是否介入研究？",
                "p_keywords": ["funding", "conflict of interest",
                               "competing interest", "disclosure",
                               "sponsored", "grant", "利益冲突", "资助",
                               "role of the funder"],
                "n_keywords": ["not disclosed", "no funding statement",
                               "employees of", "holds shares", "consultant for",
                               "未披露", "受雇于"],
                "positive": "有明确资助声明与 COI 声明，并说明资助方角色（或无角色）。",
                "negative": "资助方为利益相关厂商且参与设计/分析/写作，或作者为厂商雇员。",
                "insufficient_when": "全文无资助与 COI 声明（无法确认有无）。",
            },
        ],
    },
    # ------------------------------- RCT -------------------------------
    {
        "id": "randomization",
        "name": "随机化与分配隐藏（选择偏倚）",
        "core": True,
        "applies_to": ["rct"],
        "questions": [
            {
                "id": "ra_q1",
                "text": "随机序列生成方法是否恰当？",
                "p_keywords": ["random", "randomized", "randomised",
                               "computer-generated", "random number",
                               "block randomization", "stratified", "随机"],
                "n_keywords": ["quasi-random", "alternating", "by date of birth",
                               "by admission", "not randomized", "交替",
                               "按入院", "伪随机"],
                "positive": "计算机随机数/区组/分层随机等明文描述。",
                "negative": "按出生日期/入院顺序/交替分配等伪随机。",
                "insufficient_when": "仅写'randomized'而无任何方法细节。",
            },
            {
                "id": "ra_q2",
                "text": "分配隐藏是否充分？",
                "p_keywords": ["allocation concealment", "sealed envelope",
                               "central randomization", "opaque",
                               "分配隐藏", "中心随机", "密封信封"],
                "n_keywords": ["open-label allocation", "unsealed",
                               "not concealed", "transparent envelope",
                               "未隐藏"],
                "positive": "中心随机/不透明密封信封等明文描述。",
                "negative": "分配序列对入组者可见（开放名单、透明信封）。",
                "insufficient_when": "全文未提及分配隐藏。",
            },
        ],
    },
    {
        "id": "blinding",
        "name": "盲法实施（实施/测量偏倚）",
        "core": True,
        "applies_to": ["rct"],
        "questions": [
            {
                "id": "bl_q1",
                "text": "参与者与实施者是否盲法，结局测量者是否盲法？",
                "p_keywords": ["double-blind", "double blind", "masked",
                               "masking", "placebo-controlled", "blinded",
                               "assessor-blind", "双盲", "盲法"],
                "n_keywords": ["open-label", "open label", "unblinded",
                               "single-blind", "not blinded", "开放标签",
                               "未设盲"],
                "positive": "双盲/评估者盲并有安慰剂或等效措施描述。",
                "negative": "开放标签且结局为主观指标。",
                "insufficient_when": "未提及盲法，或仅标题写 blind 而正文无对应。",
            },
        ],
    },
    {
        "id": "attrition",
        "name": "失访与缺失数据（耗损偏倚）",
        "core": True,
        "applies_to": ["rct", "observational", "diagnostic"],
        "questions": [
            {
                "id": "at_q1",
                "text": "失访/退出是否报告、组间是否均衡、缺失数据如何处理？",
                "p_keywords": ["lost to follow-up", "dropout", "withdrew",
                               "missing data", "imputation", "ITT",
                               "intention-to-treat", "per-protocol",
                               "失访", "脱落", "缺失"],
                "n_keywords": ["excluded from analysis", "high attrition",
                               "differential dropout", "complete case only",
                               "未说明失访", "剔除"],
                "positive": "报告各组失访数与原因、采用 ITT 或合理插补。",
                "negative": "失访率高或组间不均衡且仅完整病例分析、未说明缺失机制。",
                "insufficient_when": "无法从文中确定分析集与入组数差异原因。",
            },
        ],
    },
    # --------------------------- observational ---------------------------
    {
        "id": "confounding",
        "name": "混杂控制",
        "core": True,
        "applies_to": ["observational"],
        "questions": [
            {
                "id": "cf_q1",
                "text": "是否识别并充分校正了关键混杂因素？",
                "p_keywords": ["adjusted for", "propensity", "matching",
                               "matched", "multivariable", "confounder",
                               "stratified analysis", "校正", "混杂",
                               "倾向评分", "匹配"],
                "n_keywords": ["unadjusted", "crude", "no adjustment",
                               "residual confounding", "未校正", "粗率"],
                "positive": "明确列出校正变量集或使用匹配/倾向评分，且说明选择依据。",
                "negative": "仅粗关联、关键混杂（年龄/适应证等）未纳入。",
                "insufficient_when": "无法从文中确定哪些变量被校正。",
            },
        ],
    },
    {
        "id": "selection_obs",
        "name": "研究对象选择（选择偏倚）",
        "core": True,
        "applies_to": ["observational", "diagnostic"],
        "questions": [
            {
                "id": "so_q1",
                "text": "研究对象的纳入方式是否避免与暴露/结局相关的选择性？",
                "p_keywords": ["consecutive", "population-based", "cohort",
                               "inclusion criteria", "exclusion criteria",
                               "enrolled", "recruited", "连续入组",
                               "纳入标准"],
                "n_keywords": ["convenience sample", "volunteers",
                               "self-selected", "referral", "non-response",
                               "方便样本", "自愿者", "无应答"],
                "positive": "连续入组/基于人群的抽样，纳入排除标准清晰。",
                "negative": "方便样本、自愿者、高无应答率且未比较应答/无应答者。",
                "insufficient_when": "入组流程未描述。",
            },
        ],
    },
    {
        "id": "measurement",
        "name": "暴露/结局测量（信息偏倚）",
        "core": True,
        "applies_to": ["observational"],
        "questions": [
            {
                "id": "me_q1",
                "text": "暴露与结局的测量是否客观、一致、避免回忆/访谈者偏倚？",
                "p_keywords": ["validated", "questionnaire", "medical records",
                               "registry", "blinded assessment", "objective",
                               "验证", "病历", "登记系统"],
                "n_keywords": ["self-reported", "recall", "interviewer",
                               "not validated", "主观报告", "回忆"],
                "positive": "使用验证过的工具/登记数据/盲法评估。",
                "negative": "结局依赖未验证的自报且测量者知悉暴露状态。",
                "insufficient_when": "测量方式未描述。",
            },
        ],
    },
    # ----------------------------- diagnostic -----------------------------
    {
        "id": "reference_standard",
        "name": "参考标准（金标准）",
        "core": True,
        "applies_to": ["diagnostic"],
        "questions": [
            {
                "id": "rs_q1",
                "text": "参考标准是否独立于待评价试验且对所有受试者一致执行？",
                "p_keywords": ["reference standard", "gold standard",
                               "histopathology", "verified by", "blinded",
                               "independent", "金标准", "病理"],
                "n_keywords": ["incorporated", "verification bias",
                               "partial verification", "not blinded",
                               "不同金标准"],
                "positive": "所有受试者接受同一独立参考标准，判读者盲于试验结果。",
                "negative": "仅阳性者接受金标准（部分验证偏倚）或试验结果并入参考标准。",
                "insufficient_when": "参考标准执行流程未描述。",
            },
        ],
    },
    {
        "id": "flow_timing",
        "name": "受试者流程与时间间隔",
        "core": False,
        "applies_to": ["diagnostic"],
        "questions": [
            {
                "id": "ft_q1",
                "text": "试验与参考标准的时间间隔、纳入分析的比例是否合理？",
                "p_keywords": ["within", "days between", "interval",
                               "included in the analysis", "flow diagram",
                               "时间间隔", "流程图"],
                "n_keywords": ["excluded", "indeterminate results excluded",
                               "not interpretable", "剔除不确定结果"],
                "positive": "报告时间间隔与全部受试者流程，含不确定结果。",
                "negative": "剔除不确定/不可解释结果，或间隔过长未说明。",
                "insufficient_when": "无受试者流程信息。",
            },
        ],
    },
    # -------------------------- systematic review --------------------------
    {
        "id": "search_strategy",
        "name": "检索与纳入过程",
        "core": True,
        "applies_to": ["systematic_review"],
        "questions": [
            {
                "id": "ss_q1",
                "text": "检索是否系统全面（多库、检索式、时间范围）、筛选是否双人独立？",
                "p_keywords": ["PubMed", "MEDLINE", "Embase", "Cochrane",
                               "search strategy", "two reviewers",
                               "independently screened", "PRISMA", "检索式",
                               "双人独立"],
                "n_keywords": ["single database", "one reviewer",
                               "not systematic", "convenience", "单库",
                               "单人筛选"],
                "positive": "≥2 个数据库、给出检索式与时间范围、双人独立筛选并记录分歧处理。",
                "negative": "单库检索或单人筛选且无敏感性说明。",
                "insufficient_when": "仅称'systematic review'但无检索细节。",
            },
        ],
    },
    {
        "id": "sr_quality_synthesis",
        "name": "纳入研究质量评价与综合方法",
        "core": True,
        "applies_to": ["systematic_review"],
        "questions": [
            {
                "id": "sq_q1",
                "text": "是否评价纳入研究的偏倚风险并在综合时加以考虑？",
                "p_keywords": ["risk of bias", "quality assessment",
                               "Newcastle-Ottawa", "QUADAS", "RoB",
                               "GRADE", "heterogeneity", "I2", "meta-analysis",
                               "质量评价", "异质性"],
                "n_keywords": ["no quality assessment", "pooled without",
                               "not assessed", "未评价质量"],
                "positive": "使用公认工具评价质量，做异质性检验或敏感性分析。",
                "negative": "未做任何质量评价即合并效应量。",
                "insufficient_when": "仅叙述性综合且未说明质量考量。",
            },
        ],
    },
]

# Type-detection signal words (ordered by specificity).
TYPE_SIGNALS = [
    ("systematic_review",
     ["systematic review", "meta-analysis", "meta analysis", "prisma",
      "pooled", "forest plot", "系统综述", "meta分析"]),
    ("rct",
     ["randomized controlled", "randomised controlled", "randomly assigned",
      "randomized trial", "placebo-controlled", "double-blind",
      "随机对照", "随机分组", "random allocation"]),
    ("diagnostic",
     ["sensitivity and specificity", "diagnostic accuracy",
      "receiver operating", "roc curve", "reference standard",
      "positive predictive value", "诊断准确性", "灵敏度", "特异度"]),
    ("observational",
     ["cohort study", "case-control", "case control", "cross-sectional",
      "observational", "retrospective", "prospective cohort",
      "队列", "病例对照", "横断面"]),
]

DOMAIN_MAP = {d["id"]: d for d in DOMAINS}


def domains_for_type(doc_type):
    """Return the domain spec list for a document type."""
    out = []
    for d in DOMAINS:
        ap = d["applies_to"]
        if "all" in ap or doc_type in ap:
            out.append(d)
    return out


def detect_type(text):
    """Heuristic document type detection.

    Returns (doc_type, hits, confident). Falls back to 'other'.
    """
    low = (text or "").lower()
    best, best_hits = "other", []
    for doc_type, signals in TYPE_SIGNALS:
        hits = [s for s in signals if s in low]
        if len(hits) > len(best_hits):
            best, best_hits = doc_type, hits
    confident = len(best_hits) >= 2
    return best, best_hits, confident


_WORD_RE = {}


def find_keyword_hits(text, keywords):
    """Return list of keywords found in text (case-insensitive)."""
    low = (text or "").lower()
    return [k for k in keywords if k.lower() in low]
