# 端到端示例解读（示例，非正式案例结果）

> 本文件使用 examples/fixtures/ 下的**虚构**夹具演示全管线（illustrative only）。
> 数据不构成任何真实案例答案。同样的步骤即 scripts/selfcheck.py 的自动断言。

## 0. 夹具

| 文件 | 内容（虚构） |
| --- | --- |
| records_patents.json | 2 件同族专利（family_id=FAM-ILLUS-001，公开号 XX1000001A1 / XX1000002B1） |
| records_npl.jsonl | 2 篇论文：一篇切题（缺"应用对象"表述）、一篇焊接综述（不相关） |
| notes_unclassified.txt | 无任何书目字段的说明文字 |
| query_spec_valid.json | 3 概念块（过程与设备 / 核心技术手段 / 应用对象）+ C12M 1/00 + 2015-2026 |
| query_spec_bad_no_intent.json / query_spec_bad_bare_not.json | 负例：R6 / R4 |
| case_illustrative.json | 虚构 case.json（含 output_contract） |

## 1. build：构造并校验检索式

```bash
python3 scripts/build_query.py build --spec examples/fixtures/query_spec_valid.json --out query.json
```

输出布尔式：
`(fermentation OR reactor) AND (membrane aeration OR aeration) AND (microbial OR cell culture)  [分面] IPC/CPC=(C12M 1/00) AND 年份=2015-2026`

负例验证：
`query_spec_bad_no_intent.json` → exit 2，打印 `[R6] ...词项缺 intent`；
`query_spec_bad_bare_not.json` → exit 2，打印 `[R4] ...裸 NOT`。

## 2. search：双轨执行

```bash
python3 scripts/search_corpus.py --query query.json --corpus <夹具目录> --out hits.json
```

关键结果：

- `corpus.records_total = 5`；`tracks = {patent: 2, npl: 2, unclassified: 1}`——
  专利凭公开号/kind code/IPC/权利要求入专利轨，论文凭 DOI/期刊/作者入 NPL 轨，
  说明文字无信号 → unclassified 并原样列出。
- 两件专利 family_id 相同 → **同族去重合并 1 条**（dedup.duplicates_removed=1），
  保留记录的 `duplicates` 里可追溯被合并条目的 file#loc。
- 切题论文命中 2 个块；焊接论文零命中，不入池。
- 每条命中带 `file` + `loc`（如 `$.records[0]`、`line 1`）与
  `blocks_matched`（哪个块、哪个字段、哪个词项）。

## 3. screen：PRISMA 筛选 + 排序

```bash
python3 scripts/screen_rank.py --query query.json --hits hits.json --out screening.json
```

- 默认查准阈值 = 3（语料中 3 个块都至少命中过一次）。
- 专利：3/3 块 + 分类号 C12M 1/00 重合 + 权利要求命中 → **include**（I1+I2+I3）。
- 论文：2/3 块，缺"应用对象" → **exclude E7**（理由写明缺少的块）。
- PRISMA：identified=5, duplicates_removed=1, screened=2, excluded=1, included=1，
  满足 screened = included + excluded（脚本重算；若 --expect 自报不符 → exit 3）。
- ranking 中专利 score 高于论文（块覆盖 40 vs 26.7，分类号重合 +15），分解四项齐全。
- omissions：zero_hit_blocks=[]、unclassified_records=[说明文字]、
  skipped_files=[]、notes（外部库未检索/法律状态未核验等）。

## 4. scaffold：生成 result.json

```bash
python3 scripts/scaffold_result.py --case examples/fixtures/case_illustrative.json \
    --query query.json --hits hits.json --screening screening.json --out result.json
```

- `case_id = "illustrative-demo-000"`；output_contract 的 8 个字段全部存在（镜像）。
- status=**partial**：存在 1 条无法判定记录（诚实减损，不粉饰为 ok）。
- uncertainty 含"法律状态未核验""仅本地语料，外部库未检索"等声明。

## 5. 号码模式（降级路线演示）

`mode=number_lookup`、单块、词项 `XX1000002`（不带 kind code）→
命中 `XX1000002B1`（kind code 双向容忍）。此模式不做主题相关性判断，
局限必须写入 uncertainty（见 SKILL.md"案例路由"）。
