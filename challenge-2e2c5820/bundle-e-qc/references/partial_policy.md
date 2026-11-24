# 诚实部分交付（Honest Partial）策略

可行性审查运行在有限预算内（约 64 次模型请求 / 900 秒）。本策略定义状态机、
uncertainty 写法、禁写清单与 checkpoint 节奏，目标是：**任何时刻 result.json 都是
一份站得住的交付物**。

## 状态机

```
scaffold(partial) ──完成部分约束审查──> partial（字段部分填充，uncertainty 逐条减少）
      │                                    │
      │七类约束全部审完且 G1-G6 无 FAIL     │时间/材料不足，无法补齐
      ▼                                    ▼
   complete                          partial 定稿（缺口写死，不得粉饰）
      │
      │关键材料缺失/合同条款矛盾导致无法下结论
      ▼
   failed（仅当连 partial 结论都无法给出时；uncertainty 必须写清原因）
```

规则：

- 状态只能反映**已验证**的内容。填入字段 = 该字段已有材料或计算支撑。
- 从 partial 升 complete 的必要条件：契约字段全部非 null + selfcheck 无 FAIL。
- 任何时候发现问题，允许从 complete 降级回 partial（写 change_record 说明原因）。

## uncertainty 必须写什么

1. 缺什么材料/字段（点名，例如「缺少手套箱周末时段的可预订性确认」）。
2. 哪些结论是**条件性**的，条件编号与 review_report.md 对齐。
3. 哪些数字是估算而非合同确认值，估算依据一句话。
4. 时间预算耗尽时，哪些约束类别尚未审查。

## 禁写清单（绝不落入交付物）

- 未获组织方确认的批准/预订/价格，当作既成事实写入。
- 无法从给定材料或显式假设推出的数字（预算、机时、收率等）。
- 「建议进一步确认」之类不挂在编号条件条目上的空头意见。
- 与 review_report.md 正文不一致的结论词。

## Checkpoint 节奏（900 秒预算）

| 时点 | 动作 |
| --- | --- |
| 0 min | 步骤 0：parse_contract → 骨架**立即**落为 `/app/output/result.json`（partial） |
| 每完成一个约束类别 | 把该类别结论 merge 进 result.json + change_record 追加一条 |
| ~10 min（约 600 s） | 跑一次 validate_result + lint_review，修复硬违规；保证当前状态可过 G1-G3 |
| ~12.5 min（约 750 s） | 冻结新分析：完成 review_report.md 收尾、render_report、make_manifest |
| 最后 | selfcheck；FAIL 则修复或降级 partial 再跑一次，确保最终交付 exit 0 |
