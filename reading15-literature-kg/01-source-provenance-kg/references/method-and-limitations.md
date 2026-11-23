# 方法说明与已知限制

## 1. 方法总览

流水线五步，模型只负责语义抽取，其余全部机械化、确定性：

```
/input ──normalize──> normalized_corpus.json ──┐
模型语义抽取 ──> candidate_extraction.json ────┴─verify──> verify_report.json
                                                       └─build──> graph.json(.jsonl)
case.json(query_specs) ──────────────────────────query──> queries.json
                                                       └─assemble──> result.json + ledger + 预览
```

设计要点：

1. **职责分离**：凡可机械判定的（引文子串、地址存在性、来源归属、
   canonical_key 一致性、数值一致性、覆盖度）全部交给脚本；
   模型只做语义判断（识别实体、关系、合并候选）。这使“语料真实性”
   成为可执行的不变量，而非文档层面的愿望。
2. **确定性**：所有 JSON 输出 sort_keys、排序遍历、BFS 邻接升序。
   同一输入重跑逐字节一致，差异即信号。
3. **诚实部分结果**：验证失败不阻断装配；result.json 照常生成，
   `status` / ledger.honest_partial 如实标记 partial，错误清单入台账。
4. **不臆造分数**：图谱统计只有计数（节点数、边数、覆盖段落数），
   没有“置信度”“质量分”。覆盖度是披露指标而非奖励信号。

## 2. 查询执行器语义

- `neighborhood(node, hops)`：无向 BFS，返回 hops 层内节点与内部边，
  结果子图含每个节点/边的完整证据列表；
- `by-type(kind[, source_id])`：按类型过滤，`source_id` 进一步限定
  “证据覆盖该来源”的节点——用于按来源切片（例如只看 secondary 的样品）；
- `path(from, to)`：无向 BFS 最短路径，邻接按 node_id 升序、并行边按
  edge_id 升序，路径长度与组成完全确定；不可达时返回空子图并注明。

结果子图是自包含的：审阅者不需要回查全图即可核验每条证据。

## 3. 合并纪律的判定边界

- merge 的**允许条件**（机械）：canonical_key 完全一致、跨 ≥2 来源、
  member 数值一致（若有）；
- merge 的**语义上限**（文档约束，模型须遵守）：合并只断言“同一概念”，
  不断言相同样本/条件/数值；
- nonmerge 的**触发条件**（机械）：归一化后同 label 的未合并节点对必须
  有显式 nonmerge；不同名的物理对象区分（如 AL-P1 vs AL-S1）依赖模型
  主动记录，脚本无法穷举语义——这是已知边界，靠 merge 纪律文档约束。

## 4. 已知限制

1. **引文精确 ≠ 语义正确**：脚本保证引文确实出自所指地址，但不能判断
   模型对引文的语义解读是否正确（例如把背景句当作结论句）。
   缓解：把“结论性”对象（metric/claim）的引文要求落在含数值/主张的句子上，
   由 nonmerge/conflict 机制暴露不一致。
2. **同名检测是浅层的**：label 归一化仅做大小写与空白折叠，
   不处理同义词（porosity vs void fraction）。同义异形实体的 merge/nonmerge
   需要模型在 canonical_key 层面负责。
3. **旁挂 XML 不解析**：secondary-publisher.xml 只登记存在性与 SHA-256；
   若赛题要求利用其中元数据，需要另行扩展归一化器（保持只读登记原则）。
4. **预览布局简单**：SVG 为按 kind 分层的网格布局，不模拟力导向；
   仅用于人读核验，不作为结构分析依据。
5. **路径查询为无向最短路径**：不区分边类型权重；需要语义路径时应按
   by-type 切片后再查。
6. **单 primary 假设**：根元数据归属规则按“一个 primary + 若干 secondary”
   设计；多 primary 场景需扩展 role 模型。

## 5. 与赛题规则的对应关系

| 赛题要求 | 本技能机制 |
| --- | --- |
| 根元数据只属于 primary | B1/B2 校验（paper 节点 attributes 与来源 article-meta 逐字符一致） |
| 每个实质性节点/边需 source_id+段落地址+短引文 | A 组校验（三字段齐备、子串匹配、长度上限） |
| 无 PDF 页码、禁止自造页码充当原文 | 地址模型只接受 (source_id, paragraph_id)；页码式引文无法通过子串校验 |
| 内联公式线性化 | 语料 schema 要求 text 为纯文本；非文本段落被归一化器丢弃并告警 |
| ≥3 条真实执行的查询（结果子图+证据） | query_graph 批量执行，queries.json 自包含证据 |
| 跨论文 merge 与显式 nonmerge | D 组校验（跨来源、canonical_key、数值一致、同名节点对强制判决） |
| 条件/样本/数值不并入单一结论 | D4 拒绝数值不一致的 merge；nonmerge/conflict 原样保留 |
| 冲突/未报告保留 | E 组校验（resolution=preserved）+ unreported 结构 |
| 全量建图（provenance 中心但不能只建溯源） | 节点/边/合并/冲突/查询全链路；覆盖度报告披露遗漏段落 |
| output_contract 精确镜像、诚实缺失 | 装配器按键集合填充，未知键置 null 并记台账，绝不省略 |
