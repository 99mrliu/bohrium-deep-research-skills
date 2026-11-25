# contract-mirror-assembler

文献筛选与智能排序（challenge-2dd1f64c）参赛 Skill 之一。**重心：下游交付合规**——从真实 case.json 发现 output_contract，逐字段镜像装配 result.json（case_id 回显、全记录覆盖、显式 null + 原因、诚实 partial），交付前脚本校验不过不交付。

## 文件

- `SKILL.md` — 调用契约、四步运行手册、预算纪律、异常处理。
- `scripts/contract_engine.py` — inspect / assemble / validate 三子命令，纯标准库，Python 3.8+。
- `references/contract-playbook.md` — 契约形态识别、字段装配策略、排序与平局协议、诚实 partial 规则、校验清单。
- `examples/minimal/` — 可运行的最小合成示例（含预期输出与退化路径），已标注为合成示例。
- `GITHUB_URL.txt` — 本作品的公开仓库地址。

## 依赖与运行

仅 Python 3 标准库，无安装步骤。三条命令完成一次筛选交付，见 SKILL.md 与 examples/minimal/README.md。

## 适用范围与限制

适用于平台固定案例（有限候选快照、全记录筛选、契约化交付）。不负责底层数据库接入与全文阅读；相关性语义判定由调用方按案例标注标准在批量一步完成，本 Skill 保证其交付形态合规、完整、可复核。维护信息：随本仓库版本演进，变更记录写入结果 `change_records`。
