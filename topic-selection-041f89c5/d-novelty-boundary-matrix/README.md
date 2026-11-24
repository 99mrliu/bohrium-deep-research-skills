# novelty-boundary-matrix

创新边界判定取向的科研选题评估 Skill：创新陈述四分类（方法/数据/场景迁移/结论修正），与已有工作逐格 covers/partial/none 对账，脚本强制判定规则（covers 必须有锚点、uncovered 必须有检索边界声明），产出覆盖矩阵与划界备忘录。详见 [SKILL.md](SKILL.md)。

## 文件

- `SKILL.md`：技能说明与运行时契约；
- `scripts/novelty_matrix.py`：覆盖矩阵构建 + V1–V4 判定 + X1–X3 一致性检查；
- `references/claim_format.md`：claims.json 格式与四分类判定线索；
- `references/boundary_rules.md`：对账格式、判定规则表与语义边界；
- `examples/`：合成示例（含违例对照），见 `examples/minimal_example.md`。

## 依赖

Python 3.8+ 标准库，无安装步骤。

## 快速自检

按 `examples/minimal_example.md` 两条命令运行；预期退出码 0 / 1。
