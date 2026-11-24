# 最小调用示例（合成示例，非正式案例结果）

本示例的全部输入为虚构合成数据，仅用于演示接口与流程，不冒充正式案例结果。
`examples/output/` 与 `examples/input/pack/verification_manifest.json`
是上述合成输入在本地真实执行脚本得到的真实输出。

## 输入（examples/input/）

- `pack/`：迷你可交付包——`result.json`（case_id=`SYNTH-DEMO-0005`，
  含契约键 deliverable/evidence_table 等）、`deliverable.md`
  （含〔C1〕〔C2〕标记与 [1][2] 引文的合成成稿）、
  `verification_manifest.json`（pack_manifest.py 真实生成）；
- `evidence_pack.json`：2 条逐字摘录、2 个关键数字、2 条虚构文献；
- `text/paper_a.txt`、`text/paper_b.txt`：合成来源文本（模拟复核方
  自提取的来源）。

## 调用

```bash
python3 scripts/pack_manifest.py --output-dir examples/input/pack \
  --manifest examples/input/pack/verification_manifest.json \
  --evidence examples/input/evidence_pack.json
python3 scripts/verify_pack.py --output-dir examples/input/pack \
  --sources examples/input/text \
  --manifest examples/input/pack/verification_manifest.json \
  --report /tmp/verify_report.md
```

## 输出（examples/output/，本地真实运行所得）

- `verify_report_pass.md`：15 项检查全 PASS（2 HASH + 2 QUOTE +
  2 NUMBER + 2 REF + 7 CONTRACT），退出码 0；
- `verify_report_tampered.md`：篡改演示——打包后向 deliverable.md
  追加一句话再重验，`HASH:deliverable.md` FAIL（"文件在打包后被
  改动"），退出码 1。说明任何打包后改动都会被独立复核发现，必须
  重新生成 manifest。
