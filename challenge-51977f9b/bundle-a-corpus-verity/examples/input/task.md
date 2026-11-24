# 任务说明（合成示例 / synthetic, illustrative）

> 本任务文件为虚构的教学演示数据，不构成真实评测案例。

## 研究问题

GLP-1 受体激动剂对 2 型糖尿病患者心血管结局的影响：与安慰剂或常规治疗相比，
GLP-1 受体激动剂能否降低主要不良心血管事件（MACE）、心力衰竭住院与心血管死亡？

## 任务要求

1. 对随案例提供的题录清单（records.json）先建立**可信语料层**：逐条核验元数据
   真实性，识别伪造嫌疑、精确/近似重复与撤稿记录，全部隔离并给出机器可复核的理由。
2. 仅允许通过核验的题录进入后续筛选；按 PRISMA 口径报告 identified、
   duplicates_removed、quarantined、clean_for_screening 计数。
3. 走完系统综述完整链条（检索式 → 纳排 → 筛选 → 质量评价 → 综合），隔离清单的
   每条理由写入 result.json 的 evidence_matrix 与 uncertainty。
4. 最终交付 result.json，包含 case.json 中 output_contract 列出的全部字段。

## 材料

- records.json：10 条合成题录（全部虚构，含预埋的元数据缺陷，用于演示核验规则）。
