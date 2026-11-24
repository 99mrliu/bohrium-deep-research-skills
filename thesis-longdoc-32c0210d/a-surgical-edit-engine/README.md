# surgical-edit-engine

学位论文与长文档**分章节工作稿**的手术式编辑执行引擎（Bohr Playground challenge-32c0210d 参赛 Skill，a 方向：编辑执行）。

**一句话**：把 `organizer-edit-workorder.json` 编译成确定性操作 DSL，由脚本事务式落改、自动验收、按 `output_contract` 原子装配 `result.json`；模型只处理编译器标记为 `manual` 的非机械改写。

## 流水线

```
workorder.json ──compile_workorder.py──▶ ops.json（term_unify / float_ref_fix / replace /
                                              delete / format_normalize / manual）
ops.json ──apply_ops.py──▶ 编辑后章节 + change_log.json（hunk 级：file/op_id/before/after/line_range，
                           锚点缺失记 problem 跳过、--dry-run 预览、--rollback 回滚）
章节 + workorder ──verify_acceptance.py──▶ acceptance_report.json（缺失/存在断言 +
                                          图表引用完整性，逐项 PASS/FAIL，非零退出）
case.json + 上述产物 ──make_result.py──▶ /app/output/result.json（运行时逐字段填充
                                          output_contract.fields，原子写，诚实 partial）
```

## 设计要点

- **机械操作零模型参与**：术语统一（含参考文献保护区与缩写定义同步）、图表引用编号纠错（题注集合 vs 正文引用差集，同章唯一候选自动改号）、明确新旧文替换/删除、数字-单位空格规范化，全部由脚本完成并留痕。
- **模型只做非机械判断**：识别不出的 item 编译为 `manual` op，保留 action 原文与 reason，由模型编辑工作副本后脚本重验。
- **先存 partial 再改进**：apply 之后立即装配一份 result.json，随后增量改进覆盖，超时也有诚实成果。
- **确定性可复现**：产物只含相对路径与行号，无绝对路径/时间戳；示例产物可由 `run_example.sh` 字节级复现。

## 目录

```
SKILL.md                 # 工作流与运行时契约（Harness Agent 直接照做）
scripts/                 # 4 个 python3 标准库脚本（无绝对路径写死，参数传路径）
references/ops_dsl.md    # 操作 DSL 字段与语义
references/editing_policy.md  # 脚本/模型分工与异常矩阵
examples/synthetic/      # 合成示例（自造"锌空气电池隔板"三章，非真实论文）
```

## 合成示例（非正式案例结果）

`examples/synthetic/` 的章节、数据、文献条目全部为**自造合成内容**，仅用于验证流程：

```bash
bash examples/synthetic/run_example.sh
```

一键跑通 compile → apply → verify → make_result，并与 `expected/` 逐字节对比。示例中埋了一个错误引用（正文引"图1-2"而题注是"图1-1"），由 `float_ref_fix` 自动修复；"隔膜→隔板"术语统一跳过参考文献条目。

## 依赖

python3（仅标准库）；可选 `pdftotext`（仅当输入为 PDF 时）。
