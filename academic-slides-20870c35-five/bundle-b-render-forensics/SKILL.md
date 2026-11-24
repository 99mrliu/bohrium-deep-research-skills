---
name: export-render-forensics
description: 学术汇报内容组织任务的导出渲染取证 Skill：当 Agent 需要把论文/研究材料组织成可编辑、模板合规的汇报 deck 并交付可复核的导出件时触发。它内置从契约 intake 到交付的完整六阶段协议，重心在下游导出链的机器取证——用 stdlib 确定性脚本对导出的 PDF 做像素级与几何级核验（页数、空白页、文字越界/页脚侵入、字体缩水、图丢失），并提供 python-pptx 缺失时的最小 PPTX 兜底生成器，杜绝"导出后字体、配色、母版不合规、空白页、文字溢出、图被裁"却无人察觉的失败模式。
---

# export-render-forensics —— 导出渲染取证

## 定位与重心

学术汇报做到最后一步最常见的翻车，不是内容写错，而是**交付物在导出链上悄悄坏掉**：pptx 转 PDF 后某页空白、文本框溢出页缘、字体被替换成小一号、插图没嵌进去或图页只剩图题。人眼抽查页数有限，评审却可能翻到任何一页。

本 Skill 覆盖"从真实材料到可交付 deck"的完整六阶段协议，但把**机器核验的重心放在下游导出链**：所有可判定的渲染质量属性下沉到 `scripts/render_qa.py`（确定性、可复跑、逐条报码），deck 构建在 python-pptx 缺席时由 `scripts/minipptx.py`（纯 stdlib OOXML 写出器）真实兜底。模型只做判断类工作（主线、取舍、讲稿），凡能机械判定的（页数/空白/越界/字高/墨水覆盖）一律交给脚本门控。

退出码约定（本 bundle 全部脚本一致）：

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | 通过 / 成功 | 进入下一步 |
| 1 | 门控违例，stdout 逐行打印 `CODE: detail` | 按 references/render-qa.md 的修复 playbook 逐条修，重跑 |
| 2 | 用法 / IO / 工具缺失错误 | 检查参数、路径、JSON 合法性；工具缺失则如实记录降级 |

## 安装布局

```
/skills/weekly-skill/
├── SKILL.md                  本手册
├── scripts/
│   ├── render_qa.py          导出 PDF 取证门（R1–R5），stdlib + pdftotext/pdftoppm
│   └── minipptx.py           stdlib-only 最小 PPTX 生成器/校验器（build / verify）
├── references/
│   ├── render-qa.md          各门检什么、抓到后怎么修（修复 playbook）
│   └── deck-spec.md          deck_spec.json 模式（minipptx 的输入契约）
└── examples/                 合成示例（一键跑通，good/bad 夹具现场生成现场删除）
```

下文统一记 `SKILL_DIR=/skills/weekly-skill`。

## 六阶段案例执行协议

预算纪律先行：全程 64 次模型请求 / 900 秒 / 每响应 16384 token。批处理 shell 调用、每个阶段结束立即写盘、**全量渲染修复回路至多两轮**——第三轮仍不过门就诚实交付 partial 并在 limitations 中写明残留违例，绝不粉饰。

### Phase 0 —— 契约 intake 与工具普查

- 递归查看 `/input`，读**真实文件**：`case.json`、`task.md`、全部材料（PDF/PPTX/文本）、模板 pptx、起始 deck、slide-workorder（如有）。不得从文件名推断内容；PDF 材料用 `pdftotext` 实际读。
- 写 `/app/work/contract.json`：真实 `case_id`、`output_contract` 的**全部根字段名**（动态读取，禁止硬编码字段清单）、mode、页数、听众、时长、语言、模板与起始 deck 路径、要求的导出格式。
- **立刻**写 `/app/output/result.json` 部分骨架：`case_id` 填真值，`output_contract` 各根字段先占位，`status="partial"`，limitations 写明"交付进行中"。之后每完成一个阶段就地升级它。
- 工具普查并写入 `/app/work/toolchain.json`：`pdftotext`、`pdftoppm`、`python3`、`python-pptx`（import 测试）、`soffice`、可用中文字体。普查结果决定 Phase 3/4 走哪条路径；**缺失的工具如实记录，不得假设**。
- 从 case 导出要求推导 `expectations.json`（页数=契约页数、页脚区比例、最小字高、期望图页清单），存 `/app/work/expectations.json`，Phase 4 的取证门以此为准。

### Phase 1 —— 源材料索引与主线提取

- `pdftotext -layout` 逐页抽取文本；关键图页用 `pdftoppm` 渲成 PNG 目检（这一步的 PPM/PNG 也是后面判断"图页该有多少墨水"的参照）。
- 提取 central_question / approach / results / limitations：每条结论带 strength（established/preliminary/contextual）与 locator（file、pdf_page、printed_page、section、exhibit）。数字连同单位与实验条件**逐字转录**，不凭记忆、不四舍五入。
- 产出 `/app/work/source_index.json` 与 `/app/work/claims.json`。

### Phase 2 —— 听众与页级 storyboard

- 明确听众的决策目标、先验知识与预期质疑，据此定背景比例与结论强度。
- 每页恰好一个 message：写明叙事角色（hook/problem/approach/result/limitation/conclusion…）、时间片、转场句、图表绑定（哪张 exhibit 上哪一页）。
- **同时就地把每页翻译成导出预期的雏形**：哪些页是图页（进 `expected_figure_pages`）、页脚区是否允许有文字（定 `footer_zone_fraction`）、正文最小字号（换算 `min_text_height_pt`）。storyboard 不只管讲什么，也管"导出后长什么样才算没坏"。
- 产出 `/app/work/storyboard.json`，并定稿 `/app/work/expectations.json`。

### Phase 3 —— 在真实模板内建 deck

- python-pptx 可用：`Presentation(template_path)` 在真实模板/起始 deck 上改，保留母版与版式。
- python-pptx 不可用：用兜底写出器生成合法 pptx（这是真实可编辑产物，不是占位符）：
  ```bash
  python3 "$SKILL_DIR/scripts/minipptx.py" build /app/work/deck_spec.json -o /app/output/deck.pptx
  python3 "$SKILL_DIR/scripts/minipptx.py" verify /app/output/deck.pptx   # 必须 exit 0
  ```
  deck_spec.json 的写法见 references/deck-spec.md；verify 会重开 zip、校验全部 XML well-formed、slide 数与 notes 存在性。
- 每页写入**讲稿备注**（speaker notes，含时间预算与转场句），页上保留**证据定位**（source file/page/exhibit）。
- 在 `/app/work/` 留版本快照（deck_spec.json 或中间 pptx 带序号），改坏可回退。

### Phase 4 —— 渲染取证（本 Skill 的机器核验核心）

- 导出：soffice 可用则
  ```bash
  soffice --headless --convert-to pdf --outdir /app/work /app/output/deck.pptx
  pdftoppm -r 110 -png /app/work/deck.pdf /app/output/preview
  ```
  生成 PDF 与逐页 PNG 预览。**soffice 缺席时绝不伪造渲染**：在 result.json 的 limitations 与 change_log 中如实记录"本环境无 office-renderer，渲染门未执行/仅对起始 deck 提供的 PDF 执行"，状态降 partial。
- 取证门（对真实导出的 PDF 执行）：
  ```bash
  python3 "$SKILL_DIR/scripts/render_qa.py" /app/work/deck.pdf /app/work/expectations.json \
      -o /app/output/render_report.json
  ```
  - exit 0：五门全过，进入 Phase 5。
  - exit 1：stdout 逐行 `R#: detail`，按 references/render-qa.md 的 playbook 修 deck/导出参数后**重导出重跑**。完整"修改→导出→取证"循环**至多两轮**；第二轮仍 exit 1，保留 render_report.json 作为证据，delivery 时如实 partial。
  - exit 2：工具或输入问题；若是 poppler 缺失，按降级规则记录。
- 五门速览（细则与修复见 references/render-qa.md）：
  - **R1** 页数与 expectations 一致（导出截断/多加空白页）。
  - **R2** 空白页：该页零文本且整页墨水覆盖率低于阈值（内容整页丢失）。
  - **R3** 文字越界：词框冲出页面矩形，或侵入页脚区比例带（文本框溢出、母版页脚被压）。
  - **R4** 过小文字：页内词框高度中位数低于阈值（导出时字体缩水/缩放链出错）。
  - **R5** 期望图页的内容区墨水覆盖率过低（图没嵌上、被裁、链接图断链）。

### Phase 5 —— 交付

- 完善 `/app/output/result.json`：真实 `case_id` + `output_contract` **全部根字段**（从 Phase 0 的 contract.json 动态对照，一个不落）+ 诚实 `status`（completed / partial / blocked）+ `sources`（材料与 locator）+ `uncertainty` + `change_log`（每轮修复：file/what/why）。
- 交付物齐备：可编辑 deck（pptx）、导出 PDF、逐页 PNG 预览、`render_report.json`、页级证据映射（每页 ↔ 材料 locator）。
- 诚实铁律：渲染门没跑过（工具缺失）就写 partial 并说明；两轮修复后仍有违例就列出残留违例；**宁可 partial，不得伪造 completed，不得伪造软件状态与渲染结果**。

## 确定性说明

`render_qa.py` 与 `minipptx.py` 的判定/产物不含随机数与时间戳：同一 PDF + 同一 expectations 重跑，违例清单与退出码一致；同一 deck_spec 重 build，pptx 部件内容一致（zip 内文件顺序固定）。

## 自检

bundle 自带合成示例（SYNTHETIC EXAMPLE），一键验证两个脚本真的会开火：

```bash
bash "$SKILL_DIR/examples/run_example.sh"
```

预期：matplotlib 现场生成 good.pdf（4 页合规）与 bad.pdf（埋雷：5 页=R1、第 2 页空白=R2、第 3 页词冲出页缘=R3、一页 3pt 小字=R4、期望图页只剩图题=R5）；render_qa 对 good exit 0、对 bad exit 1 且精确打印 R1–R5；minipptx build + verify 均 exit 0；演示结束自动删除全部 .pdf/.pptx/.ppm/.png 二进制，仅留文本日志与 JSON 报告；末尾打印 EXPECTED vs ACTUAL 汇总与 `ALL EXPECTATIONS MET`。
