#!/usr/bin/env python3
"""Recreate the explicitly SYNTHETIC positive and negative coverage inputs."""
from pathlib import Path
import copy
import json

ROOT = Path(__file__).resolve().parents[1]
POS = ROOT / "examples" / "positive"
NEG = ROOT / "examples" / "negative"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


facts = [
    ("direct_report", "研究共纳入 120 名合成受试者。", "120 名", "研究纳入 120 名受试者。"),
    ("direct_report", "原位组有 60 名合成受试者。", "原位组 60 名", "原位组样本量为 60。"),
    ("direct_report", "远程组有 60 名合成受试者。", "远程组 60 名", "远程组样本量为 60。"),
    ("direct_report", "主要结局为第 4 周合成症状评分。", "第 4 周症状评分", "主要结局时间点是第 4 周。"),
    ("computed", "按本演练双倍量表规则，原位组第 4 周评分输入为 12 分。", "12 × 2 = 24 分", "按预设双倍量表换算，原位组为 24 分。"),
    ("computed", "按本演练双倍量表规则，远程组第 4 周评分输入为 15 分。", "15 × 2 = 30 分", "按预设双倍量表换算，远程组为 30 分。"),
    ("computed", "第 2 周两次合成评分为 10 分与 14 分。", "(10 + 14) / 2 = 12 分", "两次评分均值为 12 分。"),
    ("computed", "合成评分为 18 分，满分为 30 分。", "18 / 30 × 100 = 60%", "该评分占满分的 60%。"),
    ("inferred", "提醒亚组完成 48 次随访，对照亚组完成 40 次。", "数字依从性可能更高", "提醒组的完成次数更多，提示依从性可能较高，但不能证明因果。"),
    ("inferred", "开放标签阶段未实施评分者盲法。", "存在测量偏倚风险", "缺少评分者盲法使测量偏倚成为可能，并非已证实发生偏倚。"),
    ("inferred", "筛选时排除 80 名潜力受试者。", "样本选择性可能较强", "排除人数较多提示选择性风险，外部推广应谨慎。"),
    ("inferred", "合成设备在 5 次传输中失败 1 次。", "数据完整性的技术风险有限但存在", "传输失败提示技术完整性风险，不能断言影响方向。"),
    ("direct_report", "合成随访窗口允许正负 3 天。", "正负 3 天", "允许的随访窗口是正负 3 天。"),
    ("direct_report", "试验共持续 4 周。", "4 周", "总试验时长为 4 周。"),
    ("direct_report", "来源列出头痛与疲劳两类不良事件。", "头痛与疲劳", "来源列出的不良事件类别为头痛和疲劳。"),
    ("direct_report", "主要分析遵循修改后意向治疗原则。", "modified intention-to-treat", "主要分析采用修改后意向治疗原则。"),
    ("computed", "第 1 周评分为 20 分，第 4 周评分为 14 分。", "20 - 14 = 6 分", "第 1 至 4 周评分下降 6 分。"),
    ("computed", "两组示例均值为 24 分与 30 分。", "(24 + 30) / 2 = 27 分", "两组的未加权均值为 27 分。"),
    ("inferred", "来源仅提供 20 名合成参与者用于估计参数。", "小样本使估计不精确", "仅 20 名参与者使不精确成为合理担忧，但未量化区间。"),
    ("inferred", "来源同时说明机制合理且无任何直接机制实验。", "机制仍是未验证解释", "机制只能视为解释性假设，因为没有直接机制实验。"),
]

questions = [
    ("Q1", "样本与主要结局是什么？", range(0, 4)),
    ("Q2", "指定数值经过换算或计算后是多少？", range(4, 8)),
    ("Q3", "从设计与观察可以作出哪些谨慎推断？", range(8, 12)),
    ("Q4", "随访、安全性与分析原则如何报告？", range(12, 16)),
    ("Q5", "进一步计算与解释是什么？", range(16, 20)),
    ("Q6", "药代动力学、生物标志物、生活质量和成本是多少？", range(20, 24)),
]

source_lines = [
    "# SYNTHETIC 最小来源：覆盖导航器演练",
    "",
    "> 本文及所有数字均为 SYNTHETIC 合成数据，不是正式论文、临床证据或官方结果。",
    "",
    "## 方法、结果与限制（最小合并文本）",
    "",
]
for index, (_, fact, _, _) in enumerate(facts, 1):
    source_lines.append(f"- F{index:02d}: {fact}")
source_lines.extend([
    "",
    "## 补充检索记录",
    "",
    "全文检索 pharmacokinetic、PK、biomarker、quality of life、QoL、cost 及中文同义词；检查上述方法、结果、表注和本补充区域。没有药代动力学、生物标志物、生活质量或成本数据。",
    "",
])
(ROOT / "examples" / "sources" / "study.md").write_text("\n".join(source_lines), encoding="utf-8")

task_text = """# SYNTHETIC 任务：不是正式结果

只依据 `examples/sources/study.md` 回答下列六个根问题及其 24 个子问题。所有数值都是合成数据，不得外推为真实临床结论。

- Q1 样本与主要结局：总样本、两组样本、主要结局。
- Q2 数值计算：四个量表换算、均值或百分比。
- Q3 谨慎推断：依从性、盲法、选择性、数据完整性。
- Q4 直接报告：随访窗口、试验时长、不良事件、分析原则。
- Q5 进一步计算与推断：两个计算、两个解释。
- Q6 未报告项目：药代动力学、生物标志物、生活质量、成本；必须记录检索范围。

```json
{
  "output_contract": {
    "mode": "EXACT",
    "fields": {
      "answers": {"type": "array"},
      "sources": {"type": "array"},
      "uncertainty": {"type": "array"},
      "change_records": {"type": "array"}
    }
  }
}
```

结果必须保留原 `case_id`，顶层只能有 `case_id` 和契约四字段。
"""
(POS / "input" / "task.md").write_text(task_text, encoding="utf-8")
(NEG / "input" / "task.md").write_text(task_text.replace("synthetic-case-001", "synthetic-negative-001"), encoding="utf-8")
save(POS / "input" / "case.json", {"case_id": "synthetic-case-001", "label": "SYNTHETIC — NOT AN OFFICIAL RESULT"})
save(NEG / "input" / "case.json", {"case_id": "synthetic-negative-001", "label": "SYNTHETIC failing fixture"})
(NEG / "input" / "environment" / "resources.yaml").write_text((POS / "input" / "environment" / "resources.yaml").read_text(encoding="utf-8"), encoding="utf-8")

claims = []
evidence = []
coverage_questions = []
result_answers = []
subserial = 0
for qid, qtext, indices in questions:
    children = []
    result_children = []
    parent_claims = []
    parent_evidence = []
    parent_mode = "unreported" if qid == "Q6" else facts[next(iter(indices))][0]
    for local_index, fact_index in enumerate(indices, 1):
        subserial += 1
        sid = f"{qid}.{local_index}"
        if qid == "Q6":
            topics = ["药代动力学", "生物标志物", "生活质量", "成本"]
            topic = topics[local_index - 1]
            child = {
                "subquestion_id": sid,
                "question": f"是否报告{topic}？",
                "answer": f"未报告{topic}数据；不能为零、阴性或无差异。",
                "answer_mode": "unreported",
                "status": "unreported",
                "confidence": 0.96,
                "progress_percent": 100,
                "claim_ids": [],
                "evidence_ids": [],
                "requirement": {"evidence_kinds": ["全文与补充材料披露检查"], "assertion_links": [f"TASK-{sid}"]},
                "unreported": {"searched_scope": [{"source_id": "SRC-SYN", "regions": ["方法、结果、表注、补充检索记录"], "actions": [f"检索{topic}及英文同义词，检查邻近段落"]}]},
            }
            answer_mode = "unreported"
        else:
            mode, fact, derivation_or_rationale, answer = facts[fact_index]
            cid = f"C{fact_index + 1:02d}"
            eid = f"E{fact_index + 1:02d}"
            support = {"direct_report": "direct", "computed": "computed", "inferred": "inferred"}[mode]
            claims.append({"claim_id": cid, "text": answer, "evidence_ids": [eid]})
            record = {"evidence_id": eid, "source_id": "SRC-SYN", "locator": f"study.md:F{fact_index + 1:02d}", "quote": fact, "support": support}
            if support == "computed":
                record["derivation"] = derivation_or_rationale
            if support == "inferred":
                record["rationale"] = "仅依据所列局部观察作谨慎推断；" + derivation_or_rationale
            evidence.append(record)
            child = {
                "subquestion_id": sid,
                "question": f"针对 F{fact_index + 1:02d}，答案是什么？",
                "answer": answer,
                "answer_mode": mode,
                "status": "answered",
                "confidence": 0.9 if mode == "inferred" else 0.99,
                "progress_percent": 100,
                "claim_ids": [cid],
                "evidence_ids": [eid],
                "requirement": {"evidence_kinds": [support + " supporting record"], "assertion_links": [f"TASK-{sid}"]},
            }
            parent_claims.append(cid)
            parent_evidence.append(eid)
            answer_mode = mode
        children.append(child)
        result_children.append({"subquestion_id": sid, "answer": child["answer"], "answer_mode": child["answer_mode"], "status": child["status"], "claim_ids": child["claim_ids"], "evidence_ids": child["evidence_ids"]})
    if qid == "Q6":
        parent_answer = "四类信息均未报告；详见每个子问题的 searched_scope。"
        parent_status = "unreported"
        parent_scope = {"unreported": {"searched_scope": [{"source_id": "SRC-SYN", "regions": ["全文及补充检索记录"], "actions": ["逐类同义词检索并检查图表和补充材料入口"]}]}}
    else:
        parent_answer = "；".join(child["answer"] for child in children)
        parent_status = "answered"
        parent_scope = {}
    parent = {
        "question_id": qid,
        "question": qtext,
        "answer": parent_answer,
        "answer_mode": parent_mode,
        "status": parent_status,
        "confidence": 0.9,
        "progress_percent": 100,
        "claim_ids": parent_claims,
        "evidence_ids": parent_evidence,
        "requirement": {"evidence_kinds": ["对应全部子问题的答案、断言与证据链"], "assertion_links": [f"TASK-{qid}"]},
        "subquestions": children,
        **parent_scope,
    }
    coverage_questions.append(parent)
    result_answers.append({"question_id": qid, "answer": parent_answer, "answer_mode": parent_mode, "status": parent_status, "claim_ids": parent_claims, "evidence_ids": parent_evidence, "subquestions": result_children})

sources = [{"source_id": "SRC-SYN", "title": "SYNTHETIC 最小来源：覆盖导航器演练", "path": "examples/sources/study.md", "uncertainty": "全部内容为合成演练，无真实临床外推效度；未知真实人群与正式结果。"}]
uncertainty = [{"scope": "entire-example", "statement": "SYNTHETIC：仅用于结构测试，不是正式或真实研究结论。"}, {"scope": "Q3/Q5 inferred rows", "statement": "推断只表达可能性，不证明因果或偏倚方向。"}, {"scope": "Q6", "statement": "未报告结论只覆盖所列最小来源，不证明其他来源也未报告。"}]
changes = [{"sequence": 1, "change": "初始建立 6 个根问题及 24 个子问题矩阵。", "reason": "先任务后阅读。"}, {"sequence": 2, "change": "将计算、推断与直接报告拆成独立行。", "reason": "避免回答模式混淆。"}]
coverage = {
    "label": "SYNTHETIC — NOT AN OFFICIAL RESULT",
    "questions": coverage_questions,
    "claims": claims,
    "evidence": evidence,
    "sources": sources,
    "uncertainty": uncertainty,
    "change_records": changes,
    "result_payload": {"answers": result_answers, "sources": sources, "uncertainty": uncertainty, "change_records": changes},
}
save(POS / "input" / "coverage.json", coverage)
negative = copy.deepcopy(coverage)
negative["label"] = "SYNTHETIC deliberate failure: missing answer and dangling IDs"
first = negative["questions"][0]["subquestions"][0]
first["answer"] = ""
first["claim_ids"] = ["C-DOES-NOT-EXIST"]
first["evidence_ids"] = ["E-DOES-NOT-EXIST"]
save(NEG / "input" / "coverage.json", negative)
print(f"Created {len(claims)} synthetic claims and {subserial} subquestions")
