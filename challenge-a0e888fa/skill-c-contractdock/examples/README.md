# 最小调用示例（合成数据，非正式案例）

`case/`：合成案例——`case.json`（含嵌套 output_contract，9 个字段）、
`raw.csv`（5 行，含 μg/L 混写、-999 哨兵、1 行完全重复）、以及模拟清洗完成的
`cleaned.csv` 与 `ledger.csv`。数据为人工编造，不对应任何真实案例。

## 真实运行过的命令（`$SK` = 本技能根目录）

```bash
python3 $SK/scripts/contract_extract.py --case case/case.json \
    --out work/contract --scaffold-out out/result.json
python3 $SK/scripts/report_build.py --cleaned case/cleaned.csv \
    --ledger case/ledger.csv --raw case/raw.csv --out out/report
# （把报告路径与重算数字回填 result.json，status 置 success）
python3 $SK/scripts/contract_verify.py --contract work/contract/contract.json \
    --result out/result.json --output-dir out \
    --report out/report/quality_report.json \
    --cleaned case/cleaned.csv --ledger case/ledger.csv --raw case/raw.csv \
    --out work/verify        # 退出码 0 = PASS
```

另做过一次负向实测：从 result.json 删除 `ledger` 字段并把 `summary.rows_out`
改为 99，验收立即 FAIL（`contract_fields_present` 与
`result_numbers_consistent` 两项被拦下，退出码 5）。

## 真实运行产物（`expected/`）

| 文件 | 内容 |
|---|---|
| `contract.json` | 规范化合同：9 个字段的路径/类型/是否必填 |
| `result.json` | 填完的交付物（含 summary 四个数字，全部来自重算） |
| `report/quality_report.json` / `.md` | 重算的质量报告：行 5→4、台账 4 条、逐动作统计 |
| `report/report_preview.svg` | 字段级问题条形图（纯 SVG，浏览器直接打开） |
| `verify_verdict.json` | 7 项验收全部 PASS |
