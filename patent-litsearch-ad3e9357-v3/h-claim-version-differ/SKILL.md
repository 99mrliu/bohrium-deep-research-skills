---
name: claim-version-structural-differ
description: 当案件材料中出现来源可定位的权利要求版本（如公开版与授权版、不同观察到的同族成员、跨越 WO 合并 OCR 边界的文本），需要对权利要求文本做确定性结构化切分（编号单元/独立从属/前序-过渡语-要素，边界逐字锚定原文）、双版本要素级对齐（unchanged/modified/added/removed/reordered）并生成经措辞闸门校验的诚实比对说明时，使用本技能。
---

# claim-version-structural-differ：权利要求文本的版本结构化比对

## 一、用途与适用条件

本技能只做一件事：**对来源可定位的权利要求文本做确定性的版本结构化比对**。具体为三步：

1. **切分**（`scripts/claim_segment.py`）：把权利要求文本切分为带编号的权利要求单元；判定独立/从属（检测对 "claim N" / "权利要求N" 的引用）；把每项权利要求切分为前序（preamble）/ 过渡语（comprising、consisting of、包含、其特征在于 等）/ 要素（按分号、编号子步骤、wherein/其中 从句切分）。所有边界以字符偏移锚定源文本，`quote` 恒等于原文子串。
2. **对齐**（`scripts/claim_align.py`）：对同一权利要求的两个版本做 token 级 diff（标准库 difflib）并提升为要素级对应表，每个要素对分类为 unchanged / modified / added / removed / reordered，每格携带两侧逐字引文与 span；相似度阈值显式声明，低于阈值的配对只列为候选、绝不强制；统计数字由脚本按对应表现场重算。
3. **说明**（`scripts/scope_note.py`）：由对应表渲染中文比对说明，附固定诚实性页脚（仅报告文本差异；不假定保护范围是否一致；法律等价性判断超出范围）；`--gate` 模式扫描任意说明并拦截违禁结论性措辞。

适用条件：输入为**纯文本**形式的权利要求版本（可含已声明的 OCR 合并边界行）。不适用：只有图像/PDF 而无文本层的情形（本技能不做 PDF 取证与 OCR）；需要法律结论的情形。

## 二、运行时契约

- 评测方将本技能安装于 `/skills/weekly-skill`，用官方 DeepSeek Harness 在 3 个固定隐藏案件上运行。输入位于 `/input/`：`case.json`、`task.md` 与材料（6 条专利记录、3 份 USPTO 传真原件 PDF、对比论文；号码/主题查询；来源可定位的权利要求版本；官方法律状态未知——须如实说明；观察到的链接并非完整同族；WO 合并 OCR 边界已保留）。**必须读取真实文件内容，绝不从文件名推断。**
- 工作目录 `/app/work`；交付物 `/app/output/result.json`，必须包含：
  - `case_id`：与 `case.json` 逐字一致；
  - `status`：诚实的 `ok` / `partial` / `failed`；
  - `sources`：每个来源的 `path` + `sha256`；
  - `uncertainty`：未解决的不确定点；
  - `change_records`：增量改进记录；
  - **镜像 `output_contract` 的全部字段**；未填写的字段置 `null` 并在 `uncertainty` 中说明原因。
- 预算：64 次请求 / 900 秒 / 16384 token。**先写出诚实的 partial 骨架结果，再增量改进**，每次改进追加一条 `change_records` 记录。
- 绝不编造；partial 必须指明自己的限制（缺失哪个版本、哪段跨越 OCR 边界等）。

## 三、调用方式（有序流水线，含具体命令）

设技能根目录为 `$SKILL`（评测时即 `/skills/weekly-skill`），两个版本的权利要求文本为 `V1.txt`、`V2.txt`（从 `/input` 材料中读取并提取而来）：

```bash
mkdir -p /app/work /app/output

# 0) 自查（可选但推荐；退出码必须为 0）
python3 "$SKILL/scripts/selfcheck.py"

# 1) 切分两个版本
python3 "$SKILL/scripts/claim_segment.py" --input V1.txt --output /app/work/seg_v1.json
python3 "$SKILL/scripts/claim_segment.py" --input V2.txt --output /app/work/seg_v2.json

# 2) 要素级对齐（阈值可显式声明；只有单一版本时省略 --b，得到 partial 单侧清单）
python3 "$SKILL/scripts/claim_align.py" --a /app/work/seg_v1.json --b /app/work/seg_v2.json \
    --threshold 0.60 --output /app/work/correspondence.json

# 3) 渲染中文比对说明，并立即过措辞闸门（退出码必须为 0）
python3 "$SKILL/scripts/scope_note.py" --table /app/work/correspondence.json \
    --case-id "<case_id>" --output /app/work/comparison_note.md
python3 "$SKILL/scripts/scope_note.py" --gate /app/work/comparison_note.md

# 4) 计算来源哈希并组装 result.json（镜像 output_contract；未填字段 null + uncertainty）
sha256sum V1.txt V2.txt
# 将 case_id（逐字）、status、sources(path+sha256)、uncertainty、change_records、
# correspondence 与 note（内联或路径）写入 /app/output/result.json
```

顺序不可颠倒：先骨架（哪怕 partial），后增量；闸门不通过的说明**不得**写入交付物。

## 四、输入输出解释

- `claim_segment.py` 输入：UTF-8 纯文本权利要求；输出 JSON：`claims[]`（`number/span/quote/type/references/preamble/transition/elements[]`，每个要素带 `index/kind/span/quote`）、`ocr_boundaries[]`、`front_matter`、`segmentation_degraded`、`raw_regions[]`、`notes[]`。逐字性不变式：对任意节点 `quote == 原文[span[0]:span[1]]`。
- `claim_align.py` 输入：两份切分 JSON（或仅 `--a`）；输出 JSON：`claim_pairs[]`（含 `element_pairs[]` 与 `candidates[]`）、`claims_added/claims_removed`、`statistics`（脚本重算）、`status/limits`。要素对分类：`unchanged / modified / added / removed / reordered`，每格含两侧 `span+quote`（缺失侧为 `null`）。
- `scope_note.py` 渲染模式输入对应表 JSON，输出 markdown 说明（含固定诚实性页脚）；`--gate` 模式输入任意 markdown，检出违禁措辞时按行号报告并返回退出码 1。
- 退出码约定（全部脚本）：`0` 正常（含 partial/degraded）；`1` 违规（仅闸门检出违禁措辞时使用）；`2` 用法/输入错误。

## 五、异常处理

- **无法切分的权利要求文本**（无编号边界、独立项找不到过渡语等）：对应区域原样保留于 `raw_regions` 或该项的 `preamble.quote`，置 `segmentation_degraded: true` 并在 `notes` 中说明；脚本退出码仍为 0，绝不为求整齐而猜切。
- **缺失版本**（只能观察到一个版本）：`claim_align.py` 省略 `--b`，产出 `mode=one_sided_inventory`、`status=partial` 的单侧清单，`limits` 首条即说明缺失；result.json 中对应字段如实置 partial/null。
- **跨越已声明 OCR 合并边界**：切分 JSON 中相关 span 带 `crosses_ocr_boundary: true`，边界行偏移见 `ocr_boundaries`；对齐结果降为 `partial`，`limits` 写明"版本 X 权利要求 N 的 span [s,e] 跨越边界"，即比对只在该处是部分的，并指出确切位置。
- 输入文件不可读、JSON 不合法、阈值越界：退出码 2，stderr 给出原因；不产生任何半成品输出。

## 六、限制（明确声明不做什么）

- 本技能**不是**法律意见工具：不做侵权判定、不做 FTO（自由实施）分析、不做保护范围/等同性的法律结论；文本差异只按文本差异报告。
- **不做** PDF 取证、版式/印章分析、OCR 重建；只处理已存在的文本层（含已声明的合并边界）。
- **不做**日期编年/优先权链整理，**不做**申请人/发明人实体消歧，**不做**法律状态查询（官方法律状态未知时如实说明）。
- 不做跨语言对齐、不做同义词/翻译层面的对应；低相似度一律落入候选。
- 观察到的链接/同族成员不视为穷尽；只就比对的两个版本发言。

## 七、自查方法

1. 运行 `python3 scripts/selfcheck.py`：合成夹具上断言 7 项性质（3 项权利要求切分与独立/从属标签、quote 逐字性、收窄=modified/丢弃=removed、统计重算一致、闸门对「保护范围相同」退出码 1、单侧 partial、OCR 边界标记），退出码必须为 0。
2. 对任意产出做机器复核：用 `quote == 原文[span[0]:span[1]]` 校验每个 span；重算 `statistics` 与对应表比对。
3. 对任意说明文字运行 `scope_note.py --gate`；退出码必须为 0，且仍需人工通读（闸门是必要条件而非充分条件，见 `references/wording_gate.md`）。
4. 参考文档：`references/claim_grammar.md`（切分语法与边界情形）、`references/alignment_method.md`（相似度/阈值/候选策略）；完整合成演示见 `examples/example_walkthrough.md`。
