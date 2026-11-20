# xlang-version-reconciler

语言识别与跨语种版本归并 Skill：对跨语言检索得到的候选记录逐条判定正文语种（以实际文本为准）与版本类型（original / publisher-translation / abstract-only-english / bilingual / exact-duplicate / undetermined），把同一工作的多语版本归并为一个 work、按 work 去重计数，并让每条命中可回指其来源、DOI、版本与语种。对应赛题"跨语言文献检索"的**方向 B（语言识别与跨语种版本归并）**，位于检索后的记录解析阶段，与查询扩展、误译复核等方向完全解耦。

## 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：用途、输入输出、调用方式、异常处理、自查方法 |
| `rules/version_policy.md` | 判定优先级、文本优先原则、归并信号权重与阈值、冲突处理 |
| `scripts/langid_version.py` | 阶段 1：语言识别与版本类型判定（Python 3.8+，仅标准库） |
| `scripts/reconcile_works.py` | 阶段 2：跨语种同文归并、去重计数、result.json 组装 |
| `templates/result_fields.md` | result.json 字段契约 |
| `examples/example_walkthrough.md` | 合成数据最小示例（示意，非正式案例结果） |

## 依赖与环境

- Python ≥ 3.8，仅标准库；无第三方依赖、无网络依赖、完全离线可运行。
- 输入契约：`/input/case.json`（case_id、output_contract）＋候选记录文件（`.json/.jsonl/.csv/.tsv/.txt/.md`，自动发现于 `/input`、`/app/work`、当前目录）。PDF 材料先用平台 pdf-text-tool/ocr-tool 抽成文本。
- 输出契约：`/app/output/result.json`（镜像 output_contract 全字段）＋ `/app/work` 下的阶段报告、归并表与运行日志。

## 一次完整使用

```bash
python3 scripts/langid_version.py --roots /input,/app/work,. \
    --out /app/work/langid_report.json --workdir /app/work
python3 scripts/reconcile_works.py --report /app/work/langid_report.json \
    --roots /input,/app/work \
    --case /input/case.json --out /app/output --workdir /app/work
```

## 输入输出解释

- **输入记录**：每条候选记录至少含 DOI 或标题之一；正文（fulltext/body/text 等字段或整篇 .txt）、摘要、语言字段、出版方/期刊字段、译本/重复关系字段均可缺省，缺省只会降低置信，不会导致崩溃。
- **langid_report.json**：逐条给出 `body_language`（code/confidence/basis）、`version_type`、`evidence`（采样定位＋Unicode 区间统计＋功能词得分）、`conflicts`、`locator`。
- **reconcile_report.json / result.json**：work 组（含 version 视图列表）、merge 决策日志、rejected_candidates、三级计数对照（raw_records → distinct_versions → distinct_works）、orphans、sources、uncertainty。

## 方法概要

1. **语种判定**：非拉丁文字按 Unicode 区间定语种（假名→ja、谚文→ko、纯 CJK→zh、西里尔→ru、阿拉伯→ar）；拉丁文字按六语功能词命中计数判定，接近时用特征字符裁决（ã/õ→pt、ñ→es、ä/ö/ü/ß→de）。长正文按头/中/尾三段采样；CJK/假名/谚文字符信息密度高，fulltext 长度阈值按双倍折算。
2. **版本判定**：规则 R0–R6 按优先级触发（见 rules/version_policy.md）；文本优先于元数据标签，冲突必记录；证据不足一律 `undetermined`。
3. **归并**：DOI 关系、标题折叠相似度、作者姓氏折叠序列、年/卷/期/页指纹构成加性打分；≥0.75 归并、0.55–0.75 保持分列并公示、显式 exact-duplicate 直接吸收进同一 version。所有信号、权重、置信写入决策日志。
4. **计数**：指标一律按 work 去重；三级计数对照使多语重复计入可见、可审计。

## 适用场景与限制

- 适用：双向跨语言"已知文献"案例的结果解析；同一工作存在原文正文、官方全译本、仅英文摘要记录、完全重复副本等多视图的归并；需要逐条命中归因（source/DOI/版本/正文语种）的交付。
- 限制：拉丁文字语种识别覆盖 en/pt/es/fr/de/it 六语（其余拉丁语种会倾向标 undetermined 而非猜错）；无正文且无元数据的记录只能标 undetermined；译名标题的跨语种表面相似度天然很低，跨语种归并主要依赖 DOI 关系＋作者序列＋书目指纹，三者皆缺时脚本宁可分列；不做机器翻译、不做主题相关性判读。

## 失败处置

- 阶段 1 报告缺失时阶段 2 以 `status=failed` 退出并写明补救命令。
- 个别文件损坏/坏行：记入 parse_notes，不影响其余记录。
- 输出目录不可写：回退写到 workdir 并在日志中说明。
- 脚本退出码恒为 0；真实状态以报告/result.json 的 `status` 字段为准。

## 自查

按 `SKILL.md` 的"自查方法"六条逐项核对；核心是：每条语种判定有 `basis` 与可回指证据、三级计数自洽、每个 version 有 source 定位、被拒候选对已进 uncertainty、`status` 诚实。

## 维护信息

- 版本：1.0（challenge-802a7115 提交版，方向 B）。判定规则编号、信号权重与阈值见 `rules/version_policy.md`；调阈值通过命令行参数完成，无需改代码。
