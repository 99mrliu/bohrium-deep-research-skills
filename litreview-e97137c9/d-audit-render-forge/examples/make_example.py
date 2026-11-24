#!/usr/bin/env python3
"""make_example.py — 合成示例（SYNTHETIC EXAMPLE，非正式案例结果）。

端到端演示 audit-render-forge 的"校验-修复"闭环：
  1. 在 <根目录>/case/ 生成合成语料：4 篇虚构短文（D1 全文、D2 全文且结论冲突、
     D3 仅摘要、D4 为 D1 的换题近重复）。
  2. 真实运行 run_case.py init（防御式解析 + 锚点化 + 分级 + 近重复分组）。
  3. 写入"模拟模型输出"（themes/evidence_ledger/review_draft，全部标注 simulated；
     摘录由脚本从 pages/<doc_id>.jsonl 程序化抽取，保证逐字）。草稿故意包含：
     - 一句引用不存在的 [E99] 的论断（演示 link_check 失败）；
     - 一句无证据标记的实质句（演示警告清单）。
  4. 真实运行 render：link_check 检出 [E99] 未解析，**非零退出**并打印报告。
  5. 脚本自动修复草稿（删去引用 E99 的句子），重跑 render 通过。
  6. 真实运行 finalize：build_result + validate_result，打印结果摘要。
用法：python3 make_example.py <工作根目录>
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

P1_BODY = """Lexical-Semantic Hybrid Search for Radiology Reports
M. Chen and A. Duarte
2020

Abstract
This synthetic study evaluates a hybrid lexical-semantic retriever for radiology reports.

Introduction
Searching radiology reports is difficult because findings are described with varied phrasing.

Methods
We compared a hybrid retriever with a sparse lexical baseline on two synthetic report collections.

Results
The hybrid retriever improved nDCG at ten from 0.58 to 0.71 on the larger synthetic collection.
Query latency increased by 22 percent relative to the lexical baseline.

Discussion
Improvements were larger on reports with synonymous descriptions of the same finding.

Limitations
Both collections are synthetic and derived from a single institution template.

Conclusion
Hybrid lexical-semantic retrieval is a promising default for radiology report search.
""" + "Additional synthetic padding sentence for length. " * 60

P2_BODY = """Sparse Baselines for Radiology Report Search Revisited
K. Hoffmann, Y. Petrov and D. Anselm
2022

Abstract
This synthetic study re-examines whether hybrid retrieval beats sparse baselines.

Methods
We benchmarked a tuned sparse baseline against a hybrid lexical-semantic retriever
on three synthetic collections of radiology reports.

Results
The sparse baseline matched the hybrid retriever on two of three collections.
On the largest collection the hybrid retriever improved nDCG at ten by 0.04.
Index build time for the hybrid method was 1.6 times higher than the sparse baseline.

Discussion
The benefit of semantic components appears condition dependent rather than universal.

Conclusion
Tuned sparse baselines should remain the reference point for report search evaluation.
""" + "Further synthetic filler sentence to reach fulltext length. " * 60

P3_ABSTRACT = """Entity Linking for Report Retrieval: A Synthetic Abstract
S. Villanueva
2023

Abstract
This synthetic abstract reports entity linking as a preprocessing step for report retrieval.
Linking reports to a controlled vocabulary improved nDCG at ten by 0.02 on one collection.
Full text was not provided for this synthetic record.
"""

D1_TITLE_LINE = "Lexical-Semantic Hybrid Search for Radiology Reports"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_case(root):
    cdir = os.path.join(root, "case")
    write(os.path.join(cdir, "paper1.txt"), P1_BODY)
    write(os.path.join(cdir, "paper2.txt"), P2_BODY)
    write(os.path.join(cdir, "paper3.txt"), P3_ABSTRACT)
    # D4：D1 的换题近重复（演示近重复分组与覆盖矩阵中的"未覆盖文档"）
    write(os.path.join(cdir, "paper4.txt"),
          P1_BODY.replace(D1_TITLE_LINE,
                          "Lexical-Semantic Hybrid Search for Radiology Reports (Workshop Version)", 1))
    case = {
        "case_id": "SYN-D-001",
        "research_question": "混合检索是否稳定优于稀疏基线用于放射学报告检索？（合成问题）",
        "documents": [
            {"path": "paper1.txt", "title": D1_TITLE_LINE, "year": 2020},
            {"path": "paper2.txt", "title": "Sparse Baselines for Radiology Report Search Revisited", "year": 2022},
            {"path": "paper3.txt", "title": "Entity Linking for Report Retrieval"},
            {"path": "paper4.txt", "title": "Lexical-Semantic Hybrid Search for Radiology Reports (Workshop Version)"},
        ],
        "output_contract": ["case_id", "status", "research_product", "evidence_matrix",
                            "audit_artifacts", "link_check", "uncertainties", "sources", "change_log"],
    }
    write(os.path.join(cdir, "case.json"), json.dumps(case, ensure_ascii=False, indent=2))
    write(os.path.join(cdir, "task.md"),
          "# 合成任务（simulated）\n围绕研究问题完成主题归纳、证据组织、综述草稿与可复核审计包交付。\n")
    return cdir


def run(cmd, expect_rc=0):
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.rstrip())
    if proc.stderr.strip():
        print(proc.stderr.rstrip(), file=sys.stderr)
    if expect_rc is not None and proc.returncode != expect_rc:
        raise SystemExit(f"命令退出码 {proc.returncode}，期望 {expect_rc}: {' '.join(cmd)}")
    return proc


def grab(pages_rows, needle):
    """从 pages 行中找到含 needle 的页与一句完整摘录（保证逐字）。"""
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
        p = os.path.join(work, "pages", f"{did}.jsonl")
        pages[did] = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] \
            if os.path.exists(p) else []

    themes = [
        {"theme": "T1", "label": "混合检索与稀疏基线的有效性分歧",
         "boundary": "直接比较混合检索与稀疏基线在放射学报告检索上效果的研究",
         "docs": ["D1", "D2"]},
        {"theme": "T2", "label": "检索预处理的轻量改进",
         "boundary": "不改主检索器、仅做实体链接等预处理的研究",
         "docs": ["D3"]},
    ]
    write(os.path.join(work, "themes.json"), json.dumps(themes, ensure_ascii=False, indent=2))

    p1, s1 = grab(pages["D1"], "improved nDCG at ten from 0.58 to 0.71")
    p2, s2 = grab(pages["D2"], "matched the hybrid retriever on two of three collections")
    p3, s3 = grab(pages["D2"], "condition dependent rather than universal")
    p4, s4 = grab(pages["D3"], "improved nDCG at ten by 0.02")
    ledger = [
        {"evidence_id": "E1", "doc_id": "D1", "locator": f"p{p1}.¶1", "verbatim_quote": s1,
         "supports": "混合检索在较大合成集合上 nDCG@10 由 0.58 提升至 0.71",
         "theme": "T1", "strength": "established", "quote_lang": "en"},
        {"evidence_id": "E2", "doc_id": "D2", "locator": f"p{p2}.¶1", "verbatim_quote": s2,
         "supports": "稀疏基线在三分之二集合上与混合检索持平",
         "theme": "T1", "strength": "contested", "quote_lang": "en"},
        {"evidence_id": "E3", "doc_id": "D2", "locator": f"p{p3}.¶1", "verbatim_quote": s3,
         "supports": "语义组件的收益具有条件依赖性而非普遍成立",
         "theme": "T1", "strength": "contested", "quote_lang": "en"},
        {"evidence_id": "E4", "doc_id": "D3", "locator": f"p{p4}.¶1", "verbatim_quote": s4,
         "supports": "实体链接预处理在单一集合上 nDCG@10 提升 0.02（仅摘要）",
         "theme": "T2", "strength": "suggestive", "quote_lang": "en"},
    ]
    with open(os.path.join(work, "evidence_ledger.jsonl"), "w", encoding="utf-8") as f:
        for r in ledger:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 草稿（simulated）：故意包含 [E99] 坏引用 + 一句无标记实质句，用于闭环演示
    draft = """# 混合检索是否稳定优于稀疏基线：综述草稿（simulated 示例）

## 主题一：混合检索与稀疏基线的有效性分歧
本主题纳入直接比较两类方法的两篇全文文献。
单一合成研究报告混合检索将 nDCG@10 由 0.58 提升至 0.71。[E1]
另一合成研究在三个集合中的两个上未观察到混合检索优于稀疏基线。[E2]
两篇文献的结论存在分歧，分歧可能源于集合规模与评价条件的差异。[E3]
有研究声称混合检索在全部真实语料上稳定占优。[E99]
[推断] 现有证据不足以支持"混合检索普遍占优"的强结论，仅支持条件性收益。

## 主题二：检索预处理的轻量改进
实体链接作为预处理步骤在单一合成集合上带来 0.02 的 nDCG@10 提升。[E4]

## 研究空白
[证据缺口] 所有证据均来自单一机构模板的合成集合，缺乏跨机构真实语料上的对照。

## 不确定性
- D3 仅摘要可用，证据强度不超过 suggestive。
- D4 为 D1 的近重复版本，未纳入主题与证据池。
总体来看这批合成文献样本量小且结论方向并不一致。
"""
    write(os.path.join(work, "review_draft.md"), draft)


def fix_draft(root):
    """自动修复：删去引用不存在证据（[E99]）的句子所在行。"""
    path = os.path.join(root, "work", "review_draft.md")
    lines = open(path, encoding="utf-8").read().splitlines()
    kept = [l for l in lines if "[E99]" not in l]
    removed = len(lines) - len(kept)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")
    print(f"[fix] 已从草稿删除 {removed} 行含 [E99] 的坏引用句")


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/arf-demo")
    cdir = make_case(root)
    work, out = os.path.join(root, "work"), os.path.join(root, "output")
    runner = os.path.join(SCRIPTS, "run_case.py")

    print("== 阶段 0：init ==")
    run([sys.executable, runner, "init",
         "--case", os.path.join(cdir, "case.json"), "--task", os.path.join(cdir, "task.md"),
         "--input-dir", cdir, "--work", work, "--out", out])

    simulate_model_outputs(root)

    print("\n== 第一次 render（预期 link_check 失败：[E99] 未解析）==")
    run([sys.executable, runner, "render", "--work", work, "--out", out], expect_rc=1)
    report = json.load(open(os.path.join(out, "link_check_report.json"), encoding="utf-8"))
    print("[link_check] failures:", json.dumps(report["failures"], ensure_ascii=False))

    print("\n== 自动修复并重跑 render（预期通过）==")
    fix_draft(root)
    run([sys.executable, runner, "render", "--work", work, "--out", out], expect_rc=0)

    print("\n== finalize（build_result + validate_result）==")
    run([sys.executable, runner, "finalize", "--work", work, "--out", out], expect_rc=0)

    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    validation = json.load(open(os.path.join(out, "validation_report.json"), encoding="utf-8"))
    html_path = os.path.join(out, "audit_report.html")
    html_text = open(html_path, encoding="utf-8").read()
    print("\n=== 示例完成（SYNTHETIC）===")
    print("status:", result.get("status"),
          "| 证据行:", len(result.get("evidence_matrix", [])),
          "| uncertainties:", len(result.get("uncertainties", [])),
          "| validation_ok:", validation.get("ok"))
    print(f"audit_report.html: {os.path.getsize(html_path)} 字节，"
          f"论断块 {html_text.count('<section class=\"claim\"')} 个")
    print("产物目录:", out)


if __name__ == "__main__":
    main()
