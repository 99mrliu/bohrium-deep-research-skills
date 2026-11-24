# 检查点协议（Checkpoint Protocol）

本协议保证：任何时刻中断都有合法的部分 result.json；重复运行幂等；恢复无需人工清理。

## 1. 阶段与检查点文件

阶段序列：`orient → materials → anchors → decisions（人判门）→ apply → letter → qc → finalize`

每阶段结束后写 `/app/work/state/<stage>.json`：

```json
{
  "stage": "apply",
  "done": true,
  "fingerprint": "sha256(各输入文件路径+内容的组合)",
  "artifacts": ["/app/output/revised-manuscript.md", "/app/work/changes.json"],
  "error": null,
  "ts": "2026-01-01T00:00:00",
  "...阶段附加字段（如 n_applied / failures / contract_fields）": "..."
}
```

- `fingerprint`：该阶段输入文件（见 `run_gates.py: stage_inputs`）的 sha256 组合；输入变化 → 指纹失效 → 阶段自动重跑。
- `artifacts`：该阶段写出的产物绝对路径；任一产物被删除 → 阶段重跑。
- `error`：非 null 即失败阶段，进入 run.log 与 JUDGMENT LIST。

## 2. 幂等规则

1. 阶段满足「state 存在且 done=true 且指纹一致 且全部 artifacts 存在」→ 打印 `[SKIP]` 跳过。
2. 否则重跑该阶段；重跑是**覆盖式**的（原子写 tmp+replace），不会产生重复内容。
3. `--force STAGE`：删除 STAGE 及全部下游阶段的 state 文件后按序重跑（上游仍幂等跳过）。
4. 判断骨架（decisions.json / edits.json）**只在不存在时生成**，绝不覆盖 Agent 已填内容。

## 3. 中断恢复演练

| 中断点 | 恢复动作 | 预期 |
|---|---|---|
| orient 之后断电 | 重跑 `run` | orient/materials/anchors 视指纹 SKIP 或秒级重跑，再次停在 decisions 门 |
| 填判断文件填到一半 | 重跑 `mark` | 门校验打印缺失项，退出 1；继续填，再 `mark` |
| apply 之后被杀 | 重跑 `mark` | orient…apply SKIP，从 letter 继续 |
| qc 失败 | 修 edits/decisions 后 `run --force apply` | apply 及下游重跑，finalize 重算 status |
| finalize 失败 | 按 FINALIZE-ERROR 清单补齐产物后 `run --force finalize` | 仅 finalize 重跑 |

## 4. 重复运行一致性

完整跑完后**连续三次** `run`：

- 三次全部阶段 `[SKIP]`（decisions 门已满足，不产生 GATE-STOP）；
- `result.json`、`revised-manuscript.md`、`response-letter.md`、`change-locations.json`、`evidence-checklist.json` 的 sha256 三次完全一致；
- `examples/run_example.sh` 第 4 步自动验证 result.json 三次哈希一致。

注意：`finalize` 写入的 `finalized_at` 时间戳只在 finalize 真正重跑时变化；幂等跳过时不改任何字节。

## 5. result.json 的早落盘时序

| 时点 | result.json 状态 |
|---|---|
| orient 完成 | 合法骨架：case_id + output_contract 全部字段（null）+ `status=partial` + note「运行中」 |
| materials 发现基线缺失 | 立即改写 `status=unable_to_determine` 并说明 |
| apply / letter 完成 | 契约字段逐个填入真实相对路径，change_records 镜像 |
| finalize | 由 qc_report + 字段完成情况重算最终 status，镜像 uncertainty |
