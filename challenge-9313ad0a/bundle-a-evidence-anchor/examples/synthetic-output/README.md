# 合成示例输出说明（synthetic example outputs）

**本目录中的全部文件均为合成示例（synthetic example）的真实运行输出**：输入是
`../synthetic-input/` 下完全虚构的玩具材料（material_alpha.txt、material_beta.txt，
非真实论文、非真实数据）与 mindmap.json；本目录文件由以下命令真实生成，未经手工修改：

```bash
cd examples/synthetic-input   # 以相对路径运行，故输出中 file 字段为材料文件名
python3 ../../scripts/material_intake.py --out work/material material_alpha.txt material_beta.txt
python3 ../../scripts/anchor_audit.py --map mindmap.json \
    --material work/material/pages.jsonl \
    --report work/anchor_report.json --quarantine work/quarantine.json
```

文件清单：

- `pages.jsonl`：material_intake.py 的分页输出（每行一页）。
- `material_index.json`：材料索引（页数、字符数、SHA-256、工具、警告）。
- `anchor_report.json`：锚定审计报告；预期 summary 为
  `{"nodes": 9, "verified": 5, "mislocated": 1, "fabricated": 1, "unanchored": 0, "number_not_found": 1, "warnings": 1}`。
- `quarantine.json`：隔离清单；预期为 `["n06", "n08"]`（n06 引文系改写 → fabricated；n08 标签数字 99.9% 不存在 → number_not_found）。

审计退出码为 1（存在 fabricated 节点），符合"存在 fabricated 或 unanchored 时退出码为 1"的约定。
