# 规则：筛选与排序协议（PRISMA 留痕 + 可解释排序）

## 1. 两阶段

- **查全阶段**（search_corpus.py）：宽式召回——任一概念块命中、或 classification
  分面命中即入池；记录召回数（去重前后）与零命中块。
- **查准阶段**（screen_rank.py）：逐条纳入/排除。默认阈值 = 语料中至少命中过一次的
  概念块数（避免零结果块误杀全部候选）；可用 `--min-blocks N` 收紧。纳入条件：
  命中块数 ≥ 阈值，或（分类号分面命中且至少 1 个关键词块命中）。

## 2. 纳排理由代码表

排除（E，必须给码）：

| 代码 | 含义 |
| --- | --- |
| E1 | 主题不相关（命中为偶然共现） |
| E2 | 文献类型不符（非目标轨道/非技术文献） |
| E3 | 重复或同族冗余 |
| E4 | 时间范围外 |
| E5 | 语言或全文不可读 |
| E6 | 信息不足无法判断 |
| E7 | 概念块覆盖不足（查准阶段未达阈值） |

纳入（I，必须给码 + rationale 相关性依据）：

| 代码 | 含义 |
| --- | --- |
| I1 | 覆盖阈值以上概念块 |
| I2 | 分类号与检索式分面重合 |
| I3 | 关键字段命中（权利要求/标题） |
| I4 | 号码精确匹配 |

人工覆写（`--decisions override.json`，键为 `file#loc`）同样受代码表约束：
排除无 E 码、纳入无 I 码或无 rationale → exit 2。

## 3. PRISMA 计数口径

| 计数 | 口径（screen_rank.py 从数据重算） |
| --- | --- |
| identified | 语料中解析出的记录总数（含 unclassified） |
| duplicates_removed | 去重合并掉的记录数（同族/DOI/标题） |
| screened | 查全阶段入池且去重后的候选数 |
| excluded | 查准阶段排除数（每条有 E 码） |
| included | 查准阶段纳入数（每条有 I 码 + 依据） |

恒等式：screened = included + excluded。自报数（`--expect`）与重算不一致 → exit 3，
以重算为准。

## 4. 排序特征定义（满分 100）

| 特征 | 上限 | 定义 |
| --- | --- | --- |
| block_coverage | 40 | 40 × 命中块数/总块数（主题覆盖度） |
| field_strength | 30 | 命中字段权重取最大：claims 30 / title 25 / abstract 20 / description、IPC/CPC 15 / applicant、_text 10；分类号分面命中再 +5 |
| class_overlap | 15 | IPC/CPC 与 classification 分面前缀重合（规范化后）即得 |
| year_proximity | 15 | 在 year_range 内 15；界外 ±2 年 8；无年份分面或年份未知给中性 5；其余 0 |

每条候选输出 score 与四项分解，按 score 降序。分数是**可解释的相对排序依据**，
不是绝对相关性概率；写作时引用分解而非裸分。

## 5. 遗漏说明（omission statement）必须包含

- 零命中概念块（zero_hit_blocks）及原因判断；
- 无法判定轨道的记录清单（unclassified_records）；
- 被跳过的文件（skipped_files：任务文件、解析失败、管线产物）；
- 来源边界：仅本地语料、未检索外部数据库；同族合并仅信语料内字段；
  法律状态未核验。
