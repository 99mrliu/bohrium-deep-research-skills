# 最小调用示例（合成示例，非正式案例结果）

本示例的全部输入为虚构合成数据，仅用于演示接口与流程，不冒充正式案例结果。
`examples/output/` 下的产物是上述合成输入在本地真实执行脚本得到的真实输出。

## 输入（examples/input/）

- `case.json`：合成案例，case_id=`SYNTH-DEMO-0001`，声明了两个材料文件；
- `task.md`：合成任务（200 字摘要 + 证据表）；
- `sources/paper_a.txt`：合成论文 A（虚构随机对照试验摘要）；
- `sources/paper_b.txt`：合成论文 B（虚构综述）；
- `sources/paper_c_corrupt.txt`：刻意含有 300 个替换字符的损坏文件，
  用于演示 DEGRADED 分级。

## 调用

```bash
python3 scripts/material_forensics.py examples/input /tmp/mf-work \
    --case examples/input/case.json
printf '%s' '治疗后 8 周，试验组空腹血糖较基线下降 1.8 mmol/L' > /tmp/q.tmp
python3 scripts/locate_quote.py /tmp/mf-work /tmp/q.tmp \
    --source sources_paper_a
```

## 输出（examples/output/，本地真实运行所得）

- `sources_registry.json`：5 个文件登记，paper_a / paper_b 为 OK，
  paper_c_corrupt 因乱码率 >1% 判为 DEGRADED；declared_hints 列出
  case.json 声明的两个文件名，可据其对账（paper_c_corrupt 存在但未声明，
  正式流程中应记入 change_log）；
- `material_report.md`：人读清单与分级结论；
- `locate_quote_result.json`：摘录在 sources_paper_a 第 1 页命中
  （found=true），正式流程中该页码直接回填证据表。

退出码：第一条 0（有可用来源），第二条 0（命中）。若摘录改为原文中
不存在的句子，第二条返回 `found=false`、退出码 1——该摘录即不得作为
逐字证据进入成稿。
