# Bundle A — 证据锚定与上游数据真实性审查（veracity-anchored-feasibility-audit）

Bohrium Playground 挑战「实验方案可行性评估」（challenge-2e2c5820）的参赛 Skill 包。
重心是**上游数据真实性与证据锚定**：杀掉"方案没写 X 就当 X 满足"、无锚定断言、
章节/版本间矛盾无人察觉这三类评审失真。

## 机制

1. `build_plan_index.py`：把 case.json 里的候选方案文本索引成 plans.json + 行偏移索引 +
   素材清单 materials.json（含 JSON 路径溯源）。
2. 模型逐类产出证据台账 evidence.jsonl，**每条判定携带逐字引文**。
3. `verify_anchors.py`：确定性校验引文确为原文子串，计算 char/line 偏移；
   无法锚定的一律拒绝（exit 2），修复后重跑；missing 必须带 absence_scope。
4. `scan_contradictions.py`：启发式抽取数值提及（值+单位+上下文），标记方案内矛盾与
   跨版本差异。
5. `assemble_result.py`：按 case.json 的 output_contract（容忍 list/dict/properties 形态）
   装配 result.json，保证契约字段齐全，诚实记录 status / sources / uncertainty /
   change_record。

## 布局

```
SKILL.md                     技能入口（YAML frontmatter + 中文工作流）
GITHUB_URL.txt               仓库地址
scripts/                     4 个 stdlib-only 脚本
references/evidence_schema.md  证据模式、五状态语义、铁律、absence_scope 指南
references/audit_protocol.md   7 约束清单、门槛项、四级结论分级规则
examples/synthetic/            合成示例（非正式案例数据）+ run_example.sh 一键复现
```

## 快速验证

```bash
cd examples/synthetic && sh run_example.sh
```

预期：4 个脚本顺序执行全部退出 0，output/ 下生成 plans.json、anchors_verified.json、
contradictions.md（含人为埋入的 58°C/60°C 矛盾）、result.json。

## 约束

全部文件 UTF-8 纯文本；脚本仅依赖 Python 3 标准库、无网络、接受绝对路径、
任意 cwd 可运行；参数错误以非零退出码报清晰用法信息。
