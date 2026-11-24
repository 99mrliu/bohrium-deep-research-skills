---
name: deck-runbook-governor
description: 当任务要求把固定论文或科研材料组织成可编辑学术汇报 deck（slides、PPTX、学术 PPT、学期汇报、组会/答辩/评审场景，含模板、起始 deck 或 slide-workorder）并交付可复核结果时触发。本 Skill 的重心是全过程治理与交付契约：防御性契约接管（contract_init.py）先把 case.json 钉死为 contract.json + PENDING 占位 result.json + 64 请求/900 秒预算台账；六阶段执行中每阶段存 SHA-256 快照（checkpoint.py）保证中断可恢复；交付前由 delivery_gate.py 执行 D1-D6 硬门控（case_id 一致性、契约字段齐备非占位、产物真实落盘、诚实状态一致、状态词表、change_log 模式），用退出码 0/1/2 判定，杜绝 partial 冒充 completed 与字段缺漏。
---

# deck-runbook-governor —— 学术汇报过程治理与交付契约

## 定位与重心

本 Skill 面向"把真实科研材料组织成可编辑、证据可追溯、模板合规的学术汇报 deck"的运行时任务。同类 Agent 的典型翻车不在某一页写得不好，而在**过程失控**：长任务跑到一半中断丢失成果、`result.json` 漏掉契约字段、`partial` 悄悄冒充 `completed`、产物路径指向不存在的文件、改坏之后无法回滚。因此本 Skill 的治理重心是：**把每一次状态变化都变成可核验、可恢复、可追责的操作**。

所有机械可判定的检查下沉到三个确定性脚本（Python3 标准库、无网络依赖），模型只做判断类工作。脚本统一退出码语义：`0` 通过/成功、`1` 门控违例或操作失败（stdout 打印精确违例码）、`2` 用法/IO/模式错误。

## 安装布局

```
/skills/weekly-skill/
├── SKILL.md                      本手册
├── scripts/
│   ├── contract_init.py          Phase 0：防御性契约接管 + 预算台账
│   ├── delivery_gate.py          Phase 5：交付总门（D1-D6）
│   └── checkpoint.py             阶段快照：save / list / verify / recover
├── references/
│   ├── runtime-contract.md       运行时契约：输入布局、result.json 语义、诚实规则
│   └── budget-protocol.md        64 请求 / 900 秒的五阶段配额 + reserve 与降级顺序
└── examples/                     合成示例（SYNTHETIC EXAMPLE，一键跑通，含埋雷变例）
```

下文统一记 `SKILL_DIR=/skills/weekly-skill`：

```bash
SKILL_DIR=/skills/weekly-skill
```

## 运行时契约速览（细则见 references/runtime-contract.md）

- 真实输入在 `/input`：`case.json` + `task.md` + 真实材料（真实 PDF/PPTX，无预提取答案层——**必须读真实文件，不得从文件名推断内容**），可能有模板 PPTX、起始 deck、slide-workorder。
- 中间产物放 `/app/work`；最终交付与可编辑件放 `/app/output`，其中 `result.json` 必须含：真实 `case_id`、case 的 `output_contract` **全部根字段（从实际 case 动态读出，禁止硬编码字段名）**、诚实 `status`（`completed`/`partial`/`blocked`）、`sources`、`uncertainty`、`limitations`、`change_log`。`partial` 必须写明限制，不得伪造软件状态或数据。
- 可编辑 deck 必须附带**真实渲染**的 PDF/PNG 预览；soffice 缺席时如实记录降级，绝不伪造渲染。
- 预算：64 次模型请求 / 900 秒 / 每响应 16384 tokens。**早存盘、增量改进**：第一阶段结束就有可交付的诚实 partial，之后每轮改进都让 result.json 更接近 completed。

## 六阶段案例执行协议

### Phase 0 契约接管（脚本驱动，必先执行，不耗模型请求）

```bash
python3 "$SKILL_DIR/scripts/contract_init.py" --case /input/case.json --out /app/output
```

脚本防御性解析 case.json，一次性产出三份治理底座：

1. `contract.json`：`output_contract` 展开为点路径清单（保留原始声明文本）、slide-workorder 字段抽取（audience / duration_min / slide_count / mode / template / starting_deck / export_formats，缺失记 null 并列入 `work_order_missing`，绝不虚构）、材料清单（逐文件 SHA-256）、必交产物字段识别。
2. `result.json` 骨架：真实 case_id、全部契约根字段 `PENDING` 占位、`status="partial"`（诚实占位，此刻本来就是 partial）。
3. `budget_ledger.json`：64 请求 / 900 秒在五个模型消费阶段上的配额 + 每阶段 reserve。

case.json 缺失或损坏时脚本写出 `status=blocked` 带 `blocked_reason` 的 result.json 并以 exit 2 退出——停止后续阶段，按 blocked_reason 如实报告。随后立即存第一份快照：

```bash
python3 "$SKILL_DIR/scripts/checkpoint.py" --out /app/output --work /app/work save p0-intake
```

模型在本阶段只读 `contract.json`：记住契约字段清单、work-order 约束与材料哈希，**不手写任何字段名**。同时做工具普查（`command -v pdftotext pdftoppm python3 soffice`；python-pptx 用 `python3 -c "import pptx"` 探测），把可用性结论记进 `/app/work/toolchain.txt` 供 Phase 3/4 决策。

### Phase 1 源材料索引与主线提取（模型判断）

- 对每份 PDF 先 `pdftotext -layout` 逐页文本落盘到 `/app/work/pages/`，再读文本做判断；关键图页用 `pdftoppm` 渲染目检。**先落盘再判断**：文本文件可重读，模型响应不可重放。
- 提取主线四件套：`central_question` / `approach` / `results` / `limitations`，每条带 `strength`（established/preliminary/contextual）与 `locator`（file / pdf_page / printed_page / section / exhibit）。
- 数字连同单位与条件**逐字转录**，不得凭记忆改写；写进 `/app/work/mainline.json`。
- 阶段结束向 `budget_ledger.json` 的 `usage` 追加一条，然后 `checkpoint save p1-index`。

### Phase 2 听众与页级 storyboard（模型判断，一次响应成型）

- 依据 work-order 的 audience / duration_min / slide_count 建立听众模型：决策目标、先验知识、预期质疑。work_order 字段为 null 时，在 `uncertainty` 声明假设，不得编造"契约里没有的要求"。
- 逐页规划写进 `/app/work/storyboard.json`：每页**恰好一个 message**（一句可讲的结论）、叙事角色、时间片（合计 = duration）、转场句、图表绑定（exhibit locator 指向 Phase 1 的真实定位）。
- `checkpoint save p2-storyboard`。

### Phase 3 建 deck（模型判断 + 工具）

- 模板优先：python-pptx 可用则 `Presentation(template_path)` 在真实模板内构建；模板缺失或 python-pptx 缺席时按"异常处置"节降级（bundle 内不预置二进制模板，可用 stdlib zipfile+XML 兜底生成最小合法 OOXML）。
- 每页写入讲稿备注（notes），页脚或备注中保留证据 locator；图表引用与 Phase 1 的 exhibit 定位一一对应。
- 产出可编辑 deck 到 `/app/output` 后立即 `checkpoint save p3-deck`——deck 是最贵产物，先保平安再打磨。

### Phase 4 渲染 QA（工具驱动，至多两轮修复回路）

- `soffice --headless --convert-to pdf` 导出，再 `pdftoppm` 出 PNG 预览，放入 `/app/output` 作为导出预览件。soffice 缺席：如实记录到 `result.json` 的异常字段与 `uncertainty`，**绝不伪造渲染**。
- 检查：页数与契约一致、无空白页、无文字溢出/裁切、字体未缩水替换。发现问题进入修复回路（改 deck → 重导出 → 重查），**至多两轮**；两轮不净则在 `limitations` 写明残留问题，以 partial 交付，不无限烧预算。
- `checkpoint save p4-render`。

### Phase 5 交付门（脚本驱动收口）

1. 回填 `result.json`：全部契约根字段（路径相对 `/app/output`）、`sources`、`uncertainty`、`limitations`、`change_log`（每条 `file`/`what`/`why`/`rollback` 四键），按真实完成度设定 `status`。
2. **先存快照再过门**：`checkpoint save p5-pre-gate`。
3. 过门：

```bash
python3 "$SKILL_DIR/scripts/delivery_gate.py" --case /input/case.json --out /app/output
```

- exit 0：打印 `GATE: PASS`，交付。
- exit 1：stdout 逐项 `D#: 细节`，逐条修复后重跑；每轮修复前先 `checkpoint save`，改坏立即 `recover`。
- exit 2：用法/IO/模式错误，检查路径与 JSON 合法性。

## 交付总门 D1-D6（delivery_gate.py）

| 门 | 规则 | 豁免 |
|---|---|---|
| D1 | `case_id` 与 case.json 完全一致 | 无 |
| D2 | `output_contract` 全部根字段存在且非 `PENDING`；空值仅 `partial` 下允许且 `limitations` 中必须有提及该字段名的条目逐项声明原因；`completed` 下空字段判负 | blocked |
| D3 | 必交产物字段（contract.json 的 `required_artifacts`：editable deck、export preview(s)、content map）解析出的每个相对路径真实存在于 `/app/output` 内且字节数 > 0；绝对路径/越界路径判负 | blocked |
| D4 | 诚实一致：`completed ⇒` 产物字段值与 `sources` 非空；`partial ⇒ limitations` 非空；`blocked ⇒ blocked_reason` 非空 | 无 |
| D5 | `status ∈ {completed, partial, blocked}` | 无 |
| D6 | `change_log` 为数组，每条恰含 `file`/`what`/`why`/`rollback` 四个非空字符串键 | 无 |

## 快照与恢复程序

```bash
python3 "$SKILL_DIR/scripts/checkpoint.py" --work /app/work list            # 盘点
python3 "$SKILL_DIR/scripts/checkpoint.py" --work /app/work verify p3-deck  # 只校验
python3 "$SKILL_DIR/scripts/checkpoint.py" --out /app/output --work /app/work recover p3-deck
```

- 存盘节奏：p0/p1/p2/p3/p4/p5-pre-gate 各一次；不要每改一处就存（快照不耗请求，但过多快照干扰选择）。
- `recover` 先全量重算 SHA-256，任一文件不符即**整体中止并点名篡改文件**（exit 1），绝不半恢复；全部通过才回滚。
- 中断恢复套路：`list` 找到最后健康快照 → `verify` 确认完整 → `recover` 回滚 → 从该阶段继续，result.json 始终是诚实 partial 兜底。

## 异常处置（识别 → 处置 → 记录）

| 异常 | 识别 | 处置 | 记录 |
|---|---|---|---|
| 模板缺失 | work_order.template 为 null 或路径不存在 | 有起始 deck 则以起始 deck 为母版；否则 stdlib OOXML 兜底；版式降级 | `exceptions` 字段 + `uncertainty`；不阻断 |
| 图片缺失/不可读 | 材料清单有图但文件打不开，或正文引用不存在的图 | 该页留图占位 + 文字说明，备注注明"源图缺失" | `exceptions` 字段 + 对应页 locator；涉及核心结果页时 status 至多 partial |
| soffice 缺席 | `command -v soffice` 为空 | 跳过分导出，交付可编辑 deck + content map；预览字段如实说明未渲染 | `uncertainty` + `limitations`；export_preview 留空时按 D2 在 `limitations` 逐项声明，status 至多 partial |
| 超时/预算将尽 | budget_ledger 的 usage 逼近配额 | 按 references/budget-protocol.md 降级顺序收缩，提前进 Phase 5 | 诚实 partial，`limitations` 逐字段写明未竟事项 |

铁律：任何异常都**不允许**通过伪造字段值来过门——门控宁可报 `partial`，也不接受编造的 `completed`。

## 预算纪律（细则见 references/budget-protocol.md）

先跑脚本骨架再思考（Phase 0 零请求）；一次响应多做事；每阶段结束立即写盘 + 追加 usage + `checkpoint save`；全量渲染至多两轮；配额将尽按降级顺序收缩，最终用诚实 partial 兜底。

## 确定性说明

`contract_init.py` 与 `delivery_gate.py` 的产物/判定不含随机数与时间戳，同一输入重复运行结果一致。`checkpoint.py` 的 manifest 含 `saved_at_*` 人读时间戳，不参与任何门控判定（见脚本 docstring）。

## 自检

bundle 自带合成示例（SYNTHETIC EXAMPLE），一键跑通全流程并证明门控真的会开火：

```bash
bash "$SKILL_DIR/examples/run_example.sh"
```

预期：contract_init exit 0 且 contract.json 含预期点路径；good_result 过门 exit 0；bad_result 过门 exit 1 且违例**恰好**为 D2/D3/D4；checkpoint save/list/recover 全部 exit 0；篡改快照内文件后 verify/recover exit 1 并点名该文件；末尾打印 `ALL EXPECTATIONS MET`。
