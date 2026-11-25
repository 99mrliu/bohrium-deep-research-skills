# 预算规则（Bundle D）

- 官方包线：64 次模型请求 / 900 秒。本 Skill 的默认值即按此设置。
- 每块恰 1 次翻译请求；术语决议等少量额外请求须如实入账（--requests）。
- `list-pending` 每批前显示剩余请求/秒；剩余不足时立即转 partial 交付：
  已完块照常组装 `result.json`，`status=partial`，未译块清单入 `uncertainties`。
- 幂等重跑不重复计预算；同一内容重复 mark-done 记 `idempotent-skip`。
- 不得为压缩请求次数而合并多块一次翻译后拆账登记——台账必须反映真实请求。
