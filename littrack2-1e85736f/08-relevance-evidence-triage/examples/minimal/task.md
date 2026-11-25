# 任务：相关性分级筛选与依据装订（合成示例 case-1e85736f-syn-008）

> 本任务与全部材料均为 **synthetic（合成）** 数据，仅用于演示与自检，不对应任何真实文献。

## 研究问题
In adults with type 2 diabetes, does high-intensity interval training (HIIT) improve
glycemic control (e.g., HbA1c, fasting glucose) compared with moderate continuous
training or usual care?

## 要求
1. 读取 `case.json` 与 `materials/` 下三个来源快照（Crossref / Europe PMC / arXiv 布局，均为合成）。
2. 运行双阶段筛选：
   - 预筛（确定性规则）：语言、文献类型、窗口内日期（2024-01-01 ~ 2024-12-31）、明显无关词表；
   - rubric 打分：按 `screening_rubric` 逐维度透明加减分，threshold=6、delta=1，
     分数落入阈值±δ 边界带的条目标记 `needs_human_review`，不强行二分。
3. 为每条 included / needs_human_review 条目从 title/abstract 原文装订逐字证据
   （quote + field + char offsets），只能从脚本切出的候选片段中选择。
4. 输出 PRISMA 式流转计数（identified→prefiltered→screened→included），
   排除条目给出分类（wrong_population / wrong_method / wrong_outcome /
   duplicate_of_kept / out_of_window / non_research_type / language 等）。
5. 写遗漏说明：未抽审的预筛排除类别、摘要缺失只能按标题判断的条目。
6. 最终写 `output/result.json`，包含 `output_contract.required_fields` 全部字段。

## 埋点预期（自检用）
- 明确相关：crossref:10.0000/syn-metab-2024-001、europepmc:SYN000101、arxiv:SYN-ARXIV-2024-00201
- 缺摘要但标题强相关（title_only）：europepmc:SYN000104
- 边界带（needs_human_review）：europepmc:SYN000102、europepmc:SYN000103
- wrong_population：crossref:10.0000/syn-ped-2024-002
- wrong_method：europepmc:SYN000105
- wrong_outcome：arxiv:SYN-ARXIV-2024-00202
- duplicate_of_kept：arxiv:SYN-ARXIV-2024-00203（与 europepmc:SYN000101 同标题）
- out_of_window：crossref:10.0000/syn-old-2021-003
- non_research_type：crossref:10.0000/syn-edit-2024-004
- language：crossref:10.0000/syn-es-2024-005
