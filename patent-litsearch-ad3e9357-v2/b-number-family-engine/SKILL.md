---
name: patent-number-family-engine
description: 面向"专利与技术文献检索"挑战（challenge-ad3e9357）的确定性专利号码规范化与同族合并引擎：当任务涉及专利公开号/授权号/申请号/优先权号的解析校验、语料中的号码命中定位、或基于优先权的同族归并时触发；所有号码解析、语料匹配与族合并均由确定性脚本完成而非模型，歧义一律以 warnings+alternatives 显式呈现绝不静默裁决，无法解析内容原文保留并记入 uncertainty，输出镜像 output_contract 并携带诚实状态（ok/partial/failed）、sources、uncertainty 与 change_records。
---

# patent-number-family-engine — 确定性号码与同族引擎

## 用途与适用条件

本 Skill 的唯一重心是**确定性解析工程**：专利号码的规范化、校验、语料命中
与同族合并全部由 `scripts/` 下的 Python 脚本（仅标准库）完成，模型只负责
编排与解释，**绝不凭记忆解析或猜测任何号码/族归属**。

适用条件：
- 任务给出或需要识别专利号码（公开号、授权号、申请号、优先权号）；
- 任务需要在给定材料（专利记录文本、USPTO 传真 PDF、对比论文）中定位号码；
- 任务需要把多条记录归并为同族（simple / extended 两种口径并排输出）。

不适用：证据台账/引文审计、检索策略设计、法律状态判定、许可分级——那些
由其他 bundle 负责。法律状态在本引擎中一律标注"官方登记未核验+查询日期"。

## 运行时契约

- 评测方将本 Skill 安装于 `/skills/weekly-skill`，用官方 DeepSeek Harness
  运行 3 个固定隐藏案例。
- 运行时输入：`/input/case.json` + `/input/task.md` + 材料文件（专利记录
  文本、3 份 USPTO 传真原件 PDF、对比论文）。**必须读取真实文件内容，绝不
  能从文件名推断内容。**
- 工作目录 `/app/work`；交付物 `/app/output/result.json`，须含 `case_id`、
  诚实状态（`ok`/`partial`/`failed`）、`sources`、`uncertainty`、
  `change_records`，并**镜像 case.json 的 output_contract 全部字段**：
  未填充字段 → `null` 且字段名列入 `uncertainty`。
- 预算：64 次模型请求 / 900 秒。因此**必须先用
  `scripts/scaffold_result.py` 生成诚实的 partial 骨架**，再增量填充改进。
- 绝不编造号码、族归属或法律状态；无法解析的内容原文保留并记入
  `uncertainty`。
- Bundle 约束：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总量 ≤2MB、无符号
  链接、无二进制。

## 调用方式（有序流水线）

在 `/app/work` 下依次执行（每步均可独立失败并降级，见异常处理表）：

1. **scaffold（最先做）**
   `python3 /skills/weekly-skill/scripts/scaffold_result.py --case /input/case.json --out /app/output`
   立即得到镜像 output_contract 的诚实 `result.json`（status=partial）。
2. **index**
   `python3 /skills/weekly-skill/scripts/corpus_scan.py index --roots /input --out /app/work/index.json`
   抽取全部专利号码 token（文件+行号定位）；PDF 经
   `pdftotext -layout` 抽取到 workdir，pdftotext 缺失则标记 unavailable 并继续。
3. **query**
   `python3 /skills/weekly-skill/scripts/corpus_scan.py query --index /app/work/index.json --numbers "US 10,293,847 B2" ... [--keywords K...] --out /app/work/hits.json`
   号码匹配种类容忍：同号不同种类列入 `related_hits` 并附核对提示；
   关键词为字面包含召回（recall-only）。
4. **extract/records**：从命中上下文与记录文本中读取书目字段，构造
   `records.json`（`record_id` / `numbers` / `priorities` / `source_locator`）。
   优先权号逐条经 `patent_numbers.py normalize` 校验；解析失败的原文保留。
5. **family merge**
   `python3 /skills/weekly-skill/scripts/family_merge.py --records /app/work/records.json --out /app/work/family.json`
   并排输出 simple 与 extended 两种口径 + scope_note。
6. **fill result**：把规范化结果、命中、双口径族等写入 fill.json，
   `python3 /skills/weekly-skill/scripts/scaffold_result.py --case /input/case.json --out /app/output --fill /app/work/fill.json --status <ok|partial|failed>`
   深合并进骨架；每一步重要操作追加 `change_records`。

## 输出

`/app/output/result.json`：镜像 output_contract；含
`case_id` / `status` / `sources` / `uncertainty` / `change_records`；
未填充字段为 `null` 且列入 `uncertainty`。中间产物（index.json、
hits.json、family.json）留在 `/app/work` 供核查。

## 关键方法

- **号码规范化**（`scripts/patent_numbers.py`，规则详见
  `references/number_formats.md`）：去分隔符/空白、大写化后按 US/WO/EP/
  CN/JP/KR（及合成测试码 XX）的公开号/授权号/申请号/优先权号模式解析，
  输出 `{input, ok, normalized, kind, country, number, kind_code,
  warnings[], alternatives[]}`。
- **歧义策略**：一个输入存在多种合法解读（如 7/8 位裸号既可能是 US 授权号
  又可能是申请序列号；无种类代码的 JP/KR 号）→ `ok=true` + 主解读 +
  `alternatives` + `AMBIGUOUS` warning，**绝不静默二选一**；非法输入 →
  `ok=false`，不猜测。
- **OCR 粘连边界**（`references/ocr_boundary.md`）：`split` 模式仅当存在
  **唯一**边界使两侧均为合法号码时才拆分；0 个或多个合法边界 → 原文保留
  + warning。
- **双口径族合并**（`references/family_scope.md`）：simple = 优先权集合
  完全相同；extended = 共享 ≥1 件优先权的连通分量；两口径并排输出并附
  scope_note；仅基于观察到的链接，不保证穷尽，不代表权利要求范围一致；
  无优先权记录单列并附"族归属不确定，观察到的链接非完整同族"。

## 案例路由表

| 案例类型 | 路由 | 说明 |
| --- | --- | --- |
| 号码类（给号查族/查命中） | 主场景：完整流水线 1→6 | 解析、命中、族合并全部确定性完成 |
| 主题类（关键词/主题检索） | 降级：`query --keywords` 字面包含召回 | 仅为召回级退路；把"字面匹配、未做语义相关性排序、召回受限"写入 `uncertainty` |
| 法律状态类 | 不判定 | 一律标注"官方登记未核验+查询日期"，写入 `uncertainty`；本引擎无法律状态机制 |
| PDF 传真件 | `index` 自动 pdftotext -layout | 抽取失败/pdftotext 缺失 → unavailable，继续并记入 `uncertainty` |

## 异常处理表

| 异常 | 行为 |
| --- | --- |
| 号码无法解析 | `ok=false`，原文保留，记入 `uncertainty`，不猜测 |
| 号码多解 | 主解读 + alternatives + AMBIGUOUS warning |
| OCR 粘连多解/无解 | 不拆分，原文保留 + warning |
| PDF 无法抽取 | 标记 unavailable，继续处理其余文件，记入 `uncertainty` |
| case.json 形状异常/无法解析 | scaffold 防御性生成最小骨架（默认字段），不中断 |
| records.json 非 list / 读取失败 | family_merge 退出码 2，骨架保持 partial |
| 预算将尽 | 保证 /app/output/result.json 为诚实 partial；缺口列入 `uncertainty` |
| pdftotext 缺失 | index 不中断；PDF 文件列入 unavailable |

## 自查

```
python3 /skills/weekly-skill/scripts/selfcheck.py
```

在 `examples/fixtures` 上端到端验证：合法/歧义/非法号码电池、OCR 粘连
（唯一边界成功、多解保持原文）、语料索引与种类容忍查询（含 related_hits
与非专利文献分离）、simple vs extended 族合并差异、scaffold 骨架与深合并、
CLI 冒烟。**全部断言通过才 exit 0**（失败 exit 1，用法错误 exit 2）。

## 最小示例

```
$ python3 scripts/patent_numbers.py normalize "US 10,293,847 B2" "16123456"
```
输出（示意，合成示例）：前者 `ok=true, normalized=US10293847B2,
kind=grant`；后者 `ok=true` 但带 `AMBIGUOUS` warning 与
`alternatives`（US 授权号 vs US 申请序列号）。
完整逐步演示见 `examples/example_walkthrough.md`。
