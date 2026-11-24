# 最小调用示例（合成数据，非正式案例）

`case/`：合成土壤汇总表（6 行）——μg/kg 与 mg/kg 混写、`ND` 缺失码、1 行
完全重复；配套合成工单、台账、质量报告、证据映射。数据为人工编造。

## 真实运行过的命令（`$SK` = 本技能根目录）

```bash
python3 $SK/scripts/snapshot_freeze.py case/raw_soil.csv --out work/frozen
python3 $SK/scripts/audit_run.py --raw case/raw_soil.csv \
    --cleaned case/cleaned_soil.csv --ledger case/ledger.csv \
    --key plot_id,analyte --manifest work/frozen/manifest.json \
    --report case/quality_report.json --workorder case/workorder.md \
    --evidence-map case/evidence_map.json --evidence-root case \
    --out work/audit        # 退出码 0 = 过门
```

## 真实运行产物（`expected/`）

| 文件 | 内容 |
|---|---|
| `frozen_manifest.json` | 输入冻结清单（路径/字节数/sha256） |
| `audit_verdict_pass.json/md` | 8 项检查全部 PASS：行列对账 6=5+1、换算逆运算 45000×0.001=45 成立、报告数字一致、工单 4 条全覆盖 |
| `audit_verdict_fail_tampered.json` | 负向实测：把 cleaned 中 pH 6.5 手改为 6.9（无台账），检查 C `no_silent_edits` 立即抓获并定位到键 `p-01␟ph`、字段 `conc`、原值 6.5→改后 6.9，退出码 5 |

要点：审计器不读清洗代码、只核对产物与原始件；任何静默改动都会被检查 C
定位到"键+字段+原值+改后值"。
