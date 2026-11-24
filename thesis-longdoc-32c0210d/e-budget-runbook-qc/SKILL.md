---
name: budget-runbook-qc
description: 在 900 秒 / 64 次模型请求硬预算下执行学位论文/长文档章节编辑工单的过程质量控制 Skill。把预算变成显式调度对象（budget.json 水位）、开工即存诚实 partial、验收门驱动完成判定、受控故障注入验证降级路径。当 /input 提供 case.json + organizer-edit-workorder.json + 分章节 Markdown 工作稿且需要在时限内可靠交付 result.json 时使用。
---

# budget-runbook-qc — 预算调度 · partial-first · 验收门

## 1. 用途与触发条件

组织方给你的不是"改论文"这个模糊目标，而是一个带硬预算的调度问题：900 秒、
64 次模型请求、单次响应 16384 token。本 Skill 提供四条机制：

1. **budget_ledger.py** — 预算是落盘的调度对象，每步先查水位再行动；
2. **checkpoint.py** — partial-first：读完 case.json 立即写诚实 partial，此后任何中断都有产物；
3. **qc_gates.py** — 验收门驱动：每条工单 acceptance 编译成机械断言，全 PASS 才允许 complete；
4. **fault_inject.py** — 故障注入演练：证明 partial 路径真实可用，不是纸面承诺。

触发条件：输入为分章节 Markdown 工作稿 + 编辑工单，且预算受限需要可中断、可交付。

## 2. 输入契约（/input 布局）

```
/input/case.json                      {"case_id","task","output_contract":{"fields":[...]}}
/input/task.md                        任务叙述
/input/organizer-edit-workorder.json  {"schema":"organizer-edit-workorder/v1","items":[{id,title,action,target,acceptance}]}
/input/chapters/*.md                  分章节可编辑工作稿（若材料在别处，以 task.md 为准）
```

**contract 字段集合以实际 case.json 为准**：checkpoint init 运行时读取
`output_contract.fields` 逐字段建骨架，禁止硬编码字段名；缺字段填 null 并记录 problems。

## 3. 工作流（可直接照做的命令序列）

设 `SK=/skills/weekly-skill`。【脚本】=机械可判定，必须脚本完成；【模型】=非机械判断。

```bash
# --- P0 开工（T0–T30）---
# 【脚本】1. 建预算账本（可用 --seconds/--requests 覆盖默认值 900/64）
python3 $SK/scripts/budget_ledger.py init --workdir /app/work --seconds 900 --requests 64

# 【模型】2. 读 /input/case.json、task.md、organizer-edit-workorder.json、章节清单
python3 $SK/scripts/budget_ledger.py tick --workdir /app/work --seconds 10 --note "read inputs"

# 【脚本】3. 立即写 partial 骨架（status=partial、契约键全 null、case_id 正确）
#    ——此后任何时刻中断都有诚实产物
python3 $SK/scripts/checkpoint.py init --workdir /app/work --outdir /app/output --case /input/case.json

# 【脚本】4. 复制可编辑工作稿
cp -R /input/chapters /app/work/chapters

# --- P1 规划（T30–T60）---
# 【脚本】5. 基线验收：未编辑先跑一遍，FAIL 清单=真实工作量
python3 $SK/scripts/qc_gates.py run \
  --workorder /input/organizer-edit-workorder.json \
  --chapters /app/work/chapters --workdir /app/work
# 【模型】6. 按 references/runbook.md §3 裁剪工单（3/5/10 项规则），manual 门聚批

# --- P2 执行循环（T60–T600，逐 item 重复）---
# 【脚本】7a. 每步先查水位
python3 $SK/scripts/budget_ledger.py status --workdir /app/work
# 【模型】7b. 非机械编辑由你完成；机械替换（术语统一等）用 sed 一次落盘，不要逐字改写：
sed -i '' 's/旧术语/新术语/g' /app/work/chapters/*.md   # macOS; Linux 用 sed -i
# 【脚本】7c. 记账 + 重验 + 升级 result.json 对应字段
python3 $SK/scripts/budget_ledger.py tick --workdir /app/work --request --seconds 30 --note "item N edit"
python3 $SK/scripts/qc_gates.py run \
  --workorder /input/organizer-edit-workorder.json \
  --chapters /app/work/chapters --workdir /app/work
python3 $SK/scripts/checkpoint.py promote --workdir /app/work --outdir /app/output \
  --field 'change_record=["item N: ..."]'
# 【模型】7d. manual 门判定（编译不出的 acceptance，攒到一次响应批量判）：
python3 $SK/scripts/qc_gates.py manual --workdir /app/work --item N --verdict PASS \
  --reason "人工核查: ..."

# --- P4 收尾（T780 前必须进入，无论进度）---
# 【脚本】8. 装配章节 + 补齐字段 + 终验 + finalize（门未全过会拒绝并保持 partial）
python3 $SK/scripts/checkpoint.py assemble --workdir /app/work --outdir /app/output --chapters /app/work/chapters
python3 $SK/scripts/checkpoint.py promote --workdir /app/work --outdir /app/output \
  --field '"uncertainty":"写明限制与未验证项"'
python3 $SK/scripts/qc_gates.py run \
  --workorder /input/organizer-edit-workorder.json \
  --chapters /app/work/chapters --workdir /app/work
python3 $SK/scripts/checkpoint.py finalize --workdir /app/work --outdir /app/output
python3 $SK/scripts/checkpoint.py validate --workdir /app/work --outdir /app/output --case /input/case.json

# 【脚本】9. 预算宽裕（normal 水位）时做受控故障注入演练，证明 partial 路径可用
python3 $SK/scripts/fault_inject.py run --workdir /app/work --outdir /app/output \
  --case /input/case.json --workorder /input/organizer-edit-workorder.json \
  --chapters /app/work/chapters
```

## 4. 输出契约（/app/output）

- `result.json`（必须）：`case_id` + `output_contract.fields` 声明的**全部字段** +
  `status`（partial/complete）+ `sources` + `problems`。
- 填充规则：每完成一个 item 立即 promote 对应字段；填不了的字段**显式**填
  `"NOT APPLICABLE — 原因"`，不许留 null 冒充完成。
- **诚实 partial**：finalize 被验收门拒绝时，保持 status=partial，把未过 item 写进
  `problems`，直接交付——partial 诚实交付远好于无 result.json。
- **先存 partial 再改进**：checkpoint init 在第 3 步就落盘，之后每次 promote 都原子写。
- `edited_chapters/`：assemble 复制编辑后章节。图示类产物若生成，须附真实渲染预览；
  渲染器不可用则在 problems 如实记录。

## 5. 异常矩阵

| 异常 | 检测 | 处置 |
|-|-|-|
| 材料缺失（章节/workorder 不在预期路径） | cp / qc_gates 报文件不存在 | problems 记录"材料缺失: <什么>"，promote 后保持 partial 交付；不编造内容 |
| 时间耗尽（水位 floor >85%） | budget_ledger tick/status | 立即停编辑；promote 已有成果；未完成 item 逐个写 problems；终验后 finalize 或保持 partial |
| 请求耗尽（64 次用尽） | budget_ledger requests=64/64 | 不再发起模型请求；剩余字段用脚本可得的实值或 "NOT APPLICABLE — 请求耗尽" 填充；validate 后交付 |
| 单 item 验收不过 | qc_gates run 该项 FAIL | 水位 normal：修一次重验；tight：只重验该 item；floor：放弃该项，写 problems，继续收尾 |
| manual 门判不出 | qc_gates overall=MANUAL_PENDING | 一次响应批量判完所有 manual 门，每条必须 --reason；判不了就 verdict=FAIL + reason 说明 |
| 渲染器不可用 | 需渲染预览时 | 不伪造预览；problems 记录"渲染器不可用，未附预览" |
| finalize 被拒（门未全过/字段 null） | finalize 退出码 3/4 | 按提示补齐或写 problems；**不要绕过**，保持 partial 交付 |

## 6. 依赖与文件清单

依赖：python3 标准库（唯一）；本 Skill 不需要 pdftotext。
文件：

```
SKILL.md                     本文件
README.md                    一页概览
GITHUB_URL.txt               GitHub 链接
scripts/budget_ledger.py     预算账本（init/tick/status，水位三级）
scripts/checkpoint.py        partial-first 检查点（init/promote/assemble/finalize/validate）
scripts/qc_gates.py          验收门编译执行（run/manual）
scripts/fault_inject.py      受控故障注入演练（run）
references/runbook.md        T0–T900 分钟级运行手册 + 水位动作表 + 裁剪规则
references/gates_dsl.md      验收断言 DSL
examples/synthetic/          合成示例（非正式案例结果，见 §5 简报契约）
```

## 7. 已知边界

- **预算靠诚实自报**：ledger 不连真实时钟，tick --seconds 由你如实填写；虚报会让水位失真。
- **DSL 覆盖有限**：只编译 absent/present/figure_ref_integrity 三类；含"除……外"等限定条款
  一律转 manual 门，不强行机械判定。
- **编辑本身不是本 Skill 的重心**：机械替换用 sed/python 落盘，非机械改写由模型完成；
  本 Skill 管"过程"——记账、检查点、验收、交付。
- **单脚本无网络/无外部进程依赖**（fault_inject 只调同目录脚本）；路径全参数化，无硬编码绝对路径。
- 示例 examples/synthetic 为**合成示例**（自造章节，与任何真实论文无关），
  产物带 "SYNTHETIC EXAMPLE" 标注，非正式案例结果。
