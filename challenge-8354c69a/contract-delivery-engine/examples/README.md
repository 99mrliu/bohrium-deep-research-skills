# 最小示例（合成示例，非正式案例结果）

演示交付工程闭环：scaffold → 部分填写 → lint 失败（L2 字段缺失 + L3 缺定位）
→ 补齐 → lint 通过 → 渲染 report.md 与 summary.png。全部数据为**合成示例**。

## 运行

```bash
cd examples
bash run_example.sh
```

## 预期（captured 于 expected/）

- 第一次 lint 非零退出并列出 L2/L3 失败项；
- 补齐后 `LINT PASS`；
- demo/output/ 含 result.json、report.md、summary.png（matplotlib 可用时）。

`expected/` 为一次真实本地运行的输出副本。
