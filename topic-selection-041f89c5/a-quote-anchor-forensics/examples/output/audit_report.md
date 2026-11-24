# 证据锚点核验报告

来源文件 3 个；台账记录 5 条：PASS 4 / FAIL 1 / ERROR 0。

| 记录 | 来源文件 | 判定 | 问题 |
|---|---|---|---|
| E1 | paper1.txt | PASS | - |
| E2 | paper1.txt | PASS | - |
| E3 | paper2.txt | FAIL | quote 在来源全文中找不到逐字匹配（归一化后） |
| E4 | paper2.txt | PASS | - |
| E5 | paper3.txt | PASS | - |

来源登记册（SHA-256 见 source_registry.json）：
- `paper1.txt`（696 字节，可解析）
- `paper2.txt`（520 字节，可解析）
- `paper3.txt`（525 字节，可解析）
