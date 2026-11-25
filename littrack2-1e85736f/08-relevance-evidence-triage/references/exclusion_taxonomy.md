# 排除原因分类法（exclusion taxonomy）

每条 excluded 记录必须且只能有一个主类别，并附 `category_evidence`（触发的规则
或命中词）。类别分两档：**预筛档**（确定性规则，stage=prefilter）与
**打分档**（rubric 阶段，stage=screening）。

## 1. 预筛档（确定性规则）

| 类别 | 触发规则 | 说明 |
|---|---|---|
| `language` | 语言不在白名单 | 语言缺失（unknown）**不**进此类，而是放行打标 `language_unknown` |
| `non_research_type` | 文献类型在排除清单 | 如 editorial / news / correction / letter / review / book-chapter |
| `out_of_window` | 发表日期在窗口外 | 日期缺失**不**进此类，放行打标 `date_unknown` |
| `blocked_term` | 标题命中明显无关词表 | 词表来自 `prefilter.blocklist_title_terms` |

## 2. 打分档（rubric 阶段）

| 类别 | 触发 | 说明 |
|---|---|---|
| `wrong_population` | 负向对象维度命中 | 研究对象不匹配（儿童/动物/其他病种等） |
| `wrong_method` | 负向方法维度命中 | 干预/方法不匹配（药物、膳食等非目标方法） |
| `wrong_outcome` | 负向结局维度命中 | 主要结局不匹配 |
| `duplicate_of_kept` | 规范化标题与被保留条目相同 | 仅作去向标注，保留来源优先级高者 |
| `off_topic_low_score` | 无负向命中但总分低于带下界 | 兜底类别；此类条目多为主题偏离 |

## 3. 非排除去向（不属于本分类法）

- `included`：高于边界带上界；
- `needs_human_review`：落在边界带内，**不是排除**，单独列出并进入
  `prisma_flow.needs_human_review`。

## 4. 优先级与一致性规则

1. 预筛档先于打分档：预筛已排除的条目不再打分（决策表 `score=null`）。
2. `duplicate_of_kept` 优先于其他打分类别（先标重复，再看负向维度）。
3. 多个负向维度同时命中时，按 `category_map` 中维度的遍历顺序取第一个，
   其余命中词仍保留在 `score_entries` 中供复核。
4. 每个类别的计数必须能回算到 `screening_decisions.jsonl` 的具体条目；
   `prisma_flow.*_by_category` 只是聚合视图。
5. 新增类别时必须：写入本文件、写入 case 的 rubric 配置、保证下游
   `omission_notes` 与 `exclusions_by_category` 同步覆盖。
