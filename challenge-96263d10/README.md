# challenge-96263d10 学术格式与模板适配 — 五方向独立 Skill 集

五个相互独立、零共享文件的 Skill bundle，重心错位（非同管道变体）：

| 目录 | Skill | 重心 |
|---|---|---|
| `skill-a-specledger/` | spec-ledger-template-adaptation | 上游规格取证：模板/须知 → 带溯源指针的规格账本，冲突显式裁决，机器逐项 PASS/FAIL/UNKNOWN |
| `skill-b-renderproof/` | render-proof-template-adaptation | 下游渲染工程：LibreOffice 真实渲染 → PDF 实测（页面几何/版心边距/栏数/字体内嵌）→ 逐项裁决账本 |
| `skill-c-fidelitycensus/` | fidelity-census-adaptation | 转换完整性：内容单元普查 + 数字/引用 token 全等比对 + 声明账本覆盖裁决，未声明差异即事故 |
| `skill-d-contractgate/` | contract-gate-run-discipline | 过程质量控制：partial 骨架先行、阶段打卡固证、seal 八项独立裁决不过不交付、900s 预算阶梯 |
| `skill-e-xrefalign/` | xref-reference-consistency | 语义一致性：题注编号/悬空引用/题注位置 + GB/T 7714 形式初筛 + 重编号全量方案 |

每个 bundle 均含完整 SKILL.md（合法 YAML frontmatter）、scripts/（纯 Python 3
标准库）、references/、examples/（合成示例，本地真实端到端运行产物存 expected/）、
GITHUB_URL.txt。示例输入全部由 make_fixture.py 现场合成，不对应真实案件。
