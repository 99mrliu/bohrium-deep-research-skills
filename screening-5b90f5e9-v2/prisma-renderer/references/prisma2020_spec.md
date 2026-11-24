# PRISMA 2020 流程要点与渲染闭合门

## 流程骨架（本技能实现的子集）

```
Identification ── Records identified from databases (n) ── Duplicates removed (n)
Screening      ── Records screened (n) ── Records excluded (n, 按理由分解)
Included       ── Studies included (n) ── Awaiting human confirmation (n)
```

题录阶段的 PRISMA 2020 完整版还含全文获取与全文排除环节；本技能只渲染
题录层面（案例范围即标题摘要筛选），全文环节存在时按同一模式扩展
counts 键并在报告注明口径，不虚构全文数据。

## 渲染前闭合门（不闭合禁止出图）

| 门 | 等式 |
|---|---|
| R1 | identified − duplicates_removed = screened |
| R2 | screened = excluded + included + needs_human |
| R3 | exclusion_reasons 合计 = excluded（给出分解时） |
| R4 | 生成的 SVG 必须 well-formed（xml.dom.minidom 解析） |

R1–R3 任一 FAIL → exit 3，只输出 render_check.json，不产出图形。
原则：**宁可没有图，不能有对不上的图**——审稿人对流程图的信任
来自每个数字都能与台账对账。

## needs_human 的画法

待人工确认的记录不算 included 也不算 excluded，在 Included 盒内单列
"Awaiting human confirmation (n=...)"，避免把它们静默并入任一侧——
这是本图与"漂亮但误导"版本的关键差别。

## Mermaid 与 SVG 双轨

- SVG：交付级图形，确定性布局，同输入同字节，可直接嵌入文档；
- Mermaid（flow.md）：Markdown 报告内嵌用，便于评审者在 GitHub/文档
  平台直接查看；两者由同一份 counts 生成，数字永远一致。
