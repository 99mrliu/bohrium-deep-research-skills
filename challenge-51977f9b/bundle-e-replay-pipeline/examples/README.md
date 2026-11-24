# examples/ — 合成示例（synthetic, illustrative）

**本目录全部数据为合成示例 / synthetic, illustrative**：题录为虚构记录，研究问题仅用于
演示，不构成任何真实医学结论，也不是正式评测案例的结果。

## 内容

| 路径 | 说明 |
|---|---|
| `input/case.json`、`input/task.md` | 合成案例：益生菌对抗生素相关性腹泻（AAD）的预防效果 |
| `input/records.json` | 8 条合成题录，含 2 条重复（R05≡R01，R08≡R03 仅大小写差异） |
| `pipeline/step1_dedupe.py` | 步骤1：去重（规范化标题+年份为键），8 → 6 |
| `pipeline/step2_screen_count.py` | 步骤2：题录级筛选（玩具条款 E1 非 RCT / E2 人群不符）→ 排除 2，进入全文 4 |
| `pipeline/step3_freeze.py` | 步骤3：全文级筛选（全文不可得排除 1）→ 冻结纳入 3 篇 + 生成 flow.json |
| `flow.json` | 合规计数版：8 − 2 = 6；6 = 2 + 4；4 = 1 + 3，全部轧平 |
| `negative/flow_broken.json` | 埋雷负例：screened=100 但 85+13=98，F2 失衡 diff=2 |
| `expected/included.json` | 期望产物：冻结纳入清单（R01、R02、R03） |
| `run_example.sh` | 一键跑通：流水线 → runlog 登记 → reconcile → verify → replay |
| `run/` | `run_example.sh` 的真实运行产物（runlog.jsonl、manifest.json、各中间产物、replay/ 重放目录），可随时删除后由脚本重新生成。注意：run/manifest.json 中的 cmd 使用相对路径，仅在 `--workdir run/replay` 下可直接重放；换目录需相应调整 cmd 中的相对路径（replay 会以 V3 报出命令失败步骤） |

## 运行

```bash
# 正例（全程预期 exit 0）
bash examples/run_example.sh
# 关键输出：reconcile: 全部轧平；verify: 6 个登记文件全部一致；replay: 3 identical, 0 differ

# 负例：计数轧不平（预期 exit 3，输出指名 F2）
python3 ../scripts/reconcile.py --flow negative/flow_broken.json

# 全流程正负例断言（预期 exit 0）
python3 ../scripts/selfcheck
```

## 预期 exit 码

| 操作 | 预期 exit |
|---|---|
| run_example.sh 全程 | 0 |
| reconcile --flow flow.json | 0 |
| reconcile --flow negative/flow_broken.json | 3（指名 F2） |
| runlog verify（run/runlog.jsonl，未篡改时） | 0 |
| 篡改 run/ 任一产物后 runlog verify | 3（指名步骤与文件） |
| replay --manifest run/manifest.json --workdir run/replay --runlog run/runlog.jsonl | 0（3 identical, 0 differ） |
| selfcheck | 0 |
