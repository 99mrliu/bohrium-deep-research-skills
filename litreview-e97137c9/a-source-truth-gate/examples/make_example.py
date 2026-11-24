#!/usr/bin/env python3
"""make_example.py — 合成示例（SYNTHETIC EXAMPLE，非正式案例结果）。

端到端演示 source-truth-gate：
  1. 在 <根目录>/case/ 生成合成语料：4 篇虚构短文（D1 全文、D2 全文且结论冲突、
     D3 仅摘要、D4 为 D1 的换题近重复），case.json 故意给 D2 错误的年份以演示
     元数据冲突检测。
  2. 真实运行 run_case.py init（解析 + 来源取证）。
  3. 写入"模拟模型输出"（screening/digests/themes/evidence_ledger/review_draft，
     全部标注 simulated；摘录由脚本从原文程序化抽取，保证逐字）。
  4. 真实运行 verify（引用门控）与 finalize（组装 result.json）。
用法：python3 make_example.py <工作根目录>
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

P1_BODY = """Adaptive Sparse Retrieval for Clinical Notes
J. Meyer and L. Okafor
2021

Abstract
This synthetic study investigates adaptive sparse retrieval for clinical notes.

Introduction
Retrieval over clinical notes is difficult because terminology varies across departments.

Methods
We evaluated an adaptive sparse retriever on two synthetic cohorts of de-identified notes.

Results
The adaptive retriever improved recall at ten from 0.61 to 0.74 on the synthetic cohort.
Indexing cost increased by 18 percent relative to the static baseline.

Discussion
Gains were consistent across both cohorts, suggesting robustness of the approach.

Limitations
The cohorts are synthetic and small, so external validity is limited.

Conclusion
Adaptive sparse retrieval is a promising direction for clinical note search.
""" + "Additional synthetic padding sentence for length. " * 60

P2_BODY = """Static Baselines Remain Competitive for Clinical Note Retrieval
R. Alvarez, P. Novak and S. Iwate
2019

Abstract
This synthetic study re-examines whether adaptive retrieval beats static baselines.

Methods
We benchmarked a static BM25-style baseline against an adaptive sparse retriever
on three synthetic collections of clinical notes.

Results
The static baseline matched the adaptive retriever on two of three collections.
On the largest collection the adaptive retriever improved recall at ten by 0.05.
Runtime for the adaptive method was 1.4 times higher than the static baseline.

Discussion
The advantage of adaptation appears condition dependent rather than universal.

Conclusion
Static baselines should remain the default reference point in this setting.
""" + "Further synthetic filler sentence to reach fulltext length. " * 60

P3_ABSTRACT = """Query Expansion with Medical Ontologies: A Synthetic Abstract
T. Beaumont
2022

Abstract
This synthetic abstract reports ontology-based query expansion for clinical notes.
Expansion with a curated ontology improved recall at ten by 0.03 on one collection.
Full text was not provided for this synthetic record.
"""

D2_TITLE_LINE = "Static Baselines Remain Competitive for Clinical Note Retrieval"
D1_TITLE_LINE = "Adaptive Sparse Retrieval for Clinical Notes"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_case(root):
    cdir = os.path.join(root, "case")
    write(os.path.join(cdir, "paper1.txt"), P1_BODY)
    write(os.path.join(cdir, "paper2.txt"), P2_BODY)
    write(os.path.join(cdir, "paper3.txt"), P3_ABSTRACT)
    # D4：D1 的换题近重复（演示重复裁定）
    write(os.path.join(cdir, "paper4.txt"),
          P1_BODY.replace(D1_TITLE_LINE, "Adaptive Sparse Retrieval for Clinical Notes (Preprint Version)", 1))
    case = {
        "case_id": "SYN-A-001",
        "research_question": "自适应稀疏检索是否稳定优于静态基线用于临床笔记检索？（合成问题）",
        "documents": [
            {"path": "paper1.txt", "title": D1_TITLE_LINE, "year": 2021},
            {"path": "paper2.txt", "title": D2_TITLE_LINE, "year": 2021},
            {"path": "paper3.txt", "title": "Query Expansion with Medical Ontologies"},
            {"path": "paper4.txt", "title": "Adaptive Sparse Retrieval for Clinical Notes (Preprint Version)"},
        ],
        "output_contract": ["case_id", "status", "research_product", "evidence_matrix",
                            "uncertainties", "sources", "change_log"],
    }
    write(os.path.join(cdir, "case.json"), json.dumps(case, ensure_ascii=False, indent=2))
    write(os.path.join(cdir, "task.md"),
          "# 合成任务（simulated）\n围绕研究问题完成筛选、主题归纳、证据组织与综述草稿。\n")
    return cdir


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def grab(pages_rows, needle):
    """从 pages 行中找到含 needle 的页与一句完整摘录。"""
    for row in pages_rows:
        for sent in re.split(r"(?<=[.!?]) ", row["text"].replace("\n", " ")):
            if needle in sent:
                return row["page"], sent.strip()
    raise SystemExit(f"needle not found: {needle}")


def simulate_model_outputs(root):
    """写入模拟模型阶段产物（simulated model outputs，非真实模型生成）。"""
    work = os.path.join(root, "work")
    pages = {}
    for did in ("D1", "D2", "D3", "D4"):
        rows = []
        p = os.path.join(work, "pages", f"{did}.jsonl")
        if os.path.exists(p):
            rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        pages[did] = rows

    write(os.path.join(work, "criteria.md"),
          "# 筛选标准（simulated）\nIC1 直接比较自适应检索与静态基线\nIC2 报告可比较指标\n"
          "EC1 与研究问题无关\nEC2 重复版本（保留代表篇）\n")
    screening = {"criteria": {"include": ["IC1", "IC2"], "exclude": ["EC1", "EC2"]},
                 "decisions": [
                     {"doc_id": "D1", "decision": "include", "reason": "IC1, IC2"},
                     {"doc_id": "D2", "decision": "include", "reason": "IC1, IC2"},
                     {"doc_id": "D3", "decision": "include", "reason": "IC1（abstract_only，仅 suggestive）"},
                     {"doc_id": "D4", "decision": "exclude", "reason": "EC2 duplicate_of D1"}]}
    write(os.path.join(work, "screening_log.json"), json.dumps(screening, ensure_ascii=False, indent=2))
    themes = [{"theme": "T1", "label": "自适应 vs 静态检索的有效性分歧",
               "boundary": "直接比较两类方法在临床笔记检索上效果的研究",
               "docs": ["D1", "D2", "D3"]}]
    write(os.path.join(work, "themes.json"), json.dumps(themes, ensure_ascii=False, indent=2))

    p1, s1 = grab(pages["D4"], "improved recall at ten from 0.61 to 0.74")
    p2, s2 = grab(pages["D2"], "matched the adaptive retriever on two of three collections")
    p3, s3 = grab(pages["D2"], "condition dependent rather than universal")
    p4, s4 = grab(pages["D3"], "improved recall at ten by 0.03")
    ledger = [
        {"evidence_id": "E1", "doc_id": "D4", "locator": f"p{p1}.¶1", "verbatim_quote": s1,
         "supports": "自适应稀疏检索在合成队列上 recall@10 由 0.61 提升至 0.74",
         "theme": "T1", "strength": "suggestive", "quote_lang": "en"},
        {"evidence_id": "E2", "doc_id": "D2", "locator": f"p{p2}.¶1", "verbatim_quote": s2,
         "supports": "静态基线在三分之二集合上与自适应方法持平",
         "theme": "T1", "strength": "contested", "quote_lang": "en"},
        {"evidence_id": "E3", "doc_id": "D2", "locator": f"p{p3}.¶1", "verbatim_quote": s3,
         "supports": "自适应方法的优势具有条件依赖性而非普遍成立",
         "theme": "T1", "strength": "contested", "quote_lang": "en"},
        {"evidence_id": "E4", "doc_id": "D3", "locator": f"p{p4}.¶1", "verbatim_quote": s4,
         "supports": "本体查询扩展在单一集合上 recall@10 提升 0.03（仅摘要）",
         "theme": "T1", "strength": "suggestive", "quote_lang": "en"},
    ]
    with open(os.path.join(work, "evidence_ledger.jsonl"), "w", encoding="utf-8") as f:
        for r in ledger:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    draft = """# 自适应稀疏检索是否稳定优于静态基线：综述草稿（simulated 示例）

## 主题一：自适应与静态检索的有效性分歧
单一合成研究报告自适应稀疏检索将 recall@10 由 0.61 提升至 0.74。[E1]
另一合成研究在三个集合中的两个上未观察到自适应方法优于静态基线。[E2]
两篇文献的结论存在分歧，分歧可能源于集合规模与评价条件的差异。[E3]
[推断] 现有证据不足以支持"自适应方法普遍占优"的强结论，仅支持条件性收益。
[证据缺口] 所有证据均来自合成小样本集合，缺乏真实临床语料上的对照。

## 不确定性
- D3 仅摘要可用，证据强度不超过 suggestive。
- D2 的 case 元数据年份与正文年份不一致，已按 T2 降级。
"""
    write(os.path.join(work, "review_draft.md"), draft)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/stg-demo")
    cdir = make_case(root)
    work, out = os.path.join(root, "work"), os.path.join(root, "output")
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "init",
         "--case", os.path.join(cdir, "case.json"), "--task", os.path.join(cdir, "task.md"),
         "--input-dir", cdir, "--work", work, "--out", out])
    simulate_model_outputs(root)
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "verify", "--work", work, "--out", out])
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "finalize", "--work", work, "--out", out])
    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    print("\n=== 示例完成（SYNTHETIC）===")
    print("status:", result.get("status"), "| 证据行:", len(result.get("evidence_matrix", [])),
          "| uncertainties:", len(result.get("uncertainties", [])))
    print("产物目录:", out)


if __name__ == "__main__":
    main()
