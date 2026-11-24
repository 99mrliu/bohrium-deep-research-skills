# 合成示例 / Synthetic Example — delivery-forge

**本目录全部内容为合成示例（synthetic example）**：所有"研究"文本均为虚构，
仅用于演示工具链，不描述任何真实研究。

## 文件 / Files

| 文件 | 说明 |
|---|---|
| `bilingual_master.md` | 双语主文档：3 个标题 + 8 个 `⟦S####⟧` 段落（含 图 1 图注、式 (1)、2 条参考文献） |
| `structure_inventory.json` | 结构清单：3 sections、1 figure、1 equation、2 references |
| `case.json` | 模拟案例文件，含显式 `output_contract`（7 个字段） |
| `output/bilingual_master.md` | 交付目录中的主文档副本（census 对象） |
| `output/bilingual.html` | 渲染产出的自包含双语 HTML（文本，随包发布） |
| `output/result.json` | 手写的高质量 result.json（匹配显式合同） |
| `output/change_log.md` | 各阶段变更记录 |
| `output/render_qa_log.json` | 渲染 QA 日志的实际文本输出 |
| `output/coverage_report.json` | census 的实际输出（PASS，7/7） |
| `output/contract_check.json` | 合同校验的实际输出（PASS） |

## 实际运行的命令 / Commands actually run

```bash
cd examples/synthetic
cp bilingual_master.md output/bilingual_master.md

python3 ../../scripts/render_bilingual.py \
    --master bilingual_master.md --outdir output --basename bilingual
# → render_qa_log: html=generated previews=generated font=Heiti TC   (exit 0)

python3 ../../scripts/census_coverage.py \
    --inventory structure_inventory.json \
    --deliverable output/bilingual_master.md \
    --report output/coverage_report.json
# → census: PASS — 7/7 covered                                        (exit 0)

python3 ../../scripts/validate_contract.py --case case.json --outdir output
# → contract: PASS — 0 violation(s) (contract origin: explicit, 7 fields) (exit 0)
```

## 关于 PDF/PNG 预览 / About the PDF/PNG previews

运行 `render_bilingual.py` 时**真实生成**了 `output/bilingual.pdf`（3 页 A4）
和 `output/bilingual_page1.png`（第 1 页预览，110 dpi）：字体发现命中
`/System/Library/Fonts/STHeiti Light.ttc`（family: Heiti TC，QA 日志中有记录）。
这两份文件是**二进制运行时产物，已按包规范从 bundle 中排除**；其 QA 信息以
文本形式保留在 `output/render_qa_log.json` 与 `output/change_log.md` 中。

若要复现（在临时副本中，预览文件会重新生成并通过合同校验）：

```bash
cp -r examples/synthetic /tmp/df-run && cd /tmp/df-run
cp bilingual_master.md output/bilingual_master.md
python3 <bundle>/scripts/render_bilingual.py --master bilingual_master.md --outdir output --basename bilingual
python3 <bundle>/scripts/census_coverage.py --inventory structure_inventory.json \
    --deliverable output/bilingual_master.md --report output/coverage_report.json
python3 <bundle>/scripts/validate_contract.py --case case.json --outdir output
```

注意：本 bundle 内发布的 `output/` 已删除 PDF/PNG，因此**直接在 bundle 目录里
重跑 `validate_contract.py` 会报两个被排除的预览文件缺失**——这是预期行为，
请在临时副本中复现完整流程。
