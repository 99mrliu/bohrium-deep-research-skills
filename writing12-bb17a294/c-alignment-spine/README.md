# alignment-spine —— 学术翻译与双语写作（对齐主干）

本 Skill bundle 面向 Bohrium Playground 挑战「写作12｜学术翻译与双语写作」
（EN↔ZH）。核心重心是**双语对齐与结构对等（对得齐）**：为源文每个段落/
题注/脚注/公式/文献条目分配稳定分段 ID 主干（`⟦S0001⟧ …`），双语母本
按主干逐段对译，脚本校验 1:1 对齐与结构完整性，纯净译文由双语母本
**派生**（绝不重译）。

数字核对、术语一致性、边界声明只做轻量记录（见 SKILL.md 与
change_log），不重复造事实台账/术语库机制。

## 文件地图

```
c-alignment-spine/
├── SKILL.md                        # Skill 主文件：目的、触发、五阶段流程、运行时约定
├── README.md                       # 本文件
├── GITHUB_URL.txt                  # 仓库地址
├── scripts/                        # Python 3 标准库实现，无第三方依赖、无网络
│   ├── segment_source.py           #   源文分段 + 稳定 ID + structure_inventory.json
│   ├── check_alignment.py          #   双语母本对齐校验 → alignment_report.json
│   └── derive_target.py            #   由母本派生纯净译文 + 覆盖率核验
├── references/
│   ├── method.md                   # 双语配对块格式规范、分段规则、派生原则、人工后编辑
│   └── output_contract.md          # 如何如实填写 /app/output/result.json
└── examples/
    └── synthetic/                  # 完全合成的最小工作示例（含复现命令）
        ├── source.md
        ├── source_segments.txt     # 生成物
        ├── structure_inventory.json# 生成物
        ├── bilingual.md            # 手写中文译文母本
        ├── alignment_report.json   # 生成物（11/11 ok, pass）
        ├── translation_target.md   # 生成物（派生译文，覆盖率 100%）
        └── README.md
```

## 如何运行示例

```bash
cd c-alignment-spine
python3 scripts/segment_source.py examples/synthetic/source.md
python3 scripts/check_alignment.py examples/synthetic/bilingual.md \
    examples/synthetic/source_segments.txt \
    --json examples/synthetic/alignment_report.json   # 期望 exit 0
python3 scripts/derive_target.py examples/synthetic/bilingual.md \
    --segments examples/synthetic/source_segments.txt \
    --inventory examples/synthetic/structure_inventory.json \
    -o examples/synthetic/translation_target.md       # 期望 exit 0
```

详见 `examples/synthetic/README.md` 与 `references/method.md`。
