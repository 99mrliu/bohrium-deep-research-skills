# 合成示例 / Synthetic Example

本目录是一个**完全合成的**最小工作示例（synthetic example）：所有"论文"
内容均为虚构，仅用于演示对齐主干工作流，不构成任何真实研究。

## 文件 / Files

| 文件 | 来源 | 说明 |
|---|---|---|
| `source.md` | 手写 | 虚构英文短文（标题、摘要、一节两段、Figure 1 题注含引用标记、一条展示公式、一条脚注、两条参考文献） |
| `source_segments.txt` | 脚本生成 | 11 个分段，稳定 ID `⟦S0001⟧`–`⟦S0011⟧` |
| `structure_inventory.json` | 脚本生成 | 结构清单：3 heading / 3 paragraph / 1 caption / 1 equation / 1 footnote / 2 reference_entry，图号 [1]，公式 1，参考文献 2 |
| `bilingual.md` | 手写 | 配对块格式双语母本（中文译文，所有标记保留，含 `> NOTE` 译注示例） |
| `alignment_report.json` | 脚本生成 | 对齐报告：11/11 `ok`，status `pass` |
| `translation_target.md` | 脚本生成 | 由双语母本**派生**的纯净中文译文（非重译），覆盖率 100% |

## 复现 / Reproduce

在本目录的上两级（bundle 根目录）运行：

```bash
cd /path/to/c-alignment-spine

# 1) 分段 + 结构清单
python3 scripts/segment_source.py examples/synthetic/source.md

# 2) 对齐校验（期望 exit 0，status pass）
python3 scripts/check_alignment.py \
    examples/synthetic/bilingual.md \
    examples/synthetic/source_segments.txt \
    --json examples/synthetic/alignment_report.json

# 3) 派生纯净译文 + 覆盖率（期望 exit 0，各项 100%）
python3 scripts/derive_target.py \
    examples/synthetic/bilingual.md \
    --segments examples/synthetic/source_segments.txt \
    --inventory examples/synthetic/structure_inventory.json \
    -o examples/synthetic/translation_target.md
```

负面测试（乱序 → `order_violation`；删 TGT → `missing_tgt`；改引用标记
→ `marker_mismatch`）均已通过，退出码均为非零；测试在临时目录进行，
不属于本 bundle。
