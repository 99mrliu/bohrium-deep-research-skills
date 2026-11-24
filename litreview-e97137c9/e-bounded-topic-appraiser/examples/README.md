# 合成示例（SYNTHETIC EXAMPLE）

本目录提供 **合成示例**：所有文献、主题、论断均为程序生成的虚构内容（模拟模型产物
一律标注 `simulated`），仅用于端到端演示 bounded-topic-appraiser 的机制，
不构成任何正式案例结果。

## 运行

```bash
python3 examples/make_example.py /tmp/bta-demo
```

## 示例设计

- 语料：5 篇虚构短文（`/tmp/bta-demo/case/*.txt`）——
  - D1 / D2：两篇结论**相反**的成人益生菌 RCT（n=120 阳性 vs n=80 阴性）→ 制造
    一对方向冲突论断（unresolved_conflict）；
  - D3：仅摘要（abstract_only）的体外细胞系抗炎筛选 → 制造 single_source theme；
  - D4 / D5：老年人单臂试验、儿童队列研究 → 拉开 facet 覆盖；
  - facet 词表中的"孕妇"等值全语料 0 覆盖 → 制造 facet_absent 空白。
- case.json 提供 3 个候选选题与 2 条约束（"仅限体内研究（in vivo）"、"样本量≥50"）。
- 流程：`init`（真实解析 + facet 打标）→ 写入模拟 themes/claims/topics →
  `gaps` → `appraise` → `finalize`，全部为真实脚本执行。

## 查看点

- `/tmp/bta-demo/work/case_extras.json`：从 case.json 探测出的候选选题与约束。
- `/tmp/bta-demo/work/facet_matrix.json`：每篇 facet、underpowered/absent facet、
  theme 覆盖缺口。
- `/tmp/bta-demo/work/gap_register.json`：每条空白的 docs_checked 与 binding_evidence。
- `/tmp/bta-demo/output/appraisal_matrix.json`：三个选题得分应拉开梯度——
  孕妇体内 RCT 选题（strong）＞ 成人 RCT 综合（conditional）＞ 体外机制选题
  （not_recommended，违反"仅限体内"约束且证据底座仅一篇摘要）。
- `/tmp/bta-demo/output/decision_memo.md`：决策备忘录。
- `/tmp/bta-demo/output/result.json`：`research_product.decision_memo` 内嵌备忘录全文。
