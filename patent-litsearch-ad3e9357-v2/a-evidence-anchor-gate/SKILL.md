---
name: verbatim-anchor-evidence-gate
description: 用于专利与技术文献检索类任务的上游数据真实性（反编造证据锚定）门控技能，当任务要求阅读 /input 下的专利记录文本、USPTO 传真 PDF 或科学论文并在 /app/output/result.json 中产出候选记录、著录字段、同族关系、法律状态或任何结论时触发，通过"源登记（sha256 指纹）—逐字引用锚定—声明式 OCR 容差—确定性审计"四步流程，保证写入 result.json 的每一个字段级事实都能在已登记源文件中找到逐字出处，凡审计不过的字段宁可留空并申报 partial，同时严格遵循 Harbor 平台 /input（case.json、task.md、材料文件）与 /app/output（result.json）的运行契约及"先落盘骨架、再增量改进"的预算纪律。
---

# verbatim-anchor-evidence-gate（逐字引用锚定·上游数据真实性门控）

## 用途与适用条件

本技能服务于"专利与技术文献检索"类 Deep Research 任务，其**重心是上游数据真实性**：凡写入
`result.json` 的字段级事实（专利号、申请号、申请人、发明人、同族成员、法律状态、论文题录、
DOI、结论性陈述等），**必须携带一个逐字引用锚点**（quote + 源文件 sha256），且该 quote 必须
是对应源文件的逐字子串。附带的确定性审计脚本 `quote_audit.py` 会阻断任何无法在源文件中找到
出处的引用；**审计不过宁可 partial，绝不放行未经锚定的内容**。

适用条件：任务输入为本地材料文件（专利著录记录、USPTO 传真 PDF、论文全文或摘要），要求
结构化抽取与比对，且结果正确性取决于"是否忠实于输入材料"而非模型记忆。凡涉及专利号、
同族、法律状态等极易被模型编造的高危字段，一律适用本门控。

## 运行时契约

1. 评测方将本技能安装于 `/skills/weekly-skill`，并以官方 DeepSeek Harness 运行 3 个固定隐藏
   用例。运行时输入为 `/input/case.json`、`/input/task.md` 及材料文件（专利记录文本、USPTO
   传真 PDF、科学论文）。**必须亲自读取真实文件内容，绝不可依据文件名臆测内容。**
2. 一切中间产物写入 `/app/work`；最终交付物为 `/app/output/result.json`，必须包含：
   - `case_id`（原样复制自 case.json）；
   - 诚实的 `status`（`ok` / `partial` / `failed`）；
   - `sources`（输入源清单：path + sha256）；
   - `uncertainty`（不确定性与未填字段说明）；
   - `change_records`（每次写入/修改 result.json 的记录）；
   - **镜像该用例 `output_contract` 的全部字段**：未填字段以 `null` 占位并列入 `uncertainty`。
3. 预算：64 次模型请求 / 900 秒。**必须先用 `scaffold_result.py` 生成诚实的 partial 骨架落盘到
   `/app/output/result.json`，再逐轮迭代改进**（save early, improve incrementally）；每轮改进后
   重跑审计，通过方可提升 status。
4. 绝不可编造专利号、同族关系、法律状态或引用文本。无法解析的内容（乱码、残缺扫描页等）
   按原样保留并记入 `uncertainty`。
5. 产物约束：技能包 ≤50 个 UTF-8 文本文件、单文件 ≤500KB、总计 ≤2MB、无符号链接、无二进制。

## 调用方式

设 `S=/skills/weekly-skill/scripts`；若该目录不存在（例如本地开发环境），回退为技能包内的
`scripts/` 目录（如 `S="$(pwd)/scripts"`）。全部脚本仅依赖 Python 3 标准库；
退出码约定：`0` 成功，`1` 审计失败，`2` 用法/输入错误。

```bash
S=/skills/weekly-skill/scripts
[ -d "$S" ] || S="$(dirname "$0")/scripts"   # 回退：本地技能包目录

mkdir -p /app/work /app/output

# 第 0 步（最先执行）：生成诚实 partial 骨架并落盘
python3 $S/scaffold_result.py --case /input/case.json --out /app/output --status partial

# 第 1 步：登记全部输入源（PDF 自动尝试 pdftotext；OCR 件预声明容差）
python3 $S/source_register.py --roots /input --out /app/work/registry.json \
    --workdir /app/work --tolerance-ocr /input/<某个OCR扫描文本>.txt

# 第 2 步：阅读真实材料，逐字段抽取并记录逐字 quote，填充 result.json
# （可借助 scaffold_result.py --fill 增量深合并）

# 第 3 步：每轮写入后执行确定性审计；通过才允许 status=ok
python3 $S/quote_audit.py --result /app/output/result.json --registry /app/work/registry.json
```

## 输出说明

`/app/output/result.json` 的锚点格式（位于 `evidence_records[]` 或嵌套于
`candidates[]` / `extracted_fields[]` 等任意层级，审计器递归收集所有同时含
`quote` 与 `source_sha256`/`source_path` 的对象）：

```json
{
  "field": "candidates[0].publication_number",
  "quote": "公开号：US0000000EX1",
  "source_path": "/input/src_patent_EX1001.txt",
  "source_sha256": "f00306a0…3bd9",
  "tolerance_used": false
}
```

- `quote`：源文件中的**逐字**片段（审计前对双方做空白归一化：连续空白折叠为一个空格）。
- `source_sha256`：源文件内容指纹，与登记表一致；`source_path` 的 basename 必须与之匹配。
- `tolerance_used`：仅当源文件在登记表中带 `tolerance: "ocr"` 预声明时才允许为 `true`。

## 关键方法

1. **源登记（source registry）**：`source_register.py` 遍历输入根目录，为每个文件记录
   path、sha256、size、字节→文本解码说明；PDF 记录哈希并在 `pdftotext` 可用时用
   `pdftotext -layout` 抽取文本，缺失则标记 `text_extraction="unavailable"` 并继续（绝不崩溃）。
2. **逐字锚定（verbatim anchoring）**：`quote_audit.py` 要求每个 quote 经空白归一化后是
   对应 sha256 源文件文本的**精确子串**；找不到即判失败并打印失败锚点位置与原因。
3. **声明式容差（declared tolerance）**：OCR 噪声（如 `0`/`O` 混淆）允许小编辑距离匹配，
   但**双重声明**缺一不可——登记表条目预声明 `tolerance: "ocr"` 且锚点携带
   `tolerance_used: true`；任何未声明的容差匹配一律 FAIL。细则见
   `references/anchoring_protocol.md` 与 `references/tolerance_declaration.md`。

## 异常处理表

| 异常情形 | 处理方式 |
|---|---|
| case.json 缺少 output_contract | 骨架生成空镜像，uncertainty 与 stderr 同时告警；人工确认契约字段 |
| case.json 缺少 case_id | 以 `UNKNOWN_CASE_ID` 占位并记入 uncertainty |
| 材料文件为 PDF 且无 pdftotext | 登记 text_extraction=unavailable 继续；不得引用其内容，结论记 uncertainty |
| 材料乱码/解码失败 | 以 replacement 字符解码并记 decoding 说明；受影响字段记 uncertainty |
| quote 精确匹配失败且无容差声明 | 审计 exit 1；删除该字段或改写为逐字 quote，status 保持 partial |
| quote 近似匹配但容差未声明 | 审计 exit 1（undeclared tolerance）；补登记与锚点声明或改用逐字 quote |
| source_sha256 不在登记表 | 审计 exit 1（missing file hash）；先登记再引用 |
| 预算将尽（请求/时间） | 立即以当前已过审计的内容定稿，status=partial，未填字段列入 uncertainty |

## 自查方法

在技能包根目录运行端到端自测（登记夹具→审计正例与两个反例→骨架镜像校验）：

```bash
python3 scripts/selfcheck.py   # 全部断言 PASS 且 exit 0 方可交付
```

## 最小调用示例

完整可复现的最小流程（含真实命令与真实输出）见
`examples/example_walkthrough.md`；夹具位于 `examples/fixtures/`，全部为明确标注的合成
虚构数据。
