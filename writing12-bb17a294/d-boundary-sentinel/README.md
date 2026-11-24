# boundary-sentinel — 学术翻译与双语写作（写作12）

**核心定位：语义边界与引用保留（边界清 + 引用保留）。** 本 Skill bundle 让
agent 在英汉学术翻译中做到：源文中的每一个否定、模糊限定（hedge）、因果
强度动词、数量限定词、归属与引用标记都被抽取进"边界台账"
（boundary ledger），译文再经确定性脚本审计——限定词不丢、论断强度不
漂移、引用不丢不增不乱序、作者没说的绝不添加。数字、术语、对齐只在
change log 中一行带过（本 bundle 不复制 fact-ledger/termbase/alignment
机制）。

## 文件地图

```
d-boundary-sentinel/
├── SKILL.md                        # 技能定义：触发、工作流、运行时契约
├── README.md                       # 本文件
├── GITHUB_URL.txt                  # 仓库地址
├── scripts/                        # 纯 Python 3 标准库，无第三方依赖
│   ├── extract_markers.py          # 源文 → boundary_ledger.jsonl
│   ├── audit_boundary.py           # 台账 + 译文 → boundary_audit.json（有错非零退出）
│   ├── citation_check.py           # 源文 + 译文 → citation_report.json（有错非零退出）
│   └── cite_patterns.py            # 共享引用正则（被上述脚本 import）
├── references/
│   ├── method.md                   # 边界规则、hedge 映射表、[待确认] 流程
│   └── output_contract.md          # 如何填写 /app/output/result.json
└── examples/synthetic/             # 完全虚构的可运行示例（合成示例）
    ├── source.txt                  # 埋好全部标记的虚构英文源文
    ├── translation_zh.md           # 手写保真译文
    ├── boundary_ledger.jsonl       # 生成结果（12 条带标记记录）
    ├── boundary_audit.json         # 0 errors / 0 warnings（exit 0）
    ├── citation_report.json        # 3 文内引用 + 2 参考文献全部通过（exit 0）
    └── README.md
```

## 快速运行示例

```bash
cd d-boundary-sentinel
python3 scripts/extract_markers.py examples/synthetic/source.txt \
    -o examples/synthetic/boundary_ledger.jsonl
python3 scripts/audit_boundary.py examples/synthetic/boundary_ledger.jsonl \
    examples/synthetic/translation_zh.md -o examples/synthetic/boundary_audit.json
echo $?   # 0 = 无 error 级发现
python3 scripts/citation_check.py examples/synthetic/source.txt \
    examples/synthetic/translation_zh.md -o examples/synthetic/citation_report.json
echo $?   # 0 = 引用完整
```

## 工作流一句话

读案件（case.json/task.md）→ 抽取边界台账 → agent 翻译 →
边界审计 + 引用审计 → 未决项进入 [待确认] 队列并记入 change_log.md →
按真实 output_contract 交付 result.json。脚本为召回导向的启发式工具：
负责"标出来让人核对"，不作正确性证明；所有发现最终由 agent/人裁决。
