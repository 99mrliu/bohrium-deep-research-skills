# protocol-freeze-screening-qc

过程质量控制取向的科研选题文献筛选 Skill：纳排标准编号化并声明冻结时间，筛选决策逐条留痕，脚本对照冻结协议机审并输出 PRISMA 式计数。详见 [SKILL.md](SKILL.md)。

## 文件

- `SKILL.md`：技能说明与运行时契约；
- `scripts/protocol_lint.py`：协议结构检查（冻结时间、编号唯一、标准可执行性）；
- `scripts/screening_audit.py`：筛选日志机审（R1–R6 违例规则）+ PRISMA 式流量计数；
- `references/protocol_format.md`：协议格式与修订纪律；
- `references/screening_log_format.md`：日志 CSV 格式与机审规则表；
- `examples/`：合成示例（含 4 处故意违例与修复版对照），见 `examples/minimal_example.md`。

## 依赖

Python 3.8+ 标准库，无安装步骤。

## 快速自检

按 `examples/minimal_example.md` 三条命令依次运行；预期退出码 0 / 1 / 0。
