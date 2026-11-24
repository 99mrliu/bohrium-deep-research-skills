#!/usr/bin/env python3
"""make_example.py — 合成示例（SYNTHETIC EXAMPLE，非正式案例结果）。

端到端演示 contract-first-budget-orchestrator：
  1. 在 <根目录>/case/ 生成合成语料：3 篇虚构全文短文（D1 支持、D2 反对、D3 中性）、
     D4 为 D1 的换题近重复、D5 仅摘要；case.json 含 output_contract。
  2. 真实运行 run_case.py init（ingest + contract_probe + budget_ledger plan），
     随即用 `budget_ledger.py status` 打印剩余预算与阶段 checkpoint。
  3. 【中断恢复演示】在写入任何模型阶段产物之前先运行一次 check：
     consistency_report 指出全部阶段缺失；随后写入"模拟模型输出"
     （screening/digests/themes/evidence_ledger/draft，标注 simulated，摘录从
     pages/<doc_id>.jsonl 程序化抽取保证逐字），用 budget_ledger.py mark 逐阶段
     登记，再运行 check 通过。
  4. 真实运行 finalize 组装 result.json，再跑一次 check 确认契约字段全部就位。
用法：python3 make_example.py <工作根目录>
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

P1_BODY = """External Synthetic Control Arms for Single-Arm Oncology Trials
M. Delacroix and H. Sun
2020

Abstract
This synthetic study evaluates external synthetic control arms built from historical
trial data for single-arm oncology studies.

Introduction
Single-arm oncology trials lack a concurrent comparator, so external controls are
increasingly used to contextualize response rates.

Methods
We constructed a synthetic control arm from two historical trial databases and
compared it with the randomized control arm of a completed phase three study.

Results
The synthetic control arm reproduced the randomized control hazard ratio within
a margin of 0.08 for overall survival in the matched cohort.
Objective response rate differed by less than 3 percentage points between arms.

Discussion
When eligibility criteria are aligned, synthetic control arms can approximate
randomized comparisons for this synthetic setting.

Limitations
The databases are synthetic and the matching variables are limited.

Conclusion
Synthetic control arms are a credible complement to randomized controls under
strict alignment of eligibility criteria.
""" + "Synthetic control methods require careful covariate balance checks. " * 55

P2_BODY = """Synthetic Control Arms Overestimate Benefit in Oncology Single-Arm Trials
K. Aalto, R. Petrov and D. Whitfield
2021

Abstract
This synthetic study warns that synthetic control arms can overestimate treatment
benefit when unmeasured confounding is present.

Methods
We simulated fifty synthetic single-arm oncology trials with known true effects
and benchmarked synthetic control estimates against the truth.

Results
In 62 percent of simulated trials the synthetic control arm overstated the
treatment effect on overall survival.
Bias was largest when performance status was not recorded in the external data.

Discussion
Unmeasured confounding, not sample size, was the dominant source of bias.

Conclusion
Synthetic control arms should not replace randomization when key prognostic
variables are missing from external data.
""" + "Residual confounding threatens external control validity in practice. " * 55

P3_BODY = """Regulatory Experience with External Controls: A Synthetic Review
L. Marchetti
2022

Abstract
This synthetic review summarizes regulatory interactions involving external
control arms submitted in oncology applications.

Methods
We reviewed twelve synthetic regulatory assessment reports that referenced
external or synthetic control arms between 2018 and 2021.

Results
Five of twelve submissions were accepted with external controls as supportive
evidence; none were accepted as the sole basis of approval.

Discussion
Regulators treated external controls as supportive rather than pivotal evidence.

Conclusion
External controls currently play a supportive role in oncology submissions.
""" + "Regulatory acceptance depends on data fitness and prespecification. " * 55

P5_ABSTRACT = """Propensity Scoring for Synthetic Controls: A Synthetic Abstract
Y. Tanaka
2023

Abstract
This synthetic abstract reports a propensity-scored synthetic control arm for
a single-arm oncology trial, reducing measured imbalance by 40 percent.
Full text was not provided for this synthetic record.
"""

D1_TITLE_LINE = "External Synthetic Control Arms for Single-Arm Oncology Trials"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_case(root):
    cdir = os.path.join(root, "case")
    write(os.path.join(cdir, "paper1.txt"), P1_BODY)
    write(os.path.join(cdir, "paper2.txt"), P2_BODY)
    write(os.path.join(cdir, "paper3.txt"), P3_BODY)
    # D4：D1 的换题近重复（预印本版，演示重复裁定与预算节约）
    write(os.path.join(cdir, "paper4.txt"),
          P1_BODY.replace(D1_TITLE_LINE,
                          "External Synthetic Control Arms for Single-Arm Oncology Trials (Preprint)", 1))
    write(os.path.join(cdir, "paper5.txt"), P5_ABSTRACT)
    case = {
        "case_id": "SYN-B-001",
        "research_question": "合成对照臂（synthetic control arm）能否替代随机对照用于肿瘤单臂试验的外部对照？（合成问题）",
        "documents": [
            {"path": "paper1.txt", "title": D1_TITLE_LINE, "year": 2020},
            {"path": "paper2.txt",
             "title": "Synthetic Control Arms Overestimate Benefit in Oncology Single-Arm Trials",
             "year": 2021},
            {"path": "paper3.txt",
             "title": "Regulatory Experience with External Controls: A Synthetic Review"},
            {"path": "paper4.txt",
             "title": "External Synthetic Control Arms for Single-Arm Oncology Trials (Preprint)"},
            {"path": "paper5.txt", "title": "Propensity Scoring for Synthetic Controls"},
        ],
        "output_contract": ["case_id", "status", "research_product", "evidence_matrix",
                            "screening_log", "run_plan", "uncertainties", "sources",
                            "change_log"],
    }
    write(os.path.join(cdir, "case.json"), json.dumps(case, ensure_ascii=False, indent=2))
    write(os.path.join(cdir, "task.md"),
          "# 合成任务（simulated）\n"
          "围绕研究问题完成筛选、主题归纳、证据组织与综述草稿。\n"
          "必须逐字段满足 case.json 的 output_contract，不得遗漏任何字段。\n"
          "所有证据摘录必须逐字来源于原文，不得转述。\n"
          "预算不得超过 64 次模型请求，须在 run_plan 中说明分配。\n")
    return cdir


def run(cmd, allow_fail=False):
    print("+", " ".join(os.path.basename(c) if i == 1 else c for i, c in enumerate(cmd)))
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0 and not allow_fail:
        raise SystemExit(f"命令失败（exit {r.returncode}）：{' '.join(cmd)}")
    return r.returncode


def grab(pages_rows, needle):
    """从 pages 行中找到含 needle 的页与一句完整摘录（保证逐字）。"""
    for row in pages_rows:
        for sent in re.split(r"(?<=[.!?]) ", row["text"].replace("\n", " ")):
            if needle in sent:
                return row["page"], sent.strip()
    raise SystemExit(f"needle not found: {needle}")


def load_pages(work, did):
    p = os.path.join(work, "pages", f"{did}.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def mark(work, out, phase, requests, artifact=None):
    cmd = [sys.executable, os.path.join(SCRIPTS, "budget_ledger.py"), "mark",
           "--work", work, "--phase", phase, "--requests", str(requests),
           "--out", out]
    if artifact:
        cmd += ["--artifact", artifact]
    run(cmd)


def simulate_model_outputs(root):
    """写入模拟模型阶段产物（simulated model outputs，非真实模型生成）。"""
    work = os.path.join(root, "work")
    pages = {did: load_pages(work, did) for did in ("D1", "D2", "D3", "D4", "D5")}

    # —— screening（simulated）——
    screening = {
        "simulated": True,
        "criteria": {"include": ["IC1 直接评估外部/合成对照臂用于肿瘤单臂试验",
                                 "IC2 报告与随机对照或真实值的可比结果"],
                     "exclude": ["EC1 与研究问题无关", "EC2 重复版本（保留代表篇）"]},
        "decisions": [
            {"doc_id": "D1", "decision": "include", "reason": "IC1, IC2"},
            {"doc_id": "D2", "decision": "include", "reason": "IC1, IC2"},
            {"doc_id": "D3", "decision": "include", "reason": "IC1"},
            {"doc_id": "D4", "decision": "exclude", "reason": "EC2 duplicate_of D1"},
            {"doc_id": "D5", "decision": "include",
             "reason": "IC1（abstract_only，证据强度 ≤ suggestive）"}],
    }
    write(os.path.join(work, "screening_log.json"),
          json.dumps(screening, ensure_ascii=False, indent=2))

    # —— digests（simulated，每篇一个文件；深度来自 run_plan）——
    plan = json.load(open(os.path.join(work, "run_plan.json"), encoding="utf-8"))
    for r in plan["reading_plan"]:
        if r["depth"] in ("full", "sections", "abstract"):
            did = r["doc_id"]
            write(os.path.join(work, "digests", f"{did}.md"),
                  f"# digest {did}（simulated）\n深度：{r['depth']}（overlap={r['overlap_score']}）\n"
                  "对象：肿瘤单臂试验外部对照；方法：合成对照臂构建/评估；"
                  "结论与关键数字见 evidence_ledger。\n")

    # —— themes（simulated，主题从 digest 归纳，非模板）——
    themes = [
        {"theme": "T1", "label": "合成对照臂与随机对照的一致性证据",
         "boundary": "直接比较合成对照臂与随机对照或已知真值的研究", "docs": ["D1", "D2"]},
        {"theme": "T2", "label": "监管接受度与证据定位",
         "boundary": "监管机构对外部对照证据的采信程度", "docs": ["D3", "D5"]},
    ]
    write(os.path.join(work, "themes.json"), json.dumps(themes, ensure_ascii=False, indent=2))

    # —— evidence_ledger（simulated，摘录程序化抽取保证逐字）——
    p1, s1 = grab(pages["D1"], "reproduced the randomized control hazard ratio within")
    p2, s2 = grab(pages["D2"], "overstated the")
    p3, s3 = grab(pages["D2"], "dominant source of bias")
    p4, s4 = grab(pages["D3"], "supportive rather than pivotal")
    p5, s5 = grab(pages["D5"], "reducing measured imbalance by 40 percent")
    ledger = [
        {"evidence_id": "E1", "doc_id": "D1", "locator": f"p{p1}.¶1", "verbatim_quote": s1,
         "supports": "匹配队列中合成对照臂复现随机对照的总生存风险比（误差 0.08 内）",
         "theme": "T1", "strength": "suggestive", "quote_lang": "en"},
        {"evidence_id": "E2", "doc_id": "D2", "locator": f"p{p2}.¶1", "verbatim_quote": s2,
         "supports": "62% 的模拟试验中合成对照臂高估了总生存获益",
         "theme": "T1", "strength": "contested", "quote_lang": "en"},
        {"evidence_id": "E3", "doc_id": "D2", "locator": f"p{p3}.¶1", "verbatim_quote": s3,
         "supports": "未测量混杂而非样本量是偏倚主导来源",
         "theme": "T1", "strength": "contested", "quote_lang": "en"},
        {"evidence_id": "E4", "doc_id": "D3", "locator": f"p{p4}.¶1", "verbatim_quote": s4,
         "supports": "监管将外部对照定位为支持性而非关键性证据",
         "theme": "T2", "strength": "suggestive", "quote_lang": "en"},
        {"evidence_id": "E5", "doc_id": "D5", "locator": f"p{p5}.¶1", "verbatim_quote": s5,
         "supports": "倾向评分合成对照减少 40% 可测失衡（仅摘要）",
         "theme": "T2", "strength": "suggestive", "quote_lang": "en"},
    ]
    with open(os.path.join(work, "evidence_ledger.jsonl"), "w", encoding="utf-8") as f:
        for row in ledger:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # —— draft（simulated）——
    draft = """# 合成对照臂能否替代随机对照：综述草稿（simulated 示例）

## 主题一：合成对照臂与随机对照的一致性证据
单项合成研究报告，匹配队列中合成对照臂可在 0.08 误差内复现随机对照的总生存风险比。[E1]
另一模拟基准研究则发现 62% 的模拟试验中合成对照臂高估了生存获益。[E2]
两篇文献结论相反，分歧可能源于外部数据中关键预后变量是否可得。[E3]
[推断] 现有证据仅支持"在严格对齐入排标准且预后变量完备时，合成对照臂可作为补充"，
不支持"替代随机对照"的强结论。

## 主题二：监管接受度与证据定位
监管综述显示外部对照目前被定位为支持性证据而非关键性证据。[E4]
方法学摘要提示倾向评分可进一步减少可测失衡。[E5]
[证据缺口] 所有证据均来自合成数据或摘要，缺乏真实注册试验中的前瞻性对照验证。

## 不确定性
- D5 仅摘要可用，证据强度不超过 suggestive。
- D4 为 D1 的预印本近重复，仅代表篇 D1 进入阅读计划。
"""
    write(os.path.join(work, "review_draft.md"), draft)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/cfo-demo")
    cdir = make_case(root)
    work, out = os.path.join(root, "work"), os.path.join(root, "output")
    run_case = os.path.join(SCRIPTS, "run_case.py")

    print("== 1. init（真实执行：ingest + contract_probe + budget_ledger plan）==")
    run([sys.executable, run_case, "init",
         "--case", os.path.join(cdir, "case.json"), "--task", os.path.join(cdir, "task.md"),
         "--input-dir", cdir, "--work", work, "--out", out, "--budget", "64"])

    print("\n== 2. 断点账本 status（剩余预算与阶段）==")
    run([sys.executable, os.path.join(SCRIPTS, "budget_ledger.py"), "status", "--work", work])

    print("\n== 3. 中断恢复演示：模型阶段产物尚未写入，先跑一次 check ==")
    rc = run([sys.executable, run_case, "check", "--work", work, "--out", out],
             allow_fail=True)
    print(f"   check 退出码 {rc}（预期非 0：consistency_report 指出缺失阶段）")
    report = json.load(open(os.path.join(out, "consistency_report.json"), encoding="utf-8"))
    print("   缺失阶段：", [c["phase"] for c in report["phase_checks"]
                           if c["status"] != "completed"])

    print("\n== 4. 写入模拟模型产物（simulated）并逐阶段 mark ==")
    simulate_model_outputs(root)
    mark(work, out, "screening", 1)
    mark(work, out, "digests", 2)
    mark(work, out, "themes", 3)
    mark(work, out, "evidence_ledger", 2)
    mark(work, out, "draft", 3)

    print("\n== 5. 补齐后 check（应通过）==")
    run([sys.executable, run_case, "check", "--work", work, "--out", out])
    mark(work, out, "verify_repair", 0,
         artifact=os.path.join(out, "consistency_report.json"))

    print("\n== 6. finalize（真实执行：组装 result.json）==")
    run([sys.executable, run_case, "finalize", "--work", work, "--out", out])

    print("\n== 7. 终态 check（契约字段全部就位）==")
    run([sys.executable, run_case, "check", "--work", work, "--out", out])
    run([sys.executable, os.path.join(SCRIPTS, "budget_ledger.py"), "status", "--work", work])

    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    contract = json.load(open(os.path.join(cdir, "case.json"), encoding="utf-8"))["output_contract"]
    missing = [f for f in contract if f not in result]
    print("\n=== 示例完成（SYNTHETIC）===")
    print("status:", result.get("status"),
          "| 契约字段:", f"{len(contract) - len(missing)}/{len(contract)} 就位",
          "| 缺失:", missing or "无")
    print("证据行:", len(result.get("evidence_matrix", [])),
          "| uncertainties:", len(result.get("uncertainties", [])),
          "| change_log:", len(result.get("change_log", [])),
          "| 预算:", result.get("budget_summary"))
    print("产物目录:", out)


if __name__ == "__main__":
    main()
