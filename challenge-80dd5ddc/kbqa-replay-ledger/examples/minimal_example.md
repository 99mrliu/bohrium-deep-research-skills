# 最小调用示例（合成示例）

> **本示例为合成示例**：输入库与输出均为虚构数据，仅说明接口与完整流程，
> 不是平台正式案例的结果。

## 输入（make_fixture.py 生成的虚构资料库）

```
input/
  case.json          # case_id=synthetic-ledger-001，1 个问题 + output_contract
  task.md
  docs/bat11_notes.txt  # 虚构数据说明（首次库仑效率 89.3%）
  docs/bat11_cycle.txt  # 虚构补充记录
```

## 调用

```bash
bash examples/run_example.sh
```

## 示意输出（实际运行得到，数据虚构）

1. `oplog init`：写入创世记录（prev=GENESIS）。
2. 六条操作留痕：scan（2 文件）、search（1 命中）、read×2（各带文件
   SHA-256）、decide（结论+依据）、verify。
3. `seal` 后 `journal_audit`：`{"entries": 8, "chain_ok": true,
   "untouched": 0, "pass": true}`——哈希链完整、两个输入文件均被日志
   触及、scan/search/verify/seal 阶段齐备。
4. `selfcheck`：result.json 与 output_contract 逐字段一致、case_id
   一致、status 合法 → `pass=true`。
5. `replay_pack`：replay/replay_steps.md（8 步人读重走步骤）+
   replay/manifest.json（4 个交付物的 SHA-256 清单）。

反例演示：seal 之后再追加一条日志，`journal_audit` 立即判
`pass=false`（"1 entries appended after seal"）——过程纪律由机器把守，
不靠自觉。
