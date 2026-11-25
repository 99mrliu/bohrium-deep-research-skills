# 来源审计报告（source_audit）

## 概览

- 扫描根：examples/corpus
- 语料文件总数：4；解析成功：3；解析覆盖率：75.0%
- 规范化记录总数：5（文献记录 5，边记录 0）

## 格式分布

| 判定格式 | 文件数 | 记录数 |
|---|---|---|
| crossref | 2 | 3 |
| europepmc | 1 | 2 |
| unknown | 1 | 0 |

## 文件级来源注册表

| 文件 | sha1(前12) | 字节 | 格式 | 记录数 | 状态 | 失败/异常原因 |
|---|---|---|---|---|---|---|
| broken_response.json | ae27b980187a | 192 | unknown | 0 | failed | JSONDecodeError: Expecting ',' delimiter: line 7 column 1 (char 192) |
| crossref_batch1.json | 8ad7778a77b4 | 1246 | crossref | 2 | ok |  |
| crossref_batch2.json | 196213977d93 | 627 | crossref | 1 | ok |  |
| europepmc_batch1.json | 1f3b8a18b4f9 | 1103 | europepmc | 2 | ok |  |

## 冲突线索

- **同 DOI 不同标题**：`10.0000/synth.001`
  - 标题：A Synthetic Gradient Method for Citation Flow
  - 标题：A Synthetic Gradient Method for Citation Flow: Extended Conference Version
  - 定位：`crossref_batch1.json` `/message/items/0`
  - 定位：`europepmc_batch1.json` `/resultList/result/1`
