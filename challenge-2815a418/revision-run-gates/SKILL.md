---
name: revision-run-gates
description: 审稿回复与论文修改的受控运行方案——当评测要求按审稿意见修订给定基线稿、逐条回复并交付诚实 result.json 时触发；以阶段门、检查点、预算台账与诚实部分结果为第一公民。
---

# revision-run-gates：受控返修流程（阶段门 + 检查点 + 预算台账 + 诚实部分结果）

## 用途
把「审稿回复与论文修改」建模为一条**受控运行**的阶段机：

```
orient → materials → anchors → decisions（人判门）→ apply → letter → qc → finalize
```

- 每个阶段写检查点 `work/state/<stage>.json`，任何时刻中断都有合法的部分 `result.json`。
- `decisions` 是唯一的**人判门**：脚本跑到门口停下并打印 JUDGMENT LIST，Agent 填好判断文件后用 `mark` 继续。
- `finalize` 不由 Agent 拍脑袋定状态：由 qc_report 与各字段完成情况**重算**诚实总体 status。
- 全流程仍是完整返修方案（拆解意见 → 逐条决策 → 锚点落稿 → 回复信 → 派生产物 → 机器回检），过程控制是它的灵魂。

## 运行契约（必须严格遵守）
- 输入：`/input/case.json` 与 `/input/task.md`；材料在 `/input/materials/manuscript-baseline.md`（组织方基线摘要）与 `/input/materials/reviewer-comments.md`（意见摘要）。
- 工作目录 `/app/work`；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 必须含**原始 case_id** 和案例 `output_contract` 的**全部字段**（字段名以 case.json 为准），另含诚实 `status`（success / partial / unable_to_determine）、`sources`、`uncertainty`、`change_records`。
- **早落盘原则**：orient 阶段就写合法的 partial result.json；此后每完成一个阶段就增量更新；部分完成必须说明界限；材料缺失 / 无法判断 / 运行失败分别说明。
- 只修订指定基线，逐条处理实际给出的意见；实质性修改必须真实落在基线中（脚本逐字锚点落稿，Agent 不得手改产物绕过 changes.json）。
- 预算：64 次模型请求、900 秒、16384 tokens/响应；见「预算台账」。
- 重复运行必须**幂等**：阶段产物存在且输入未变则跳过；`--force STAGE` 重跑指定阶段及下游。

## 快速路径
```bash
export SKILL=/skills/weekly-skill     # 安装路径；cwd 无关，默认即契约路径
python3 "$SKILL/scripts/run_gates.py" run      # 跑到 decisions 门停下，打印 JUDGMENT LIST
# …Agent 阅读 JUDGMENT LIST 与 work/anchor_map.json，填写 /app/work/decisions.json 与 /app/work/edits.json…
python3 "$SKILL/scripts/run_gates.py" mark     # 确认判断已填，自动走完 apply→letter→qc→finalize
python3 "$SKILL/scripts/run_gates.py" status   # 随时查看各阶段 done / PENDING / FAILED
```
非标准路径时用 `--input / --work / --output` 覆盖（见 examples/run_example.sh）。

## 检查点协议摘要
- 检查点文件：`/app/work/state/<stage>.json`，含 `done / fingerprint / artifacts / error / ts`。
- 指纹 = 该阶段输入文件的 sha256 组合；指纹一致且产物存在 → `[SKIP]` 幂等跳过。
- 中断恢复：**直接重跑 `run`（或 `mark`）即从最后一个未完成检查点继续**，无需任何清理。
- 细节与演练见 `references/checkpoint_protocol.md`。

## 预算台账（64 次模型请求）
| 用途 | 请求数 | 说明 |
|---|---|---|
| 探查 | 1 | 读 task/case/材料 + `run` + `status`（尽量一次读完） |
| 判断 | ≤58 | 逐条意见决策、写 decisions.json / edits.json、QC 失败后的修复迭代 |
| 核验 | ≥3 | 读 qc_report、抽查锚点、核对 result.json——**不可省** |
| 交付 | 2 | finalize 摘要核对与收尾汇报 |

规则：每通过一个检查点，在 `/app/work/run.log` 追加一行 `BUDGET spent=N remain=M note=<阶段>`。超支降级：先砍回复信润色（骨架即可交付），核验与交付请求必须保留。详见 `references/budget_ledger.md`。

## 事实红线（QC 会机器扫描，违反即 fail）
- 不得冒称真实审稿人逐字要求；只处理材料中实际给出的意见。
- 不得冒称真实补做了实验/数据；无法补做的一律 `action=cannot` 并进入 uncertainty。
- 不得冒称原作者已改稿；所有修改由本流程的 edits.json 落稿并留 CHG 标记。
- 不得冒称编辑部已接收。

## 异常处理表
| 情形 | 处理 |
|---|---|
| 运行中断 | 直接重跑 `run` / `mark`，从最后检查点继续（幂等） |
| 门未满足 | `mark` 打印缺失项并退出 1；填好两个判断文件后重跑 `mark` |
| QC 失败 | 读 `work/qc_report.json` 定位失败维度，修正 decisions/edits 后 `run --force apply`（或对应阶段）重跑 |
| 意见冲突 | 相关 req 取 `action=clarify` 或 `reject`，rationale 写明冲突，回复信如实披露 |
| 意见有误 | `action=reject` + rationale 给出依据 |
| 无法补做 | `action=cannot` + `evidence_status=无法补做`；result.json 的 uncertainty 必含此项；总体 status 至多为 partial |
| 基线缺失 | materials 阶段记录 BASELINE_MISSING，result.json 立即落 `unable_to_determine` |
| 多轮返修 | 新意见到达后 `run --force anchors` 重建骨架（已填文件不被覆盖，需人工合并） |

更多失败分类与披露写法见 `references/failure_taxonomy.md`。

## 脚本清单
| 文件 | 作用 |
|---|---|
| `scripts/run_gates.py` | 阶段机：`run / mark / status / --force`；写检查点、早落盘 result.json、幂等跳过 |
| `scripts/workers.py` | 确定性工人：材料清单与锚点图、判断骨架、锚点落稿、回复信骨架、派生产物 |
| `scripts/qc_check.py` | 五维机器回检：覆盖/锚点/对齐/CHG 三方一致/证据合法 + 语气红线 + 材料外数字警告 |
| `scripts/finalize.py` | 交付闸门：字段级校验、重算诚实 status、镜像 uncertainty 与 change_records |

全部仅用 Python 3 标准库；无可选依赖，无需降级。

## 最小示例
`examples/` 内含合成示例（**非正式案例结果**）：`examples/run_example.sh` 演示完整受控流程——
`run`（停在门）→ `status` → 拷入示例判断文件 → `mark` 自动跑完 → 重复 `run` 证明幂等 → 负例（坏锚点）验证 QC/finalize 报错。
