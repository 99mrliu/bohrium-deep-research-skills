# result-contract-replay-compiler

下游交付与可复跑工程 Skill（Bohrium Playground 挑战「专利与技术文献检索」challenge-ad3e9357，
bundle e-contract-replay-compiler）。

本 bundle 是交付"最后一公里"的执行机器：**result.json 契约镜像与校验 + 可复跑证据包 + 人类可读复核报告**。
不负责号码解析、查询构造、引文台账或许可分级（其他 bundle 的职责）。

## 组成

| 路径 | 作用 |
| --- | --- |
| `scripts/scaffold_result.py` | 从任意 case.json 提取 case_id + output_contract，生成诚实 partial 脚手架；`--fill` 深度合并并同步 uncertainty / change_records |
| `scripts/contract_validate.py` | V1–V6 契约校验（case_id 一致 / 字段齐备 / status 自洽 / 来源完整 / 编造标记 / 变更记录），输出逐条报告 |
| `scripts/replay_pack.py` | `log`（带 SHA-256 的运行日志）→ `pack`（replay manifest）→ `verify`（fresh/stale/missing-input 复跑核验） |
| `scripts/report_render.py` | 渲染中文复核报告 review.md（六章节，纯 stdlib） |
| `scripts/selfcheck.py` | 端到端自检：37 项断言，全过 exit 0 |
| `references/contract_fields.md` | 契约镜像语义、status 判定标准、uncertainty/change_records/sources 写法 |
| `references/replay_protocol.md` | run log 格式、manifest 结构、fresh/stale 定义、第三方复跑指引 |
| `examples/example_walkthrough.md` | 完整可走查示例（真实命令 + 示意输出，合成示例） |
| `examples/fixtures/` | 合成 fixtures（虚构标记齐全）：正常案例、fill、两个反例、示例 run log |

## 快速开始（真实命令，在 skill 根目录执行）

```bash
W=/tmp/rcrc-demo; mkdir -p "$W"

# 1) 脚手架（第一分钟落地诚实 partial）
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json \
    --out "$W/output" --note "初始脚手架"

# 2) 合并填充
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json \
    --out "$W/output" --fill examples/fixtures/fill.json --note "填入候选与来源"

# 3) 契约校验（exit 0）
python3 scripts/contract_validate.py --case examples/fixtures/case_fixture.json \
    --result "$W/output/result.json" --out "$W/output/validate_report.json"

# 4) 运行日志 → manifest → 核验
python3 scripts/replay_pack.py log --runlog "$W/run_log.jsonl" \
    --cmd "scaffold+fill" --inputs examples/fixtures/case_fixture.json examples/fixtures/fill.json \
    --outputs "$W/output/result.json" --workdir "$W"
python3 scripts/replay_pack.py pack --runlog "$W/run_log.jsonl" --out "$W/replay_manifest.json"
python3 scripts/replay_pack.py verify --manifest "$W/replay_manifest.json"

# 5) 渲染复核报告
python3 scripts/report_render.py --result "$W/output/result.json" \
    --manifest "$W/replay_manifest.json" --out "$W/review.md"

# 6) 自检（37 项断言）
python3 scripts/selfcheck.py
```

各命令的预期输出见 `examples/example_walkthrough.md`（示意输出，合成示例）。

## 约定

- 仅依赖 python3 标准库（3.8+）；退出码：`0` 成功，`1` 校验失败，`2` 用法/输入错误。
- fixtures 全部为**合成示例 / 虚构数据**，仅用于演示与自检。
- 运行时契约（/input、/app/work、/app/output、64 请求 / 900 秒预算、首分钟 partial 落地）见 `SKILL.md`。
