# 最小调用示例（合成示例，非正式案例结果）

本示例的全部输入为虚构合成数据，仅用于演示接口与流程，不冒充正式案例结果。
`examples/output/` 下的产物是上述合成输入在本地真实执行脚本得到的真实输出。

## 输入（examples/input/）

- `text/paper_a.txt`、`text/paper_b.txt`：2 份合成来源（虚构 RCT
  与虚构队列研究）；
- `claims.json`：3 条论断——C1 与原文一致；C2 数字错位（论断写
  1.6，原文为 1.8）；C3 方向反转（论断写"升高"，原文为"下降"）；
- `claims_meta.json`：研究设计登记（C1=cohort n=80；C2/C3=rct n=120）；
- `draft.md`：合成草稿，C1 句使用了"证据表明"（超出 C 级允许措辞）。

## 调用

```bash
python3 scripts/align_check.py examples/input/claims.json \
  examples/input/text /tmp/d-align.json --report /tmp/d-align.md
python3 scripts/strength_map.py --meta examples/input/claims_meta.json \
  --draft examples/input/draft.md --out /tmp/d-strength.json \
  --report /tmp/d-strength.md
```

## 输出（examples/output/，本地真实运行所得）

- `d-align.json` / `d-align.md`：C1 supported（anchored）；C2
  NUMERIC-MISMATCH:1.6 → failed → 论断 unsupported；C3
  DIRECTION-CONFLICT:claim=up,quote=down → failed → unsupported；
  汇总 1 supported / 2 unsupported，退出码 1；
- `d-strength.json` / `d-strength.md`：C1=C 级、C2/C3=B 级；
  C1 草稿句命中"证据表明"（C 级禁用）判 OVERSTATED，退出码 1；
  报告同时给出各等级允许措辞供改写。

正式流程中，C2/C3 的论断须修复证据或删除后才允许成稿，C1 句须
改写为"一项队列研究提示"后复验至退出码 0。
