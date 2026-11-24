#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_intake.py — 案例接收入口：实例化检查清单 + 立即落保底 partial result.json。

用法:
    python3 case_intake.py --case /input/case.json --task /input/task.md \
        --checklist-out /app/work/checklist.json --result-out /app/output/result.json

行为:
    1. 容错读取 case.json 与 task.md(缺文件/缺键均不崩溃,exit 0)。
    2. 从 task 文本识别声明的审查面(六大方向关键词);再按材料/任务内容启发式
       补充未声明的审查面(有参考文献表→引用面;人体/动物关键词→伦理面;
       第三方图表来源→版权面等)。
    3. 从内置标准检查项库(与 references/checklist_library.md 一致)为每个
       审查面实例化检查项,写出 checklist.json(每项状态=未开始)。
    4. 立即写出保底 result.json 骨架:status=partial、output_contract 要求的
       全部字段齐备、change_log 首条、uncertainty 说明"审查进行中"。
       若 result.json 已存在则默认不覆盖(--force 强制)。

仅使用 Python3 标准库;确定性输出(不含时间戳);单次运行 <5 秒。
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 审查面定义
FACETS = {
    "citation": "引用规范",
    "ethics": "伦理审查",
    "privacy": "隐私合规",
    "copyright": "版权合规",
    "integrity": "学术诚信",
    "submission": "投稿要求",
}

# 声明面识别关键词(命中任一即视为该面被 task 声明)
FACET_KEYWORDS = {
    "citation": ["引用规范", "引用", "参考文献", "引证", "citation", "reference", "文献著录"],
    "ethics": ["伦理审查", "伦理", "知情同意", "ethic", "irb", "受试者保护"],
    "privacy": ["隐私合规", "隐私", "个人信息", "脱敏", "pii", "privacy", "受限数据"],
    "copyright": ["版权", "许可", "授权", "copyright", "license", "第三方素材", "转载"],
    "integrity": ["学术诚信", "诚信", "图像复用", "重复发表", "署名", "利益冲突",
                  "integrity", "plagiarism", "抄袭", "一稿多投"],
    "submission": ["投稿要求", "期刊指南", "期刊要求", "投稿格式", "格式规范",
                   "submission", "guideline", "字数限制"],
}

# 启发式补充规则: (正则, facet, 理由)
HEURISTIC_RULES = [
    (r"参考文献|references|\[\d+\]\s*\S", "citation",
     "材料含参考文献表/顺序编码引文,补充引用规范面"),
    (r"人体|受试者|问卷|志愿者|患者|动物实验|小鼠|大鼠|participant|subject|mouse|mice|rat",
     "ethics", "材料含人体/动物研究关键词,补充伦理审查面"),
    (r"转载自|adapted from|reproduced from|第三方|图.*来源| reproduced|授权使用",
     "copyright", "材料含第三方图表/素材来源表述,补充版权合规面"),
    (r"1[3-9]\d{9}|身份证|住院号|病历号|phone|tel[:：]",
     "privacy", "材料疑似含手机号/证件号等 PII,补充隐私合规面"),
]

# ------------------------------------------------- 标准检查项库(与 references/checklist_library.md 一致)
CHECKLIST_LIBRARY = {
    "citation": [
        ("CIT-01", "每条参考文献是否真实存在(作者/题名/刊物可核对,无编造嫌疑)?"),
        ("CIT-02", "参考文献元数据是否完整一致(作者、题名、刊名、年、卷期、页码无缺失)?"),
        ("CIT-03", "正文引证标注与文末文献表是否一一对应(无孤儿条目、无悬空引用)?"),
        ("CIT-04", "引用体例是否全文统一(顺序编码制/著者-出版年制不混用)?"),
        ("CIT-05", "引文是否支撑其所在论断(无张冠李戴、无引用无关文献)?"),
        ("CIT-06", "是否混入未公开发表且不可获取的来源(私聊、内部报告未注明)?"),
        ("CIT-07", "自引比例是否异常,是否存在堆砌无关自引?"),
        ("CIT-08", "文献年代分布是否合理,关键近 5 年进展是否被遗漏?"),
    ],
    "ethics": [
        ("ETH-01", "涉及人体研究是否有伦理委员会批准声明及批件编号?"),
        ("ETH-02", "是否声明取得受试者知情同意(书面/口头,范围是否覆盖本研究用途)?"),
        ("ETH-03", "伦理批件适用范围是否覆盖论文实际报告的研究内容?"),
        ("ETH-04", "动物实验是否有动物伦理审批与 3R 原则说明?"),
        ("ETH-05", "是否报告受试者退出机制、风险与补偿安排?"),
        ("ETH-06", "临床研究是否注册(如 ChiCTR/ClinicalTrials.gov)并给出注册号?"),
    ],
    "privacy": [
        ("PRV-01", "正文/图表/附录是否含直接 PII(姓名、手机号、身份证、病历号等)?"),
        ("PRV-02", "是否含可重识别的间接标识组合(罕见病+地区+年龄等)?"),
        ("PRV-03", "受限数据(医疗、基因、地理轨迹)使用是否在授权范围内?"),
        ("PRV-04", "脱敏处理是否充分且说明方法(遮蔽/泛化/扰动)?"),
        ("PRV-05", "数据共享声明是否不泄露原始个体数据?"),
        ("PRV-06", "补充材料/代码仓库是否夹带未脱敏数据?"),
    ],
    "copyright": [
        ("COP-01", "第三方图表是否标注来源并取得许可/属合理使用?"),
        ("COP-02", "复用他人代码是否保留许可证与署名(LICENSE 兼容)?"),
        ("COP-03", "使用的数据集是否有许可证明且在授权范围内再分发?"),
        ("COP-04", "是否有整段文字来自其他作品而未标注引用(版权风险)?"),
        ("COP-05", "作者自有前作材料的复用是否符合出版社版权转让条款?"),
        ("COP-06", "图片中的商标、地图、受保护素材是否有使用依据?"),
    ],
    "integrity": [
        ("INT-01", "图像是否存在复用/拼接/局部篡改迹象(同一图重复标注不同条件)?"),
        ("INT-02", "是否存在重复发表/一稿多投迹象(与作者前作高度重叠)?"),
        ("INT-03", "署名是否完整且贡献声明与实际相符(无荣誉作者/遗漏作者)?"),
        ("INT-04", "是否声明利益冲突且与作者单位/资助方一致?"),
        ("INT-05", "基金资助信息是否与致谢、作者单位表述一致?"),
        ("INT-06", "数据/代码可用性声明是否真实可验证(链接有效、非空话)?"),
        ("INT-07", "是否存在捏造/篡改数据迹象(统计量内部矛盾、过于完美的分布)?"),
        ("INT-08", "AI 辅助写作/工具使用是否按期刊要求声明?"),
    ],
    "submission": [
        ("SUB-01", "稿件结构是否符合目标期刊指南(摘要、关键词、章节要求)?"),
        ("SUB-02", "字数/图表数量/参考文献数量是否在指南限额内?"),
        ("SUB-03", "图表分辨率、格式、编号是否满足投稿要求?"),
        ("SUB-04", "必需声明(伦理、利益冲突、数据可用性、作者贡献)是否齐全?"),
        ("SUB-05", "投稿信、亮点(highlights)、图文摘要等附加材料是否齐备?"),
        ("SUB-06", "语言、缩写、单位与术语是否符合期刊风格(体例统一)?"),
    ],
}

DEFAULT_REQUIRED_FIELDS = [
    "case_id", "status", "findings", "not_reviewed",
    "summary", "sources", "uncertainty", "change_log",
]


def read_text(path):
    """容错读文本:失败返回空串。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def read_json(path):
    """容错读 JSON:失败返回 {} 并在调用处说明。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def detect_declared_facets(task_text):
    declared = []
    for facet, keywords in FACET_KEYWORDS.items():
        low = task_text.lower()
        if any(k.lower() in low for k in keywords):
            declared.append(facet)
    return declared


def infer_facets(corpus, already):
    """按材料内容启发式补充审查面。返回 [(facet, reason), ...]"""
    inferred = []
    for pattern, facet, reason in HEURISTIC_RULES:
        if facet not in already and re.search(pattern, corpus, re.IGNORECASE):
            inferred.append((facet, reason))
            already.add(facet)
    return inferred


def build_checklist(facets):
    items = []
    for facet in facets:
        for check_id, question in CHECKLIST_LIBRARY.get(facet, []):
            items.append({
                "check_id": check_id,
                "facet": facet,
                "facet_label": FACETS.get(facet, facet),
                "question": question,
                "status": "未开始",
            })
    return items


def skeleton_result(case_id, required_fields, facets, notes):
    """保底 partial result.json:contract 字段一个不少。"""
    result = {
        "case_id": case_id,
        "status": "partial",
        "findings": [],
        "not_reviewed": [
            {"facet": f, "facet_label": FACETS.get(f, f),
             "reason": "审查进行中:该面检查项尚未执行"}
            for f in facets
        ],
        "summary": {
            "findings_count": 0,
            "facets_total": len(facets),
            "facets_covered": 0,
            "coverage_pct": 0.0,
            "severity_counts": {"critical": 0, "major": 0, "minor": 0, "info": 0},
            "stage": "intake",
        },
        "sources": [],
        "uncertainty": "审查进行中:本文件为开工 60 秒内生成的保底 partial 结果,"
                       "不代表最终结论;任何中断时以此文件为诚实部分结果。",
        "change_log": [
            {"seq": 1, "action": "intake",
             "detail": "case_intake.py 生成保底 partial result.json 骨架;"
                       "全部 contract 字段以占位值就位"}
        ],
        "_header": "合成/运行期保底输出,非正式测评结果",
    }
    # 保证 contract 要求的字段全部存在(未知字段以空值占位)
    for field in required_fields:
        if field not in result:
            result[field] = [] if field.endswith("s") else ""
    if notes:
        result["intake_notes"] = notes
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="案例接收:实例化检查清单并立即落保底 partial result.json")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/input/task.md", help="task.md 路径(可不存在)")
    ap.add_argument("--materials", nargs="*", default=[],
                    help="可选:材料文本路径,用于启发式补充审查面")
    ap.add_argument("--checklist-out", default="/app/work/checklist.json",
                    help="checklist.json 输出路径")
    ap.add_argument("--result-out", default="/app/output/result.json",
                    help="保底 result.json 输出路径")
    ap.add_argument("--force", action="store_true",
                    help="result.json 已存在时仍覆盖(默认不覆盖)")
    args = ap.parse_args(argv)

    notes = []
    case = read_json(args.case)
    if not case:
        notes.append("case.json 缺失或无法解析,按空案例处理")
    case_id = str(case.get("case_id") or "unknown-case")

    task_text = str(case.get("task") or "")
    md = read_text(args.task)
    if md:
        task_text = task_text + "\n" + md
    elif args.task:
        notes.append("task.md 缺失或为空,仅以 case.json 的 task 字段识别审查面")

    contract = case.get("output_contract")
    required = DEFAULT_REQUIRED_FIELDS
    if isinstance(contract, dict) and isinstance(contract.get("required_fields"), list):
        required = [str(x) for x in contract["required_fields"]]
    else:
        notes.append("output_contract.required_fields 缺失,使用默认字段集")

    declared = detect_declared_facets(task_text)
    corpus_parts = [task_text]
    for m in args.materials:
        t = read_text(m)
        if t:
            corpus_parts.append(t)
        else:
            notes.append("材料不可读: %s" % m)
    corpus = "\n".join(corpus_parts)
    inferred = infer_facets(corpus, set(declared))
    facets = list(declared) + [f for f, _ in inferred]
    if not facets:
        notes.append("未识别到任何审查面,checklist 为空;请人工确认 case 任务描述")

    checklist = {
        "_header": "合成/运行期检查清单输出,非正式测评结果",
        "case_id": case_id,
        "facet_labels": {f: FACETS.get(f, f) for f in facets},
        "declared_facets": declared,
        "inferred_facets": [{"facet": f, "reason": r} for f, r in inferred],
        "required_fields": required,
        "items": build_checklist(facets),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.checklist_out)), exist_ok=True)
    with open(args.checklist_out, "w", encoding="utf-8") as f:
        json.dump(checklist, f, ensure_ascii=False, indent=2)

    result_path = args.result_out
    if os.path.exists(result_path) and not args.force:
        notes.append("result.json 已存在,未覆盖(--force 可强制);保底文件沿用现有版本")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(result_path)), exist_ok=True)
        result = skeleton_result(case_id, required, facets, notes)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "ok": True,
        "case_id": case_id,
        "declared_facets": declared,
        "inferred_facets": [f for f, _ in inferred],
        "checklist_items": len(checklist["items"]),
        "checklist_out": args.checklist_out,
        "result_out": result_path,
        "notes": notes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
