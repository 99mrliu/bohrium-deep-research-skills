---
name: crossdb-identity-merge
description: 跨库论文身份解析与版本合并：把同一工作的预印本、会议版、期刊版、增补版合并为干净清单，识别同名不同文/同文不同名，并保留逐簇合并证据。当任务的输入是多来源文献记录（Crossref/EuropePMC/出版方/本地导出）且要求去重、身份对齐、可复核的合并依据时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约。
---

# 跨库身份解析与版本合并（crossdb-identity-merge）

## 用途与适用条件

对多来源文献记录做**不预去重的全量摄入**，然后用确定性规则决定哪些记录是同一工作：合并预印本/会议版/期刊版/增补版，识别"同名不同文"（标题相同作者不相交）与"同文不同名"（标题措辞差异但硬标识一致），输出可直接放进综述的干净清单＋逐簇合并证据账簿＋待人工裁定队列。

不适用：引文边追踪（方向 1）、关联发现（方向 2）。本 Skill 只解决"谁是谁"，可叠加在任何追踪流程之后做清单清洗。

## 输入

- `/input/case.json`：含 `case_id`、`output_contract`；案例材料中的文献记录文件。
- 本地记录：`.json/.jsonl/.csv/.tsv`，自动发现于 `/input`、`./environment`、`/app/work`、当前目录；Crossref、EuropePMC、OpenAlex、Semantic Scholar 等异构格式自动识别。

## 调用方式

```bash
# 1. 合并
python3 scripts/identity_merge.py --case /input/case.json --out /app/output --workdir /app/work
# 2. 自查（必须；失败项写入 result.json 的 uncertainty）
python3 scripts/verify_merge.py /app/output /app/work
```

可选参数：`--review-threshold`（进入人工队列的标题相似度，默认 0.80）、`--roots` 追加语料目录。

## 输出（/app/output）

- `result.json`：`case_id`、`status`、`clean_works`（每簇：canonical、版本集合、全部 DOI/arXiv/外部标识、成员及定位、字段冲突）、`review_queue`（疑似对＋证据＋待裁定原因）、`conflicts`、`stats`（摄入数/簇数/去重数/待审数）、`sources`、`uncertainty`，镜像 `output_contract` 全字段。
- `merge_ledger.json`：逐簇合并账簿（合并决策、逐对证据、canonical 选择规则、成员保留清单）。
- `merge_table.md`：人读合并表。日志 `/app/work/run_log.json`，自查 `/app/work/verify_report.json`。

## 关键方法（详见 rules/dedup_keys.md）

1. **分块（blocking）**：DOI、arXiv、标题指纹、首末主题词、第一作者姓＋年份五路分块，只在块内做成对比较，控制比较规模。
2. **三级决策**：AUTO_MERGE（硬标识一致，或标题指纹一致＋年份差≤1＋作者重叠，或标题 Jaccard≥0.90＋第一作者相同＋年份差≤2）；REVIEW（高相似但 DOI 冲突、或同题但作者不相交——进入人工队列，**绝不自动合并**）；其余 KEEP_SEPARATE。
3. **版本分类与 canonical 选择**：按 Crossref type/venue/标识形态判定 preprint/conference/journal/supplement/dataset；canonical 取 期刊版＞会议版＞预印本，同级取字段最全者；被合并成员的标识全部并入 `all_doi/all_arxiv/all_ext_ids`，原始记录与定位全部保留。
4. **冲突保留**：簇内年份、标题、卷期差异写入 `field_conflicts`，不静默覆盖。

## 异常处理

| 情况 | 处置 |
|-|-|
| 同名不同文（标题一致、作者不相交） | 进 review_queue，不合并 |
| 同文不同名（DOI/arXiv 一致、标题不同） | AUTO_MERGE，标题差异记入 field_conflicts |
| DOI 冲突（高相似标题、不同 DOI） | 进 review_queue 并给出双方标识与定位 |
| 缺标题/缺作者的残记录 | 只靠硬标识参与合并；无硬标识则保持单例并计数 |
| 撤稿/更正记录 | 版本分类保留原 type；在 uncertainty 提示人工核验，不做主观删除 |
| 无任何记录 | status=partial，clean_works=[]，如实说明 |

## 自查方法

`verify_merge.py` 检查：记录无丢失无重复、簇间硬标识唯一（不漏并）、待审对未被自动合并、canonical 属于本簇、定位文件存在、统计自洽。失败项写入 `uncertainty` 后方可交付。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成数据，**非正式案例结果**）。
