# examples — 合成示例（SYNTHETIC）

**本目录全部内容为合成示例：`synthetic_excerpt.txt` 是完全虚构的教学样例，
不对应任何真实研究；其中“植入错误”均为故意埋入，用于校验重算管线。**

## 文件

| 文件 | 说明 |
|---|---|
| `synthetic_excerpt.txt` | 虚构的结果小节（合成示例），含 3 个植入错误 |
| `run_example.sh` | 一键运行：statmath 自检 → 抽取 → 重算 |
| `expected_output/stats.jsonl` | 真实运行产物：抽取到的 8 条统计量 |
| `expected_output/findings.jsonl` | 真实运行产物：3 条发现 |

## 植入错误与预期结果

| 位置 | 内容 | 预期判定 |
|---|---|---|
| F(2, 125) = 3.05, p = .047 | 重算 p ≈ .051 | critical / 显著性翻转 |
| HR = 0.65, 95% CI [0.40, 1.05], p = .040 | CI 跨 1 却报显著 | critical / CI↔p 矛盾 |
| 23/45 (45.0%) | 实为 51.1% | major / 百分比不自洽 |
| t(126) = 2.45, p = .016 | 正确 | 不产生发现 |
| χ²(1) = 4.20, p = .040 | 正确 | 不产生发现 |
| r(124) = 0.24, p = .007 | 正确 | 不产生发现 |
| 52.3 ± 11.4 / 51.8 ± 10.9 | 正确（SD 标记） | 不产生发现 |

## 运行

```bash
bash examples/run_example.sh
```

管线是确定性的：重跑会原位重新生成 `expected_output/`，内容应保持一致。
