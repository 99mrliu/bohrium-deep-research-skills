# VERIFICATION — 本地端到端验收记录

> 合成示例（synthetic example）的验证记录，非正式案例结果。本记录只证明
> bundle 接口可运行、降级路径诚实，不代表任何正式案例表现。

验收日期：2026-11-24；环境：macOS arm64，Python 3.12.14，poppler 的
pdftotext/pdftoppm（`~/Library/Application Support/com.bohrium.runtime/.../poppler/bin`），
TeX Live 2026 的 pdflatex（仅用于附加分支验证时现场生成测试 PDF）。
全部命令已录入 `examples/run.sh`；运行工作区 `examples/_run/` 验收后已删除。

## 1. 主流程（examples/input/）

合成输入：`notes.md`（3 个数字事实：92.4%、n = 128、12 h）、`data.csv`
（含与 notes 冲突的 accuracy 94.1）、`refs.bib`（2 个条目）、`draft.tex`
（故意含 1 个材料里有的数字 92.4%、1 个材料外数字 9 h、1 个冲突数字
93.7%、1 个未知 cite 键 zhang2023unknown）、`task.md`、`case.json`
（output_contract 为 `{type, required}` 方言，4 个字段）。

实际命令（工作目录变量见 run.sh）：

```bash
python3 scripts/matscan.py  --input examples/input --work examples/_run/work
python3 scripts/texaudit.py --draft examples/input/draft.tex --work examples/_run/work
# Agent 步骤：读 coverage.md 与 task.md，改稿写入 output/，手写 change_log.md
python3 scripts/texaudit.py --draft examples/_run/output/draft.tex --work examples/_run/work
python3 scripts/finalize.py --case examples/input/case.json --task examples/input/task.md \
    --work examples/_run/work --output examples/_run/output --input examples/input
```

观察到的关键输出：

- matscan：`材料 5 个，事实 10 条，gap 0 条`；materials_index.md 正确列出
  5 个材料与 gaps 段（无）。
- texaudit 初稿：`matched=2 unmatched=2 conflict=1 材料间冲突=1`，三类问题
  全部被标出（留档副本见 `output-sample/coverage-initial-draft.md`）：
  - conflict：`draft.tex:7` 的 93.7%，给出两个不同口径材料锚点
    `data.csv:3`（94.1）与 `notes.md:5`（92.4%）；
  - unmatched：`draft.tex:8` 的 9 h（候选 `12 h @ notes.md:7` 显式标注
    [弱匹配]）、`draft.tex:9` 的 cite 键 zhang2023unknown（候选 wang2021cnn
    [弱匹配]）；
  - matched：`draft.tex:6` 的 92.4% → `notes.md:5`，wang2021cnn → `refs.bib:2`；
  - 材料间冲突预警：`notes.md:5 = 92.4%` vs `data.csv:3 = 94.1`（共享上下文
    accuracy）；
  - 运行备注确认"已排除来自被审计稿件自身的 3 条事实，避免自我匹配"。
- Agent 改稿后复检：`matched=3 unmatched=0 conflict=0`（94.1%→data.csv:3、
  92.4%→notes.md:5、wang2021cnn→refs.bib:2），稿件注释中的"9 h"与
  `\cite{zhang2023unknown}` 未误报（注释剥离生效）。
- finalize：`status=complete 契约字段=4（null=0）artifacts=6`。result.json
  目检确认（留档副本 `output-sample/result.json`）：
  - `case_id` 原样复制为 `synthetic-provenance-demo-001`；
  - `contract_dialect = typed_dict`，4 个契约字段逐字段镜像为顶层键且值为
    真实存在的产物（`revised_draft: "draft.tex"` 等），未把 `{type, required}`
    元数据当值输出；
  - `artifacts` 6 项全部真实存在；Agent 手写的 change_log.md 与补全后的
    source_map.md 在 finalize 重跑后被原样保留，`uncertainty` 为空。

## 2. 降级场景（examples/input-degraded/，缺失材料路径）

case.json 指向不存在的 `missing/spectra.pdf` 与 `missing/main.tex`，
output_contract 为自然语言方言（3 个字段，含无对应产物的 conflict_memo）。

观察到的关键输出：

- matscan：`材料 1 个，事实 3 条，gap 3 条`，3 条缺失路径全部记入
  materials_index.md 的 gaps 段与 extraction_report.json，脚本未中断。
- texaudit 指向不存在的稿件：落盘空报告并在 notes 记"稿件不可读"，退出码 0。
- finalize：`status=partial 契约字段=3（null=2）`（留档副本
  `output-sample/result-degraded.json`）：
  - `contract_dialect = natural_language`，3 个字段正确解析；
  - `revised_draft: null`、`conflict_memo: null`，uncertainty 逐条说明原因
    （诚实空值，未编造）；`source_map` 指向真实生成的骨架文件；
  - gaps 含全部缺失路径与"无稿件可交付"；result.json 仍按时落盘。

## 3. 附加分支验证

- **PDF 提取**：用 pdflatex 现场编译一段含 `92.4%`、`n = 128`、`12 h` 的
  tex 得到 1 页 PDF（按规范不提交二进制，验收后已删除），matscan 抽出 3 条
  事实，锚点为页码形式 `gen.pdf:p1`，materials_index 注明"PDF 条目锚点以
  页码代行号"。
- **pdftotext 缺失**：以 `PATH=/usr/bin:/bin` 运行 matscan，报告
  `pdftotext: MISSING`，PDF 记入 gaps（"无法提取 PDF 文本"），其余处理照常。
- **case.json 缺失**：同次运行验证降级为遍历输入目录并如实记录 notes。

## 4. 约束检查

在 bundle 根目录执行（find + python3）：

- 文件数 20（≤50）；总大小 66,943 字节（≤2MB，亦低于 300KB 目标）；
- 单文件最大 15,800 字节（≤500KB）；
- 符号链接 0；全部文件通过 UTF-8 解码检查；无 PDF/PNG 等二进制；
- SKILL.md frontmatter 仅含 `name`、`description` 两键，`name` 为
  `latex-source-provenance-gate`，YAML 可解析；
- 每个示例产物文件首部均有「合成示例（synthetic example），非正式案例结果」
  标注（json 以 `_example_notice` 首键形式，留档时添加并已注明）。

## 5. 验收中发现并已修复的问题

1. 初版 texaudit 未排除"被审计稿件自身作为材料被扫描"的条目，导致稿件数字
   自我匹配为 matched；已修复（自我排除 + 报告备注）。
2. 初版 texaudit 会扫描 LaTeX 注释，把 Agent 留在注释里的处置说明误报为
   unmatched；已修复（剥离未转义 `%` 起的注释，`\%` 不受影响），并在
   references/fact-extraction-rules.md 第 4 节记录该约定。
3. coverage.md 中值与单位连写（`9h`），已改为 `9 h`（百分号直连不变）。
