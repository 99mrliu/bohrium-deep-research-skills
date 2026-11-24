# delivery-forge — 学术翻译下游交付与渲染工程 Skill

面向 Bohrium Playground 挑战 **写作12｜学术翻译与双语写作**（EN↔ZH）的独立
Skill bundle。重心在**下游交付与渲染工程 + 过程质量门**：把双语主文档变成
评审可直接打开的交付物，并用真实 PDF/PNG 预览、结构完整性普查、输出合同校验
三道闸门证明质量。数字核对、术语库、对齐与边界记录只作一行提示，由上游机制
负责，本包不重复造轮子。

## 文件地图

```
e-delivery-forge/
├── SKILL.md                        # Skill 主文件（frontmatter + 全流程 + 运行时契约）
├── README.md                       # 本文件
├── GITHUB_URL.txt                  # 仓库地址
├── scripts/
│   ├── render_bilingual.py         # 双语主文档 → 自包含 HTML + 真实 PDF/PNG 预览 + QA 日志
│   ├── census_coverage.py          # 结构清单 vs 交付物 → coverage_report.json（缺失即非零退出）
│   └── validate_contract.py        # 按 case 实际 output_contract 校验 result.json
├── references/
│   ├── method.md                   # 主文档格式、交付物矩阵、预览策略、质量门顺序、字体发现
│   └── output_contract.md          # result.json 填写规范、早期部分保存、原子更新
└── examples/synthetic/             # 合成示例（全流程实际输出，PDF/PNG 为运行时产物不入包）
    ├── bilingual_master.md
    ├── structure_inventory.json
    ├── case.json
    ├── README.md
    └── output/ (bilingual_master.md, bilingual.html, result.json, change_log.md,
                 render_qa_log.json, coverage_report.json, contract_check.json)
```

## 运行示例

```bash
cd examples/synthetic
cp bilingual_master.md output/bilingual_master.md
python3 ../../scripts/render_bilingual.py --master bilingual_master.md --outdir output --basename bilingual
python3 ../../scripts/census_coverage.py --inventory structure_inventory.json \
    --deliverable output/bilingual_master.md --report output/coverage_report.json
python3 ../../scripts/validate_contract.py --case case.json --outdir output
```

期望输出：`previews=generated`（matplotlib 可用时）→ `census: PASS — 7/7` →
`contract: PASS`。详见 `examples/synthetic/README.md`。

## 技术要点

- 核心逻辑仅用 Python 3 标准库；matplotlib 仅用于预览渲染，缺失时诚实降级
  （QA 日志记录原因，退出码仍为 0，绝不伪造预览）。
- CJK 字体按路径扫描发现（macOS PingFang/STHeiti、Linux Noto Sans CJK /
  WenQuanYi、Windows msyh），找不到则回退默认字体并写入 `font_warning`。
- 合同校验不假设固定 schema：字段名从 case 文件实际读取；无显式合同时使用
  文档化的回退字段集。
