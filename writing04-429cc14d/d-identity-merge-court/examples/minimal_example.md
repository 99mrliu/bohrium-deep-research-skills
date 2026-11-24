# 最小调用示例（全虚构合成数据）

**合成声明**：本目录所有数据均为编造——人名、刊名、DOI（10.55555/* 为保留测试段）、
arXiv 号、PMID 均不指向任何真实文献，仅用于演示脚本行为。

`examples/output/` 中的每个文件都是下列命令的**真实运行产物**（非手工编写）。

## 输入设计（examples/input/records.jsonl，21 条虚构记录）

> 说明：任务书枚举的 7 个应并场景（①–⑦，其中⑦与①同组）加 3 个陷阱共 10 个候选组；
> 记录数由场景枚举决定（21 条），决策数为 10（7 merge + 2 keep_separate + 1 human_queue）。

应并重复（7 组 → merge）：

| 组 | 成员 | 场景 |
|---|---|---|
| G001 | R001/R002/R003 | ①+⑦ 同一文献的三个数据库导出：DOI 大小写差异、PubMed 多 PMID、Scopus 缺页码且 DOI 在 url 字段 |
| G002 | R004/R005 | ② 同题名仅大小写+冒号差异，无 DOI，作者/年/容器三重佐证 |
| G003 | R006/R007 | ③ 题名微变（正式版多副标题 "a review"）+ 同作者同年同容器同卷，Jaccard=0.889 |
| G004 | R008/R009 | ④ arXiv 预印本 vs 正式版：同题名同作者，年正式版晚一年，材料内 note 写明关系与正式版 DOI |
| G005 | R010/R011 | ⑤ 中英题名对：translation_of 字段线索 + 共享 DOI（大小写差异） |
| G006 | R012/R013 | ⑥ CNKI vs Crossref：同 DOI 不同大小写、页码连字符样式差异、中英刊名 |
| G007 | R014/R015 | EndNote 导出 DOI 内嵌 url 字段 vs 显式 doi 字段，规范化后相同 |

陷阱（2 keep_separate + 1 human_queue）：

| 组 | 成员 | 场景 | 预期裁决 |
|---|---|---|---|
| G008 | R016/R017 | 同姓（Zhang Wei vs Zhang Lei）同年 2024、题名一词之差（flow vs speed），容器/卷页/DOI 全异 | M5 → keep_separate |
| G009 | R018/R019 | 同规范化 DOI 但年份 2021 vs 2022、页码 77–88 vs 177–188 冲突 | M2 → human_queue（禁止自动并） |
| G010 | R020/R021 | 短通用题名撞车 "Digital twins in manufacturing"，作者/年/容器/DOI 全异 | M3 → keep_separate |

## 全流程命令与预期（仓库根目录执行）

```bash
# 1. 候选挖掘（退出码 0）
python3 scripts/dedup_candidates.py --records examples/input/records.jsonl --out examples/output
# 预期：21 条记录 → 10 个候选组，分级 G001/G004/G005/G006/G007/G009=strong，
#       G002/G003=moderate，G008/G010=weak；解析警告 2 条。

# 2. 裁决校验与施加（退出码 0）
python3 scripts/merge_adjudicate.py --candidates examples/output/candidates.json \
  --records examples/input/records.jsonl --decisions examples/input/decisions.json --out examples/output
# 预期：merge=7 keep_separate=2 human_queue=1，记录 21→13，
#       重定向 8 条（G001 吸收 2 条，其余 6 组各 1 条）。

# 3. 引用重定向复核（预期退出码 1——演示残留检出）
python3 scripts/redirect_check.py --manuscript examples/input/manuscript.txt \
  --redirect_map examples/output/redirect_map.json --out examples/output
# 预期：检出 1 处残留——第 17 行 chen2024neuralpm 应重定向到 chen2024neural。

# 4. booby-trap：错误裁决必须被拒（退出码 1，且不写任何产物）
python3 scripts/merge_adjudicate.py --candidates examples/output/candidates.json \
  --records examples/input/records.jsonl --decisions examples/input/decisions_bad.json --out /tmp/bad
# 预期输出（stderr，真实捕获见 examples/output/decisions_bad_rejection.log）：
#   裁决校验失败（未写任何产物）：
#     - G009: [M2] 共享规范化 DOI(10.55555/abl.2021.033) 但书目坐标冲突 ['pages', 'year']，
#       必须 human_queue，禁止 merge
```

## 产物目检要点（examples/output/）

- `candidates.json`：10 组，每组含信号明细与逐字段冲突表；G001 带 ">2 条组"两两证据提示。
- `merged_records.jsonl`：13 条；canonical R009 含 `lineage`（preprint_arxiv=2401.98765、
  relation=published_version_of、redirect="R008 -> R009"、evidence=材料内 note 声明），
  且自动补齐了 arxiv 与 version 字段；R011/R013 的中英题名/刊名差异进入
  `merge_exceptions`（不阻断合并，留作人工抽查）。
- `redirect_map.json`：8 条 record 级 + 8 条 cite_key 级重定向；G008/G009/G010 不出现。
- `merge_report.md`：10 节逐案 rationale（成员、证据分级、理由、冲突表、谱系、未决跟进）。
- `residual_report.json/md`：1 处残留（演示用途，故意保留）。
- `decisions_bad_rejection.log`：decisions_bad.json 被 M2 拒绝的真实 stderr（退出码 1，
  /tmp/bad 目录未生成任何文件——原子性）。

## 已验证的额外拒绝路径（自测，不在 output 中留档）

- G008（M5）判 merge → 拒绝；G010（M3 weak）判 merge → 拒绝；
- G004 以预印本 R008 为 canonical（M4）→ 拒绝；
- canonical 非组成员、reason 为空、候选组漏判 → 均拒绝（退出码 1）。
