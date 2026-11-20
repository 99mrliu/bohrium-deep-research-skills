# xlang-termexpansion-queryforge

术语表驱动的多语种受控查询扩展 Skill：从研究问题抽取概念并建立带来源标注的多语种术语表，对未覆盖概念做受控翻译与回译校验，逐语种生成布尔查询式，再把本地检索结果逐条对齐回术语变体并核算语种覆盖。对应赛题"跨语言文献检索"的**方向 A（术语表驱动的多语种受控查询扩展）**。

## 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：用途、输入输出、调用方式、异常处理、自查 |
| `rules/term_expansion_policy.md` | 术语扩展与受控翻译规则：扩展时机、发散控制、上下位词边界、回译判据、unverified 降级、缩写歧义 |
| `scripts/term_table.py` | 术语表工具：候选概念抽取、表合并、回译校验、to_translate 清单（Python 3.8+，仅标准库） |
| `scripts/query_build.py` | 逐语种查询生成＋命中-术语对齐＋语种覆盖核算＋result.json 组装 |
| `resources/term_table_seed.json` | 小规模**格式示范**术语表（3 概念 × 6–7 语种）；不是完整词表，不会自动加载 |
| `templates/result_fields.md` | result.json 字段契约 |
| `examples/example_walkthrough.md` | 合成数据最小示例（示意，非正式案例结果） |

## 依赖与环境

- Python ≥ 3.8，仅标准库；无第三方依赖、无网络依赖（完全离线可运行）。
- 输入契约：`/input/case.json`（含 case_id、研究问题、output_contract）＋本地语料记录文件。
- 输出契约：`/app/output/result.json`（镜像 output_contract 全字段）＋ `query_log.json` ＋ `hit_alignment.md`；中间产物在 `/app/work`。

## 方法概述

```
研究问题 ──► 概念抽取(启发式候选) ──► 术语表(概念×语种×变体, 带来源/置信)
                                      │  未覆盖概念
                                      ▼
                              受控翻译(Agent 供给+back_translation)
                                      │  回译校验(通过/降级)
                                      ▼
              逐语种布尔查询(概念内 OR, 概念间 AND) ──► 本地语料表面匹配
                                      │
                                      ▼
        命中-术语对齐(逐概念命中的变体) ＋ 语种覆盖统计 ＋ 归因转写
```

关键设计决定：
1. **脚本不翻译**。翻译只能由 Agent 以受控翻译条目供给并附回译证据；脚本负责校验（回译规范化后与概念英文 label 比对），不一致即降级为 `unverified`（保留、标记、置信减半）。这把机翻三类错误中的"译名与学科用词不符""译文与原文不同义"变成可核对、可降级的显式状态，而不是隐性失败。
2. **逐语种独立查询**。不拼接多语种 OR 大查询；每语种一条，命中能精确归因到"哪个语种查询、哪个术语变体"。
3. **匹配是表面形式匹配**：拉丁文 NFKD 变音折叠（Portuguese/Spanish 重音、German 变元音与 ß）、CJK 与假名直接子串。不声称语义匹配；对齐表供人工核对。
4. **归因转写不推断**：命中的 language/version/translation_of 等只从记录原文字段转写；缺失即缺失。

## 一次完整使用

```bash
# Agent 先据案例编写 /app/work/case_terms.json（格式照 resources/term_table_seed.json）
# 和 /app/work/translations.json（受控翻译条目，附 back_translation）
python3 scripts/term_table.py --case /input/case.json \
    --out /app/work/term_table.json --workdir /app/work \
    --seed /app/work/case_terms.json --translations /app/work/translations.json
python3 scripts/query_build.py --case /input/case.json \
    --term-table /app/work/term_table.json --out /app/output --workdir /app/work
```

然后按 SKILL.md「自查方法」核对 hit_alignment.md 与 result.json。

## 输入输出解释

- `term_table.py` 输出 `term_table.json`：`concepts`（合并后全表）、`to_translate`（缺失 概念×语种，需 Agent 补译）、`candidate_concepts`（启发式候选，仅供参考）、`roundtrip`（校验统计）。
- `query_build.py` 输出 `result.json`：字段契约见 `templates/result_fields.md`。`status` 判定：术语表为空 → failed；全部声明语种有有效命中 → ok；有语种零命中（已给显式说明）或存在降级查询 → partial。

## 适用场景与限制

- 适用：跨语种已知文献检索的查询构建；需要向人工评审证明"非英语文献由哪个术语变体召回"的场景；葡/西/法/德（变音）、日（假名音译）、中（简体表面形式）等多语种语料。
- 限制：匹配是表面形式匹配，不做词形还原（如葡语复数 piroptoses 需在术语表中列为变体）；中文简繁差异、日文新旧字体需在术语表中显式列变体；不做实时检索，命中上限即本地语料；不判断版本归并（同一工作的多语种视图是否重复计入由下游方向处理，本 Skill 只保证归因字段完整转写）。
- 失败处置：见 SKILL.md 异常处理表；任何部分失败都写入 `uncertainty` 且退出码为 0，`status` 字段承载真相。

## 维护信息

- 版本：1.0（challenge-802a7115 提交版，方向 A）。扩展判据与降级规则见 `rules/term_expansion_policy.md`；目标语种通过 `--langs` 调整，无需改代码。
