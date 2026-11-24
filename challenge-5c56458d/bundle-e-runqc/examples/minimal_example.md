# 最小调用示例（合成示例，非正式案例结果）

> 本示例使用**合成数据**（脚本现场生成的合成 case 与合成库），仅说明
> 接口与流程，不冒充平台正式案例的运行结果。

## 合成输入

`run_example.sh` 现场生成：

- `input/case.json`：合成案例（case_id=demo-synthetic-001，三字段
  output_contract）。
- `work/plan.json`：三步门禁计划（G1 建库 → G2 统计 → G4 填 result.json）。

## 调用方式

```sh
sh examples/run_example.sh
```

## 示意输出（示例，非正式结果）

- bootstrap：立即写出 `output/result.json`（status=partial，三个 contract
  字段以 unable_to_determine 占位）。
- gate 第一次运行：三步依次通过，日志与 checkpoint 落盘。
- gate 第二次运行：全部步骤 `skipped (checkpoint)`——演示断点续跑不重做。
- selfcheck：C1–C7 全过，判定 **GO**；最终 result.json 为 complete，
  含合成统计结果、evidence 指向 stats.json、limitations 声明为合成演示。

## 预期运行环境

Python 3.9+，仅标准库；产物写入 mktemp 目录。
