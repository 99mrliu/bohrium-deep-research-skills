# 最小调用示例（合成示例，非正式案件结果）

演示"普查 → 差异 → 声明覆盖"闭环。**全部输入由 make_fixture.py 现场合成
（三个手写最小 DOCX）；expected/ 下为合成示例的真实运行产物，仅示意接口。**

## 运行

```bash
python3 examples/make_fixture.py
python3 scripts/census.py examples/work/source.docx      --out examples/work/census_src.json
python3 scripts/census.py examples/work/adapted.docx     --out examples/work/census_adp.json
python3 scripts/census.py examples/work/adapted_bad.docx --out examples/work/census_bad.json
# 正路：声明改动被覆盖
python3 scripts/census_diff.py examples/work/census_src.json examples/work/census_adp.json \
    --out examples/work/diff_ok.json                                  # 退出码 1（有差异）
python3 scripts/change_ledger.py init examples/work/ledger.json
python3 scripts/change_ledger.py add examples/work/ledger.json --unit "unit 1" \
    --before "0.85" --after "0.86" --reason "任务要求按复核后数值更新转化率"
python3 scripts/change_ledger.py verify examples/work/ledger.json examples/work/diff_ok.json   # 退出码 0
# 反路：事故产物被拦截
python3 scripts/census_diff.py examples/work/census_src.json examples/work/census_bad.json \
    --out examples/work/diff_bad.json                                 # 退出码 1
python3 scripts/change_ledger.py verify examples/work/ledger.json examples/work/diff_bad.json  # 退出码 1
```

## 本示例实测结果（2026-11-24 真实运行）

- 普查：source.docx 抽出 5 个文本单元、3 类对象（表格 1、脚注引用 1、脚注 1）、
  7 个数字 token、1 个引用 token。
- 正路：adapted.docx 与源稿 3 处差异（单元 1 文本、0.85 减、0.86 增），
  一条账本声明全覆盖 → COVERED（退出码 0）。
- 反路：adapted_bad.docx 共 6 处差异；同一份账本只覆盖声明过的 0.85→0.86，
  其余 3 处被裁决 UNDECLARED_CHANGES（退出码 1）：整段静默删除（unit_count）、
  单元 2 的 3 次→5 次篡改、单元 3 的连带文本错位——精确定位到单元号。

expected/ 内容：diff_ok/diff_bad 报告、两份 coverage 裁决、声明账本 ledger.json。
