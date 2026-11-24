# 最小调用示例（合成示例，非正式案例结果）

全部输入为**虚构合成数据**，仅演示接口与流程。本示例在编写过程中真实帮助修复了脚本的两个缺陷（标准编号解析缺 MULTILINE、日期与带时区时间戳做字典序比较），现行为已核验。

## 输入

- `input/protocol.md`：虚构筛选协议（2 纳入标准、3 排除标准、冻结时间 2026-11-24T10:00+08:00）；
- `input/screening_log.csv`：8 行虚构筛选日志，故意埋 4 处违例：R5 行 hold 缺 note、R6 行 exclude 未引用标准、R7 行引用不存在的 E9 且决策日期早于冻结；
- `input/screening_log_fixed.csv`：修复后的日志（修复动作写进 note 留痕）。

## 调用与预期输出（真实运行产生，已目检）

```bash
# 1. 协议结构检查 → 通过
python3 scripts/protocol_lint.py --protocol examples/input/protocol.md \
    --out examples/output/protocol_lint
# 退出码 0：{"passed": true, "fails": 0, "criteria": 5}

# 2. 机审含违例日志 → 拦下
python3 scripts/screening_audit.py --protocol examples/input/protocol.md \
    --log examples/input/screening_log.csv --out examples/output/screening_qc
# 退出码 1；4 条违例：hold 缺 note（R5）、exclude 未引用 E 类标准（R2）、
# 引用不存在编号（R4）、协议前决策（R6）
# PRISMA 计数：候选 8 → 纳入 2 / 排除 5 / 待定 1

# 3. 机审修复后日志 → 全绿
python3 scripts/screening_audit.py --protocol examples/input/protocol.md \
    --log examples/input/screening_log_fixed.csv \
    --out examples/output/screening_qc_fixed
# 退出码 0；PRISMA：候选 8 → 纳入 2 / 排除 6（E1×2、E2×3、E3×1）/ 待定 0
```

产物在 `examples/output/`：`protocol_lint.{json,md}`、`screening_qc.{json,md}`、`screening_qc_fixed.{json,md}`。
