# identity-reconciliation-court

跨库文献去重与论文身份合并 Skill（Playground challenge-60a8202d「引文追踪与关联文献发现」v2 五件套之 v2-c）。

给定多个文献数据库导出（Crossref / EuropePMC / OpenAlex / 通用 JSON / JSONL / CSV / BibTeX），本 Skill 用
blocking + 成对打分 + 阈值裁决识别同一论文的不同版本（预印本/会议版/期刊版/增补版），
显式区分「同名不同文」与「同文不同名」，交付干净实体清单与可回指复核的合并证据台账；
再在合并后的实体图上做 1–2 层引用扩展，输出镜像 `output_contract` 全字段的 `result.json`。

## 运行

```bash
python3 scripts/identity_merge.py --roots /input --workdir /app/work
python3 scripts/run_case.py --case /input/case.json --workdir /app/work --out /app/output --layers 2
python3 scripts/audit_merge.py --case /input/case.json --workdir /app/work --out /app/output
```

仅用 Python 3 标准库；默认离线；脚本位置无关（`pathlib`）。

本地跑合成示例：

```bash
python3 scripts/identity_merge.py --roots examples/corpus --workdir examples/run_out
python3 scripts/run_case.py --case examples/case.json --workdir examples/run_out --out examples/run_out --layers 2
python3 scripts/audit_merge.py --case examples/case.json --workdir examples/run_out --out examples/run_out
```

## 目录结构

```
SKILL.md                     Skill 定义（frontmatter + 运行契约 + 异常表 + 自查）
README.md                    本文件
GITHUB_URL.txt               提交用 GitHub 链接
scripts/
  identity_merge.py          语料解析 + blocking + 打分 + 阈值裁决 + 版本谱系 + 台账
  run_case.py                实体图 1–2 层扩展 + result.json / merge_report.md
  audit_merge.py             交付前自查（ok=true/false，退出码 0/1）
references/
  dedup_keys.md              blocking 键与成对打分表
  version_lineage.md         版本谱系信号与裁决规则
examples/
  case.json / task.md        合成最小案例契约与任务说明
  corpus/                    3 个跨库风格 JSON（8 条虚构记录）
  walkthrough.md             合成示例端到端走查说明
  run_out/                   一次真实端到端运行的产物（合成示例输出）
```

## 合成示例声明

`examples/` 下全部文献与 DOI（形如 `10.0000/synth.*`）均为**虚构**，仅为演示管线行为；
**SYNTHETIC, not real papers, 非正式案例结果**，不冒充任何真实文献或正式评测结果。
`examples/run_out/` 是作者在本机真实运行三条命令后保留的小型产物，用于说明预期输出形态。
