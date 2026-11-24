# 选题评估决策备忘录（decision memo）模板

> 用途：模型阶段结束后，由 `appraise.py` 按本结构程序化渲染 `out/decision_memo.md`；
> 模型若需补充手写判断，只允许在第 4 节追加，且必须标注 [模型判断]。
> 全文禁止"有待进一步研究"式无绑定表述（见 rules/gap_evidence_binding.md）。

- case_id：{case_id}
- 研究问题：{research_question}
- 候选选题来源：{case_extras | topics_md_fallback}
- 可用文献：{n} 篇；登记空白：{n_gaps} 条（single_source / unresolved_conflict / facet_absent）
- 权重：novelty 0.45 / sufficiency 0.30 / fit 0.25（无约束时 0.6/0.4 归一）

## 1. 结论一览

| 选题 | 新颖度 | 充分度 | 约束契合 | 加权总分 | 推荐档位 |
| --- | --- | --- | --- | --- | --- |
| {topic} | {novelty} | {sufficiency} | {fit|null} | {total} | **{strong|conditional|not_recommended}** |

## 2. 逐题评估理由

### {topic} — {recommendation}（{weighted_total}）
- 理由：{rationale：支持文献 x/N、相关文献构成、约束满足情况}
- 选题 signature：{facet 命中清单}
- 支持文献：{supporting_docs}；相关文献：{related_docs}
- 约束「{constraint}」→ {satisfied|unverifiable|violated}（{detail}）

## 3. 绑定空白清单

- {topic} → {gap_id 清单}（每条空白的 docs_checked 与 binding_evidence 见 gap_register.json）
- 未绑定任何空白的选题在此显式列出并说明风险。

## 4. 边界与不确定性

- 新颖度仅在当前语料内有界成立；语料外是否空白需另行查证，本备忘录不外推。
- 约束核查中 unverifiable 的条目逐条列出，不计为满足。
- 降级文献（abstract_only）、粗聚类 theme 等异常在此复述（与 result.json
  uncertainties 一致）。
