# 人工复核协议（review protocol）

本文件是 `scripts/apply_overrides.py` 所执行协议的权威说明。

## 1. override 格式（overrides.jsonl）

每行一个 JSON 对象，字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `target_path` | ✓ | 点路径，如 `summary`、`items.1.conclusion`（列表段用数字下标） |
| `new_value` | ✓ | 任意 JSON 值 |
| `reviewer` | ✓ | 复核人标识（谁改的必须可查） |
| `rationale` | ✓ | 修改理由——**这是沉淀的原料**，写“因为……所以……” |
| `date` | ✓ | 复核日期（ISO 建议） |
| `old_value_expected` | 可选 | 乐观锁：声明“我以为现值是 X”，不符则拒绝，防止基于过期版本误改 |

示例：

```json
{"target_path": "summary", "new_value": "……", "reviewer": "李复核", "rationale": "草稿遗留占位符；依据 evidence[1] 改判", "date": "2026-11-25", "old_value_expected": "……TBD"}
```

## 2. 应用语义

- 按文件行序逐行应用；
- **拒绝创建新分支**：目标路径的任何中间层或末层不存在 → 拒绝。
  唯一例外是 `change_records` 追加（脚本内部使用），以防拼写错误
  静默变成新字段；
- `old_value_expected` 与现值不符 → 拒绝并在 changelog 记录期望/实际；
- 每一行（无论应用或拒绝）都写入 `<workdir>/changelog.jsonl`；
- 应用的行追加到 result.json 的 `change_records`（含 before/after）；
- 被拒绝的行**绝不中断运行**，脚本恒以 exit 0 结束。

## 3. 复核人角色

| 角色 | 职责 |
|---|---|
| reviewer（复核人） | 逐条核对结果与证据，对问题字段提交 override，必须写 rationale |
| adjudicator（裁决人） | 处理冲突 override（见第 4 节），拥有最终拍板权 |
| maintainer（流程维护人） | 读沉淀报告，把高频修正固化为模板/校验/预算调整 |

小规模团队可一人兼多角，但 **reviewer 与原作者不应是同一人**。

## 4. 冲突 override 的裁决

两个 override 指向同一 `target_path` 时：

1. **先到先应用**：行序靠后的 override 面对的是已被改过的现值；
2. 若后者携带 `old_value_expected`，它自然因不符而被拒绝——这是
   乐观锁在保护你，不是故障；
3. 意见真正冲突时，**不要靠覆盖顺序解决**：由 adjudicator 单独写一行
   新的 override（rationale 中注明“裁决：采纳 X 的意见，理由……”），
   让裁决本身也留在 change_records 里；
4. 同一字段被来回改 ≥2 次 → 自动进入沉淀报告重点名单，触发流程复盘。

## 5. 沉淀机制（sedimentation）

人工修正的归宿是**流程改进**，不是一次性补丁：

1. `apply_overrides.py` 每次运行后写 `<workdir>/sedimentation_report.md`；
2. 报告按 `target_path` 首段（字段族）聚类，统计应用/拒绝次数；
3. 对高频被改字段族给出改进建议，例如：
   - `summary` 反复被润色 → 把高频人工措辞固化为生成模板/写作规范；
   - `items` 结论反复被纠正 → 该类条目增加二次独立评估（双跑取一致）
     或提高其模型请求预算；
   - `evidence` 反复被补 → 把 source/locator 必填校验前置到生成阶段；
   - `status` 判定反复被推翻 → 把判定规则写成可执行检查清单；
4. maintainer 每个评估周期至少复盘一次沉淀报告，把建议转成对
   上游提示词、检查规则或预算分配的具体修改；
5. **禁止**直接手改 result.json 而不走 override——那会让修正无法沉淀，
   审计链断裂（契约修复等机械性补齐除外，且应在 change_records 中说明）。
