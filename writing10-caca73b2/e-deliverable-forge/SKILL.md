---
name: deliverable-forge-rd
description: 面向"结果与讨论"章节定稿的下游交付工程 Skill。针对基础代理只产出松散 Markdown 的常见问题——缺少可编辑 Office 交付物、缺少可供检查的真实渲染预览、图表交叉引用断裂、题注与浮动体脱节——本 Skill 提供一条零第三方依赖的确定性流水线：交叉引用审计与自动重编号、纯标准库生成可编辑 .docx 并自验(失败时降级为 .md+.html)、纯标准库生成 SVG 分页预览、按 output_contract 组装并校验 result.json。本 Skill 不改动任何科学内容，只证明交付包可检查、可编辑、前后一致。Use when a finalized Results & Discussion manuscript must be packaged into an editable .docx deliverable with rendered SVG previews, cross-reference auditing, and a contract-checked result.json in a sandbox that has only the Python standard library.
---

# deliverable-forge-rd:结果与讨论章节交付物锻造

## 解决的问题

上游写作代理通常只返回松散 Markdown,存在四类交付缺陷:

1. **无可编辑交付物**:评审要求的 .docx 并不存在,或依赖 pandoc/LibreOffice/python-docx 等沙箱中不可用的工具;
2. **无渲染预览**:交付物无法被人工快速检视,版式问题(题注脱节、表格溢出)要到投稿时才暴露;
3. **交叉引用断裂**:正文"见图3"实际不存在图3、表1只有题注从未被引用、图号跳号;
4. **结果不合契约**:result.json 缺 output_contract 键或 case_id 被改写。

本 Skill 是定稿之后的**下游锻造环节**:不生产科学内容,只保证交付包**可编辑、可预览、可审计、合契约**。

## 何时使用 / 不适用

**适用**:结果与讨论章节已定稿(数值、结论由上游或模型保证),需要产出可编辑 .docx、渲染预览页、交叉引用审计报告与合契约的 result.json。

**不适用**:

- 稿件尚在写作或数据核验阶段(本 Skill 不生成、不修改科学内容);
- 需要出版级排版(本 Skill 的预览是排版近似,不是出版级 PDF);
- 运行环境允许 pandoc/LibreOffice 且需要复杂样式模板时(本 Skill 面向零依赖沙箱)。

## 运行契约

- 输入:`/input/case.json` 与 `/input/task.md` 及随案材料(稿件 Markdown);
- 工作目录:`/app/work`(中间产物、降级产物均置于此);
- 交付目录:`/app/output`(最终交付物与 result.json);
- `result.json` 必须包含:`case_id`(从 case.json **原样照抄**)、`output_contract` 声明的**全部键**(常见为 deliverable、preserved_facts、evidence_map、change_log),以及诚实的 `status`(success/partial/fail)、`sources`、`uncertainty`;
- docx 构建或预览生成失败时:`status` 记为 `partial`,保留 md/html 降级产物,并在 `uncertainty` 中说明原因;
- 交付物清单(含 .docx 的 sha256 与字节数)写入 result.json 或随附清单文件,供评审复核。

## 依赖

- Python ≥ 3.9,**仅标准库**(argparse/json/re/zipfile/hashlib/xml.etree/unicodedata);
- 不依赖 pandoc、LibreOffice、python-docx、matplotlib 或任何第三方包;
- 所有脚本支持 `--help`,以退出码表达结果(0 成功;1 审计存在错误;2 用法/IO/构建失败)。

## 工作流(按序执行)

**步骤 0 — 读任务,照抄契约键**:读取 `/input/case.json` 与 `/input/task.md`,记录 `case_id` 与 `output_contract` 的全部键名;后续 result.json 以此为准。

**步骤 1 — 初始化 result.json**:

```bash
python3 /skills/weekly-skill/scripts/result_contract.py init \
  --case-json /input/case.json --out /app/work/result.json
```

**步骤 2 — 定稿 manuscript.md**:科学内容(数值、结论、比较关系)由上游/模型保证,写入 `/app/work/manuscript.md`。本 Skill 在此之后**不改动任何数值与论断**。

**步骤 3 — 交叉引用审计**:

```bash
python3 /skills/weekly-skill/scripts/xref_check.py \
  --input /app/work/manuscript.md \
  --report-md /app/output/xref_report.md --report-json /app/output/xref_report.json
```

审计内容:每个浮动体至少在正文被引用一次;每个正文引用可解析到已定义浮动体;同类编号连续;题注非空;首次提及顺序(警告)。若 FAIL:先补正文引用(编辑性修复),再用 `--fix-renumber fixed.md --moves moves.json` 修复编号,重跑至 PASS;全部修复记入 change_log。

**步骤 4 — 构建可编辑 docx**:

```bash
python3 /skills/weekly-skill/scripts/build_docx.py \
  --input /app/work/manuscript.md \
  --out /app/output/manuscript.docx --manifest /app/output/build_manifest.json
```

脚本以 zipfile+手写 OOXML 生成 .docx(标题/段落/粗斜体/管道表格/题注样式),随后**自验**:重开 zip、xml.etree 解析 document.xml、统计段落与表格并断言段落数>0,打印自验摘要;清单与哈希写入 build_manifest.json。

**步骤 5 — 生成 SVG 预览**:

```bash
python3 /skills/weekly-skill/scripts/render_preview.py \
  --input /app/work/manuscript.md --out-dir /app/output
```

输出 preview-1.svg … preview-N.svg(A4 近似页面、CJK 感知换行、标题加粗、表格网格、题注居中、页码;完全确定性)。

**步骤 6 — 组装并校验 result.json**:填写 output_contract 全部键及 status/sources/uncertainty,然后:

```bash
python3 /skills/weekly-skill/scripts/result_contract.py check \
  --case-json /input/case.json --result /app/output/result.json
```

check 打印 PASS 方可交付;FAIL 按提示逐项补齐。

## 红线

1. **渲染/打包环节不得改动任何科学内容**:数值、单位、结论、比较关系在 manuscript.md 定稿后一律冻结;允许的唯一改动是交叉引用编号与正文引用的机械性改写,且必须记入 change_log(附 moves.json);
2. **预览不得冒充出版级 PDF**:SVG 预览是排版近似(朴素换行、字体回退),result.json 的 uncertainty 必须如实声明;
3. **产物清单与哈希必须写入 result.json**(或随附清单),不得虚报未实际生成的文件;
4. case_id 必须逐字节照抄,不得"修正"其格式。

## 异常处理表

| 异常 | 处理 | 记录位置 |
| --- | --- | --- |
| docx 自验失败(zip 损坏、document.xml 不可解析、段落数为 0) | 自动写出 manuscript.md + manuscript.html 降级产物,脚本退出码 2;result.json `status=partial` | change_log + uncertainty |
| 图片/数据文件缺失 | 保留题注与正文引用,题注位置以占位框(预览中为空表格位)表示,不删除浮动体 | evidence_map + uncertainty |
| 字体缺失(CJK 字体不可用) | SVG 使用通用 font-family 回退列表,不嵌入字体文件;版面仍为近似 | uncertainty |
| xref 审计 FAIL 且无法机械修复(如正文引用指向不存在的浮动体) | 停止打包,报告问题清单,`status=fail` | result.json |

## 限制

- markdown 解析为子集实现(标题/段落/粗斜体/管道表格/无序列表/题注行),不支持脚注、公式、嵌套列表与图片嵌入;
- SVG 预览的换行为宽度单位近似,长英文单词不执行断词;
- docx 为最小可用 OOXML,不含页眉页脚、目录域与编号定义,复杂期刊模板需后续人工套版;
- 交叉引用规则覆盖 图/表/Figure/Fig./Table 五类标记,其他语言或自定义浮动体需扩展正则。
