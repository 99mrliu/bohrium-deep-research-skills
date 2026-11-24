#!/usr/bin/env python3
"""make_example.py — 合成示例（SYNTHETIC EXAMPLE，非正式案例结果）。

端到端演示 quant-evidence-synth：
  1. 在 <根目录>/case/ 生成合成语料：4 篇虚构短文——
     D1 全文（recall@10 0.74、延迟 350 ms）、D2 全文（recall@10 0.52，与 D1 差异 >20%
     且 CI 不重叠 → 演示冲突检测；延迟 0.31 s，与 D1 的 ms 单位不一致 → 演示归一化）、
     D3 仅摘要（precision 0.81 + 无单位 RMSE 4.2 → 演示 unnormalized）、
     D4 为 D1 的换题近重复（演示冲突检测只取代表篇）。
  2. 真实运行 run_case.py init（解析 + 抽取 + 归一化 + 冲突检测）。
  3. 写入"模拟模型输出"（themes/screening/evidence_table/review_draft，全部标注
     simulated；草稿与证据表中的数字全部由脚本从 quant candidates 程序化取值，
     保证数字回链门控通过；其中 81% 与 0.35 s 演示百分数/ratio 等价与单位换算容忍）。
  4. 真实运行 verify（数字回链门控）与 finalize（组装 result.json），打印摘要。
用法：python3 make_example.py <工作根目录>
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

P1_BODY = """Distilled Student Models for On-Device Intent Classification
A. Ferreira and K. Tanaka
2022

Abstract
This synthetic study evaluates a distilled student model for on-device intent classification.

Introduction
On-device intent classification requires models that are both accurate and fast.

Methods
We distilled a large teacher model into a compact student and evaluated it on a synthetic benchmark of user intents.

Results
The distilled model achieved recall@10 of 0.74 (95% CI [0.68, 0.80]) on n = 480 synthetic queries, p < 0.01.
Mean latency was 350 ms per query (95% CI [320, 380]).
The teacher model remained slightly better on rare intents.

Discussion
The results suggest distillation preserves most retrieval quality on common intents.

Limitations
The benchmark is synthetic and may not reflect production traffic.

Conclusion
Distilled students are a viable option for on-device intent classification.
""" + "Additional synthetic padding sentence for length. " * 60

P2_BODY = """Static Teachers Remain Strong for On-Device Intent Classification
M. Duarte, H. Lindqvist and P. Osei
2023

Abstract
This synthetic study re-examines whether distilled students match static teachers.

Methods
We benchmarked a distilled student against a static teacher on the same synthetic intent benchmark.

Results
On the same synthetic benchmark the distilled student reached recall@10 of 0.52 (95% CI [0.44, 0.60]).
Average latency was 0.31 s per query on the test device.

Discussion
The quality gap appears larger than previously reported under this evaluation condition.

Conclusion
Static teachers should remain the reference point for on-device intent classification.
""" + "Further synthetic filler sentence to reach fulltext length. " * 60

P3_ABSTRACT = """Calibration of Distilled Intent Classifiers: A Synthetic Abstract
L. Moreau
2024

Abstract
This synthetic abstract reports calibration of distilled intent classifiers.
The calibrated student achieved precision of 0.81 on the synthetic dev split.
RMSE of the confidence estimator was 4.2 on the synthetic calibration set.
Full text was not provided for this synthetic record.
"""

D1_TITLE = "Distilled Student Models for On-Device Intent Classification"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def fmt(v):
    return f"{v:g}"


def make_case(root):
    cdir = os.path.join(root, "case")
    write(os.path.join(cdir, "paper1.txt"), P1_BODY)
    write(os.path.join(cdir, "paper2.txt"), P2_BODY)
    write(os.path.join(cdir, "paper3.txt"), P3_ABSTRACT)
    # D4：D1 的换题近重复（演示冲突检测只取代表篇）
    write(os.path.join(cdir, "paper4.txt"),
          P1_BODY.replace(D1_TITLE, D1_TITLE + " (Preprint Version)", 1))
    case = {
        "case_id": "SYN-C-001",
        "research_question": "蒸馏学生模型能否在端侧意图分类上兼顾召回率与延迟？（合成问题）",
        "documents": [
            {"path": "paper1.txt", "title": D1_TITLE, "year": 2022},
            {"path": "paper2.txt", "title": "Static Teachers Remain Strong for On-Device Intent Classification", "year": 2023},
            {"path": "paper3.txt", "title": "Calibration of Distilled Intent Classifiers"},
            {"path": "paper4.txt", "title": D1_TITLE + " (Preprint Version)"},
        ],
        "output_contract": ["case_id", "status", "research_product", "quant_summary",
                            "numeric_conflicts", "evidence_table",
                            "uncertainties", "sources", "change_log"],
    }
    write(os.path.join(cdir, "case.json"), json.dumps(case, ensure_ascii=False, indent=2))
    write(os.path.join(cdir, "task.md"),
          "# 合成任务（simulated）\n围绕研究问题完成定量证据抽取、数值冲突合成与综述草稿。\n")
    return cdir


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def pick(cands, doc_id, metric):
    for c in cands:
        if c["doc_id"] == doc_id and c.get("metric") == metric:
            return c
    raise SystemExit(f"candidate not found: {doc_id}/{metric}")


def simulate_model_outputs(root):
    """写入模拟模型阶段产物（simulated model outputs，非真实模型生成）。

    草稿与证据表中的每个数字都程序化取自 quant candidates（含 81%≡0.81 与
    350 ms≡0.35 s 的等价写法），保证数字回链门控通过。
    """
    work = os.path.join(root, "work")
    cands = load_jsonl(os.path.join(work, "quant_normalized.jsonl"))
    r1 = pick(cands, "D1", "recall@10")
    r2 = pick(cands, "D2", "recall@10")
    l1 = pick(cands, "D1", "latency")
    l2 = pick(cands, "D2", "latency")
    p3 = pick(cands, "D3", "precision")
    m3 = pick(cands, "D3", "rmse")
    n1 = pick(cands, "D1", "sample_size")
    v1 = pick(cands, "D1", "pvalue")

    themes = [{"theme": "T1", "label": "蒸馏学生模型召回率的跨研究分歧",
               "boundary": "报告 recall@10 且可相互比较的研究", "docs": ["D1", "D2"]},
              {"theme": "T2", "label": "端侧延迟",
               "boundary": "报告单查询延迟的研究（单位口径不一致，已归一化）", "docs": ["D1", "D2"]},
              {"theme": "T3", "label": "单源与不可比数值",
               "boundary": "仅单一来源或未归一化的数值", "docs": ["D3"]}]
    write(os.path.join(work, "themes.json"), json.dumps(themes, ensure_ascii=False, indent=2))
    screening = {"criteria": {"include": ["IC1 报告可比较定量指标"], "exclude": ["EC1 重复版本"]},
                 "decisions": [
                     {"doc_id": "D1", "decision": "include", "reason": "IC1"},
                     {"doc_id": "D2", "decision": "include", "reason": "IC1"},
                     {"doc_id": "D3", "decision": "include", "reason": "IC1（abstract_only，仅 suggestive）"},
                     {"doc_id": "D4", "decision": "exclude", "reason": "EC1 近重复，代表篇 D1"}]}
    write(os.path.join(work, "screening_log.json"), json.dumps(screening, ensure_ascii=False, indent=2))

    def ci_str(c):
        return f"95% CI [{fmt(c['ci_low'])}, {fmt(c['ci_high'])}]" if c.get("ci_low") is not None else "无 CI"

    table = f"""# 定量证据表（simulated 示例；数值均回链 quant candidates）

| 证据ID | qid | 文献 | 定位 | 指标 | 数值(原文) | 归一化值 | 强度 | 备注 |
|-|-|-|-|-|-|-|-|-|
| E1 | {r1['qid']} | D1 | {r1['locator']} | recall@10 | {fmt(r1['value'])} | {fmt(r1['value_canonical'])} ratio | suggestive | {ci_str(r1)}, n = {fmt(n1['value'])}, p < {fmt(v1['value'])} |
| E2 | {r2['qid']} | D2 | {r2['locator']} | recall@10 | {fmt(r2['value'])} | {fmt(r2['value_canonical'])} ratio | contested | 与 E1 冲突：相对差异超阈值且 CI 不重叠（见 numeric_conflicts.json）；条件差异假设：评价条件更严格 |
| E3 | {l1['qid']} | D1 | {l1['locator']} | latency | {fmt(l1['value'])} {l1['unit']} | {fmt(l1['value_canonical'])} {l1['unit_canonical']} | suggestive | 原文单位 ms；{ci_str(l1)} |
| E4 | {l2['qid']} | D2 | {l2['locator']} | latency | {fmt(l2['value'])} {l2['unit']} | {fmt(l2['value_canonical'])} {l2['unit_canonical']} | suggestive | 原文单位 s；与 E3 归一化后方可比较 |
| E5 | {p3['qid']} | D3 | {p3['locator']} | precision | {fmt(p3['value'])} | {fmt(p3['value_canonical'])} ratio | suggestive | abstract_only，单源，不得称"平均提升" |
| E6 | {m3['qid']} | D3 | {m3['locator']} | rmse | {fmt(m3['value'])} | —（unnormalized） | suggestive | 无单位且无默认量纲，不参与跨文献比较 |
"""
    write(os.path.join(work, "evidence_table.md"), table)

    draft = f"""# 蒸馏学生模型能否兼顾召回率与延迟：综述草稿（simulated 示例）

## 主题一：蒸馏学生模型召回率的跨研究分歧
D1 报告蒸馏学生模型 recall@10 为 {fmt(r1['value'])}（{ci_str(r1)}，n = {fmt(n1['value'])}，p < {fmt(v1['value'])}）。[E1]
D2 在同一合成基准上报告 recall@10 为 {fmt(r2['value'])}（{ci_str(r2)}）。[E2]
两篇文献同一指标的数值差异超过规则阈值且置信区间不重叠，构成数值冲突候选（见 numeric_conflicts.json），结论并列 contested，不取平均、不自动调和。

## 主题二：端侧延迟
D1 报告平均延迟 {fmt(l1['value'])} {l1['unit']}（归一化后为 {fmt(l1['value_canonical'])} {l1['unit_canonical']}）。[E3]
D2 报告平均延迟 {fmt(l2['value'])} {l2['unit']}。[E4]
两处原始单位不一致（ms 与 s），经 units.json 归一化后方可比较；归一化后差异未超过规则阈值。
[推断] 现有两项证据提示蒸馏学生模型的延迟处于同一量级，但均来自合成基准，外推需谨慎。

## 主题三：单源指标与不可比数值
D3（仅摘要）报告 precision 为 {fmt(p3['value'] * 100)}%（即 {fmt(p3['value'])}），属单源证据，不得表述为"平均提升"或总体效应。[E5]
D3 另报告 RMSE 为 {fmt(m3['value'])}，因缺少单位且无默认量纲，已标记 unnormalized，不参与跨文献比较。[E6]

## 研究空白
[证据缺口] 真实生产流量上的召回率—延迟联合报告：现有文献均使用合成基准（已查 D1–D4）。

## 不确定性
- D3 仅摘要可用，数值证据强度不超过 suggestive。
- D4 为 D1 的近重复，仅作重复版本记录，其数值不作为独立证据参与冲突检测。
"""
    write(os.path.join(work, "review_draft.md"), draft)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/qes-demo")
    cdir = make_case(root)
    work, out = os.path.join(root, "work"), os.path.join(root, "output")

    print("=== 阶段 0：init（解析 + 数值抽取 + 归一化 + 冲突检测）===")
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "init",
         "--case", os.path.join(cdir, "case.json"), "--task", os.path.join(cdir, "task.md"),
         "--input-dir", cdir, "--work", work, "--out", out])

    norm_rows = load_jsonl(os.path.join(work, "quant_normalized.jsonl"))
    by_dim, unnorm = {}, 0
    for r in norm_rows:
        if r.get("norm_status") == "ok":
            by_dim[r["dimension"]] = by_dim.get(r["dimension"], 0) + 1
        else:
            unnorm += 1
    print(f"\n数值候选: {len(norm_rows)} 个 | 归一化: {len(norm_rows) - unnorm}"
          f"（{by_dim}） | unnormalized: {unnorm}")
    conf = json.load(open(os.path.join(work, "numeric_conflicts.json"), encoding="utf-8"))
    print(f"跨文献比较: {conf['compared_pairs']} 对 | 冲突候选: {conf['conflict_count']} 对"
          f" | 近重复跳过候选: {conf['skipped_duplicate_candidates']} 个")
    for c in conf["conflicts"]:
        print(f"  冲突 {c['conflict_id']}: {c['metric']} — "
              f"{c['a']['doc_id']} {fmt(c['a']['value_canonical'])} vs "
              f"{c['b']['doc_id']} {fmt(c['b']['value_canonical'])} "
              f"({c['a']['unit_canonical']}), rel_diff={c['rel_diff']:.1%}, "
              f"ci_overlap={c['ci_overlap']}, reasons={c['reasons']}")

    print("\n=== 模型阶段（simulated）===")
    simulate_model_outputs(root)
    print("已写入模拟模型产物：themes.json / screening_log.json / "
          "evidence_table.md / review_draft.md（数字全部程序化取自 quant candidates）")

    print("\n=== verify（数字回链门控）===")
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "verify", "--work", work, "--out", out])

    print("\n=== finalize（组装 result.json）===")
    run([sys.executable, os.path.join(SCRIPTS, "run_case.py"), "finalize", "--work", work, "--out", out])

    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    print("\n=== 示例完成（SYNTHETIC）===")
    print("status:", result.get("status"),
          "| 契约字段:", len([k for k in result if k not in ()]),
          "| 冲突对:", len(result.get("numeric_conflicts", [])),
          "| uncertainties:", len(result.get("uncertainties", [])))
    print("产物目录:", out)


if __name__ == "__main__":
    main()
