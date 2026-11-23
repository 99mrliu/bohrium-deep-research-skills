# 最小调用示例运行记录（合成示例，非正式案例结果）

> 本示例使用 `synthetic-case.json`（虚构论文 SYN-2026-Photocat-07，8 个段落、2 个中文问题），
> 仅用于演示接口与完整流程；输出不代表任何正式案例的成绩。

## 环境

Python 3.12（仅标准库），macOS；任何 Python ≥3.10 环境均可复现。

## 命令序列（已真实执行）

```bash
mkdir -p work/input work/app/work work/app/output
cp examples/synthetic-case.json work/input/case.json

# 1) 解析 + 完整性审计 + 骨架落盘
python3 scripts/source_ledger.py audit --case work/input/case.json --work work/app/work --out work/app/output
# stdout: audit ok: 8 paragraphs, 0 flagged, 2 questions -> work/app/work

# 2) 读 inventory.md 与 case_norm.json（人工/模型步骤，略）

# 3) 读取留痕（全部 8 段均读）
python3 scripts/source_ledger.py mark --work work/app/work --read "P1,P2,P3,P4,P5,P6,P7,P8"
# stdout: ledger total read: 8

# 4) 机械生成 coverage
python3 scripts/source_ledger.py coverage --work work/app/work --reason "无（全部段落均已读取）"
# stdout: {"read_sections": ["P1", ..., "P8"], "unread_sections": []}

# 5) 模型依据 case_norm.json 写出 result.json（本仓库内对应文件：result.synthetic.json），
#    并复制到 /app/answers.json

# 6) 机器校验
python3 scripts/source_ledger.py check --case-norm work/app/work/case_norm.json --result work/app/output/result.json
# stdout: check done: 0 error(s), 0 warn(s)；exit=0
```

## 中间产物（节选）

`inventory.md`：

```
| 段落编号 | 类别 | 字符数 | SHA-8 | 完整性标记 |
| P1 | abstract | 155 | 81e2aa2b | - |
| P2 | body | 178 | d25cd5ff | - |
| ... | ... | ... | ... | ... |
| P8 | reference | 131 | 4d26a952 | - |
共 8 段；完整性异常 0 段。
```

## 异常路径验证（已真实执行）

- `audit --case /nonexistent.json` → 退出码 2，`result.json` 如实写
  `status=input_error`、`input_error` 字段含具体原因，`answers` 为空。
- 非法 JSON 输入 → 退出码 2，同样落 input_error 骨架。
- 把某条 quote 改成不逐字的文本后 `check` → 退出码 1，
  输出 `ERROR: Q1/Q1-C1: 引文逐字校验失败（P2）`。

## 最终产物

`result.synthetic.json`：本次合成示例运行的真实输出，`check` 通过（0 error / 0 warn）。
