#!/usr/bin/env python3
"""make_example.py — 合成示例（SYNTHETIC EXAMPLE，非正式案例结果）。

端到端演示 bounded-topic-appraiser：
  1. 在 <根目录>/case/ 生成合成语料：5 篇虚构短文（D1/D2 为结论相反的成人 RCT、
     D3 仅摘要的体外细胞系研究、D4 老年人单臂试验、D5 儿童队列研究）。
     facet 分布被设计为：至少一个 absent facet（孕妇 等）、一个 single_source
     theme（体外机制仅 D3）、一对方向冲突论断（D1 positive vs D2 negative）。
     case.json 提供 3 个候选选题与 2 条约束（仅限体内研究；样本量≥50）。
  2. 真实运行 run_case.py init（防御式解析 + case_extras 探测 + facet 打标）。
  3. 写入"模拟模型输出"（themes.json / claims.jsonl / topics.md，全部标注 simulated）。
  4. 真实运行 gaps（空白登记）、appraise（选题评分 + 决策备忘录）、finalize
     （组装 result.json），并打印三个选题的得分梯度。

用法：python3 make_example.py <工作根目录>
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

FILLER = "This synthetic sentence provides additional context for the simulated study. "

P1_BODY = """Probiotic Supplementation for Irritable Bowel Syndrome: A Randomized Controlled Trial in Adults
K. Aoyama and M. Reyes
2021

Abstract
This synthetic study tests whether a multi-strain probiotic improves symptoms in adults
(成人) with irritable bowel syndrome (IBS).

Methods
We conducted a double-blind randomized controlled trial (随机对照试验, RCT) in adults
with IBS. The sample size (样本量) was n = 120 participants. This in vivo (体内) study
recruited patients (患者) from two outpatient clinics.

Results
The probiotic group showed significantly greater symptom relief (症状缓解) than placebo,
with a p-value below 0.05.

Discussion
The improvement was consistent across subgroups of adult patients.

Conclusion
Probiotic supplementation improved IBS symptoms in this adult randomized trial.
""" + FILLER * 55

P2_BODY = """Probiotics Show No Benefit over Placebo in Adult IBS: A Randomized Trial
H. Lindqvist, T. Osei and R. Fabbri
2020

Abstract
This synthetic study re-examines whether probiotics relieve IBS symptoms in adults (成人).

Methods
We ran a randomized controlled trial (随机对照试验, RCT) of a multi-strain probiotic in
adult patients (患者) with IBS. The sample size (样本量) was n = 80 participants.
This in vivo (体内) trial followed participants for eight weeks.

Results
Symptom relief (症状缓解) did not differ between the probiotic and placebo arms,
with a p-value of 0.34.

Discussion
The null result contrasts with earlier positive reports and may reflect differences
in strain composition and baseline severity.

Conclusion
In this adult randomized trial, probiotics did not improve IBS symptoms.
""" + FILLER * 55

P3_ABSTRACT = """In Vitro Anti-Inflammatory Screening of Probiotic Strains: A Synthetic Abstract
S. Duarte
2022

Abstract
This synthetic abstract reports an in vitro (体外) screen of probiotic strains in a human
epithelial cell line (细胞系). Two strains reduced inflammation (炎症) biomarker levels in
cell culture. Full text was not provided for this synthetic record.
"""

P4_BODY = """Single-Arm Dietary Intervention in Elderly Patients with IBS: A Synthetic Pilot
E. Nakamura and G. Petrov
2019

Abstract
This synthetic pilot study evaluates a dietary intervention in elderly patients
(老年患者) with IBS.

Methods
We conducted a single-arm (单臂) dietary intervention in elderly patients (患者).
The sample size (样本量) was n = 60 participants, with a follow-up (随访) of 12 weeks.
This in vivo (体内) pilot had no control arm.

Results
Quality of life (生活质量) scores improved modestly over the follow-up period.

Discussion
Without a control group, the improvement cannot be attributed to the intervention.

Conclusion
Controlled studies in elderly patients are needed.
""" + FILLER * 55

P5_BODY = """Dietary Patterns and Adverse Events in Children with Functional Gut Disorders: A Cohort Study
L. Moreau and A. Haddad
2018

Abstract
This synthetic cohort study follows children (儿童) with functional gut disorders.

Methods
We assembled a cohort (队列) of children aged 6 to 12 years and recorded dietary patterns
over a follow-up (随访) of 18 months.

Results
Adverse events (不良事件), mostly mild gastrointestinal complaints, were reported in a
minority of children and were not associated with any specific dietary pattern.

Discussion
The observational design limits causal interpretation.

Conclusion
Dietary patterns were not linked to adverse events in this child cohort.
""" + FILLER * 55

TOPIC_STRONG = "孕妇群体中益生菌干预的体内随机对照试验研究"
TOPIC_COND = "成人益生菌随机对照试验对IBS症状缓解的效果综合"
TOPIC_WEAK = "细胞系水平上益生菌菌株的体外抗炎机制研究"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_case(root):
    cdir = os.path.join(root, "case")
    write(os.path.join(cdir, "paper1.txt"), P1_BODY)
    write(os.path.join(cdir, "paper2.txt"), P2_BODY)
    write(os.path.join(cdir, "paper3.txt"), P3_ABSTRACT)
    write(os.path.join(cdir, "paper4.txt"), P4_BODY)
    write(os.path.join(cdir, "paper5.txt"), P5_BODY)
    case = {
        "case_id": "SYN-E-001",
        "research_question": "益生菌与饮食干预对肠易激综合征（IBS）的效果与下一步选题（合成问题）",
        "documents": [
            {"path": "paper1.txt", "title": "Probiotic Supplementation for IBS: RCT in Adults", "year": 2021},
            {"path": "paper2.txt", "title": "Probiotics Show No Benefit over Placebo in Adult IBS", "year": 2020},
            {"path": "paper3.txt", "title": "In Vitro Anti-Inflammatory Screening of Probiotic Strains"},
            {"path": "paper4.txt", "title": "Single-Arm Dietary Intervention in Elderly Patients with IBS"},
            {"path": "paper5.txt", "title": "Dietary Patterns and Adverse Events in Children"},
        ],
        "candidate_topics": [TOPIC_STRONG, TOPIC_COND, TOPIC_WEAK],
        "constraints": ["仅限体内研究（in vivo）", "样本量≥50"],
        "output_contract": ["case_id", "status", "research_product", "appraisal_matrix",
                            "gap_register", "uncertainties", "sources", "change_log"],
    }
    write(os.path.join(cdir, "case.json"), json.dumps(case, ensure_ascii=False, indent=2))
    write(os.path.join(cdir, "task.md"),
          "# 合成任务（simulated）\n围绕研究问题归纳主题与论断，登记证据空白，"
          "并对候选选题做出有约束的评估决策。\n")
    return cdir


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def simulate_model_outputs(root):
    """写入模拟模型阶段产物（simulated model outputs，非真实模型生成）。"""
    work = os.path.join(root, "work")
    themes = [
        {"theme": "T1", "label": "成人益生菌随机对照试验的症状结局", "docs": ["D1", "D2"],
         "simulated": True},
        {"theme": "T2", "label": "体外菌株抗炎机制", "docs": ["D3"], "simulated": True},
        {"theme": "T3", "label": "非随机饮食干预的耐受性与生活质量", "docs": ["D4", "D5"],
         "simulated": True},
    ]
    write(os.path.join(work, "themes.json"), json.dumps(themes, ensure_ascii=False, indent=2))
    claims = [
        {"claim_id": "C1", "doc_id": "D1", "topic": "益生菌干预改善成人IBS症状",
         "direction": "positive",
         "statement": "成人 RCT（n=120）中益生菌组症状缓解显著优于安慰剂（p<0.05）",
         "simulated": True},
        {"claim_id": "C2", "doc_id": "D2", "topic": "益生菌干预改善成人IBS症状",
         "direction": "negative",
         "statement": "成人 RCT（n=80）中益生菌与安慰剂症状缓解无差异（p=0.34）",
         "simulated": True},
        {"claim_id": "C3", "doc_id": "D4", "topic": "饮食干预改善IBS患者生活质量",
         "direction": "positive",
         "statement": "老年人单臂试验中生活质量评分中度改善（无对照，不能归因）",
         "simulated": True},
        {"claim_id": "C4", "doc_id": "D5", "topic": "儿童饮食模式与不良事件关联",
         "direction": "neutral",
         "statement": "儿童队列中不良事件与饮食模式无关联",
         "simulated": True},
    ]
    with open(os.path.join(work, "claims.jsonl"), "w", encoding="utf-8") as f:
        for r in claims:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # topics.md 仅为回退路径演示（simulated）；本例 case.json 已提供 candidate_topics，
    # appraise 优先使用 case_extras，本文件不会被采用。
    write(os.path.join(work, "topics.md"),
          "# 候选选题（simulated，回退用，本例不生效）\n"
          "- 孕妇群体中益生菌干预的体内随机对照试验研究\n"
          "- 成人益生菌随机对照试验对IBS症状缓解的效果综合\n"
          "- 细胞系水平上益生菌菌株的体外抗炎机制研究\n")


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/bta-demo")
    cdir = make_case(root)
    work, out = os.path.join(root, "work"), os.path.join(root, "output")
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "init",
         "--case", os.path.join(cdir, "case.json"), "--task", os.path.join(cdir, "task.md"),
         "--input-dir", cdir, "--work", work, "--out", out])
    simulate_model_outputs(root)
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "gaps", "--work", work])
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "appraise",
         "--work", work, "--out", out])
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "finalize",
         "--work", work, "--out", out])

    appraisal = json.load(open(os.path.join(out, "appraisal_matrix.json"), encoding="utf-8"))
    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    print("\n=== 示例完成（SYNTHETIC）===")
    print(f"{'选题':<38} {'新颖度':>6} {'充分度':>6} {'约束':>6} {'总分':>6}  档位")
    for r in appraisal["appraisals"]:
        fit = "null" if r["constraint_fit"] is None else f"{r['constraint_fit']:.3f}"
        print(f"{r['topic']:<38} {r['novelty_within_corpus']:>6.3f} "
              f"{r['evidence_sufficiency']:>6.3f} {fit:>6} {r['weighted_total']:>6.3f}  "
              f"{r['recommendation']}")
    reg = result.get("gap_register") or {}
    print("gap_register:", reg.get("n_gaps"), "条",
          json.dumps(reg.get("by_type", {}), ensure_ascii=False))
    print("result.json status:", result.get("status"),
          "| uncertainties:", len(result.get("uncertainties", [])))
    print("产物目录:", out)


if __name__ == "__main__":
    main()
