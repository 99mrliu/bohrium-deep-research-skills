# examples/expected — 预期副本说明

**合成示例（synthetic），非正式案例结果。**

本目录的 4 个 JSON 是在一台 macOS/arm64 机器上执行 `examples/run_example.sh`
得到的真实输出副本，仅用于对照字段结构与判定方向：

| 文件 | 对应产物 | 预期要点 |
|------|----------|----------|
| `code_audit_stable.json` | 对 `examples/input/method_stable.py` 的 code_audit | `rng_calls` 为空、无告警 |
| `code_audit_unseeded.json` | 对 `examples/input/method_unseeded.py` 的 code_audit | `rng_calls` 命中第 12 行 `random.random`，`seeded=false`，告警"未播种 RNG" |
| `determinism_report_stable.json` | stable 重放 3 次 | `verdict` 为 `identical`（或 `numerically_stable`） |
| `determinism_report_unseeded.json` | unseeded 重放 3 次 | `verdict` 为 `unstable`，`artifacts.result_unseeded.txt.identical=false`（各次 sha256 不同） |

注意：其中的绝对路径、`wall_time_seconds`、unseeded 的具体随机数值与 sha256
哈希随机器与运行而变，**逐字段相等不是预期**；只需 verdict、告警与字段结构一致。
