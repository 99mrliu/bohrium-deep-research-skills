---
name: zh-register-calibrator
description: 中文学术写作、润色、校对、投稿前文体规范类任务触发。核心能力是对中文稿件做确定性文体 lint（人称、全角标点、口语化、夸大词、缩写规范、术语一致）与措辞强度校准（把结果断言的 L1 初步/L2 较强/L3 定论措辞与材料中的证据强度信号对齐，发现越级断言与因果越界），并自动修复无歧义项、闭环复检到高级别清零。红线：自动修复仅限无歧义规则（R2 全角化、R1 明显人称替换），涉及语义判断的 R3–R8 只报告、由模型逐条处理并登记，绝不自动改写语义。不适用于纯英文稿件，不负责材料取证、数字重算与排版渲染。
---

# zh-register-calibrator：中文学术文体规约与措辞强度校准

## 定位

本 skill 是**语言层的确定性规则引擎**，专治基础 Agent 所产中文稿件的文体病：
口语化、人称混乱、半角标点、强度词越级（把初步结果写成定论）、因果措辞越界、术语与缩写不统一。

与其他写作类 skill 的本质区别：**不管材料取证、不管数字重算、不管渲染**。输入是稿件 + 材料文本，输出是带行号/规则号/严重级的 style_report、无歧义自动修复、以及经模型逐条处理后复检清零的最终稿件。全部规则表驱动、可配置（`references/rules.json`），仅用 Python3 标准库。

## 运行契约（评测平台）

- skill 安装于 `/skills/weekly-skill`；输入在 `/input/case.json`、`/input/task.md` 及材料文件；在 `/app/work` 下工作；最终结果放 `/app/output`。
- `/app/output/result.json` 必须**原样包含 case.json 中 output_contract 的全部字段**（典型键：`case_id`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`），`case_id` 原样回填；另附诚实的 `status` / `sources` / `uncertainty` 与逐条 change records。由 `scripts/assemble_result.py` 机械装配，缺项会以 null 占位并写入 uncertainty，绝不静默丢键。
- 执行预算：**64 次模型请求 / 900 秒**。脚本调用不占模型请求，尽量把检查/修复/装配全部下沉到脚本。

## 可复制命令

```bash
SKILL=/skills/weekly-skill
cd /app/work

# 1) 全量检查（R1–R8），生成报告 + 机器可读 findings + 统计
python3 $SKILL/scripts/register_lint.py \
  --draft draft.md --materials /input/materials/*.md --workdir /app/work \
  --report style_report.md --findings-json findings.json --stats-json lint_stats.json

# 2) 自动修复（仅限 R2 全角化 + R1 无歧义人称替换），逐条写入 fix_log.json
python3 $SKILL/scripts/register_lint.py \
  --draft draft.md --materials /input/materials/*.md --workdir /app/work \
  --fix --out draft_autofixed.md --fix-log fix_log.json

# 3) 模型逐条处理 style_report 中 R3–R8（修改或驳回+理由），写入 resolution_log.json，
#    并据以产出 deliverable.md（此步由你完成，脚本不代写语义）

# 4) 复检：高级别项未清零则退出码 1，回到第 3 步
python3 $SKILL/scripts/register_lint.py \
  --draft deliverable.md --materials /input/materials/*.md --workdir /app/work --verify

# 5) 装配 result.json（契约 5 字段 + 诚实字段 + lint 统计）
python3 $SKILL/scripts/assemble_result.py \
  --case /input/case.json --deliverable deliverable.md \
  --fix-log fix_log.json --resolution-log resolution_log.json --lint-stats lint_stats.json \
  --preserved-facts preserved_facts.json --evidence-map evidence_map.json \
  --sources /input/materials/*.md --out /app/output/result.json
```

## 时间表（900 秒 / 64 请求预算）

| 阶段 | 动作 | 时间 | 模型请求 |
|------|------|------|----------|
| 0 | 读 case.json / task.md / 材料 / 病稿，确认契约键 | 60s | 1–2 |
| 1 | 脚本全量 lint（步骤 1–2，秒级） | 30s | 0 |
| 2 | 读 style_report，逐条处理 R3–R8，写 resolution_log + deliverable | 400s | 2–4（长稿按章节分批，每批 1 请求） |
| 3 | 脚本 --verify；若未清零，回到阶段 2 补处理 | 60s | 0–2 |
| 4 | preserved_facts / evidence_map 核对材料后填写 | 120s | 1–2 |
| 5 | assemble_result + 目检 result.json | 60s | 0–1 |
| 余量 | 复检往返与意外 | ~170s | — |

正常情况下总请求 ≤12，远低于 64 上限；禁止逐条 lint 项单独发请求。

## 规则总表

| 规则 | 名称 | 严重级 | 自动修复 | 要点 |
|------|------|--------|----------|------|
| R1 | 人称 | 高 | 仅「笔者→本文」「我们→本研究」 | 正文出现 我/我们/你/您/笔者；建议改「本文/本研究」 |
| R2 | 标点 | 中 | 是（全角化） | 中文字符后的半角 , . ( ) : ;；小数点、英文句、代码块不误伤 |
| R3 | 口语化 | 高 | 否 | 搞/弄/东西/挺/差不多/一大堆等词表 + 「很」（白名单：很可能/很多/很少） |
| R4 | 夸大词 | 高 | 否 | 革命性/颠覆性/首次提出/完美/彻底解决；同行附「材料依据」标注可豁免 |
| R5 | 强度校准 | 高/低 | 否 | 材料仅 L1 信号而稿件用 L3 定论 → CALIBRATION-MISMATCH（高）；材料无信号 → 低，提示人工确认 |
| R6 | 因果越界 | 中 | 否 | 摘要/结果/结论章节出现 导致/使得/促进了 等，而材料无因果设计信号 → 建议改「相关/伴随」 |
| R7 | 缩写规范 | 中/低 | 否 | 缩写首现须「中文全称（ABBR）」；重复定义报低 |
| R8 | 术语一致 | 低 | 否 | glossary.lock 变体检索 + 高频候选术语组自动抽取，列出让模型裁决 |

判定逻辑、完整词表与豁免条件见 `references/rules.md`；强度分级体系见 `references/strength-calibration.md`；glossary.lock 格式见 `references/glossary-format.md`。所有词表/阈值可在 `references/rules.json` 调整，无需改代码。

## 误报处理

- lint 是启发式规则，允许误报；**处理闭环不是“照单全收”**：模型对每条 finding 选择 `fixed`（改）或 `rejected`（驳回 + 理由），全部写入 resolution_log.json。驳回必须给出语言学/事实理由（示例：R8 把「配伍规律/方剂配伍」误判为变体，实为不同概念，驳回）。
- 漏报优先于误报被容忍的场景：R2 只匹配中文字符紧邻的半角标点，宁漏勿错；R5 在材料无信号时只发低级别提示，不阻断交付。
- `--verify` 只对**高**级别项卡关；中/低项允许带理由保留，但必须在 resolution_log 登记。
- 遇到系统性误报，优先调整 `references/rules.json` 词表/白名单，不要改稿件迁就规则，也不要改脚本逻辑。

## 最小示例

`examples/` 内含合成示例全套（**合成示例，非正式案例结果**）：`examples/input/`（case.json、task.md、含「初步」信号词的材料、故意触发 R1–R7 各至少一条的病稿 draft_bad.md）与 `examples/output/`（真实运行生成的 style_report.md、deliverable.md、fix_log.json、resolution_log.json、result.json 等）。复现命令见 `examples/README.md`。
