# 合成示例（非正式案例数据）

> 本目录全部内容为**合成示例，非正式案例数据**，仅用于演示与回归测试技能流程。

## 埋入的缺陷（供验证脚本是否真能发现）

1. **方案内矛盾**：v1 第 3.2 节退火温度写 `58 °C`，第 5 节写 `60 °C`。
   预期被 `scan_contradictions.py` 的 (a) 表标记，并被 E04/E05 记为 fail。
2. **门槛 missing**：v1、v2 均使用人体临床样本却未写伦理审批。
   预期 E10/E11 以 missing + absence_scope 通过锚定校验。
3. **跨版本差异**：v1 与 v2 在退火温度、样本量、耗材数量上口径不同，
   预期出现在矛盾扫描 (b) 表。

## 复现

```bash
sh run_example.sh
```

预期全程退出码 0；产物写入 `output/`：

| 文件 | 说明 |
|---|---|
| `plans.json` / `plans.lineindex.json` | 方案索引与行偏移 |
| `materials.json` | 组织方合同与参数域（含 JSON 路径） |
| `anchors_verified.json` | 全部证据条目 + char/line 偏移 + verified 标志 |
| `anchors_rejected.json` | 被拒条目（正常应为空） |
| `contradictions.md` | 矛盾扫描报告 |
| `result.json` | 按 output_contract 装配的结果 |

## 反向测试（验证校验器会拒绝坏引文）

```bash
sed 's/退火延伸 58 °C 30 s/退火延伸 58度/' evidence_ledger.jsonl > /tmp/bad.jsonl
python3 ../../scripts/verify_anchors.py output/plans.json /tmp/bad.jsonl /tmp/badout
# 预期退出码 2，并列出被拒条目；rm -rf /tmp/bad.jsonl /tmp/badout
```
