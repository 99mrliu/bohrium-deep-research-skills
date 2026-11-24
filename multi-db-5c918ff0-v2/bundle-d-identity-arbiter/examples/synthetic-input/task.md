# 任务：多数据库联合检索的论文身份去重（合成教学案例）

> SYNTHETIC teaching data — 本案例全部实体均为虚构，仅用于演示 skill 行为。

对 `materials/` 下的离线材料执行论文身份去重判定与确定性合并：

1. 嗅探分类各材料（Crossref / EuropePMC / 出版方 / reference_graph / import_state），
   无法识别的形状一律隔离，不得强行解析。
2. 按分层规则判定重复：T1 标识符精确（含显式别名）、T2 书目精确、T3 模糊候选仅入仲裁队列。
3. 每个候选对输出一条可解释决策行（tier / decision / reason_code / evidence）。
4. 按来源优先级确定性合并，逐字段记录溯源与冲突。
5. 交付 `/app/output/result.json`：`case_id` + 全部 `output_contract` 字段，
   诚实的 `status` / `sources` / `uncertainty` / `change_records`。

本案例故意包含一对 T3 近似重复（rec 标题仅差单复数、年份差 1）：在不提供裁决文件时，
它**必须**停留在仲裁队列中，`status=partial` 是诚实且正确的结果。
