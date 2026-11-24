# pdf-ingest-provenance

科研选题评估技能的**上游摄入取证**方向：先把材料变成带哈希登记与页级溯源的
可信文本层，再谈综述与结论。

- 核心脚本（仅标准库）：
  - `scripts/ingest_register.py`：逐文件 SHA-256 登记；PDF 用系统工具真实解析
    （不假设预提取文本层），按页统计字符与乱码率；
  - `scripts/extraction_qc.py`：文本层四级质检（ok/ok_with_notes/suspect/unreadable）
    + 引文页级定位（NFKC + 空白折叠归一化子串匹配，未命中即禁用该证据）。
- 运行契约：`/input` → `/app/work`（registry、文本层、QC 报告）→ `/app/output`
  （result.json 含 case_id 与全部 output_contract 字段，诚实 partial；摄入附件随附）。
- 协议细节：`references/ingest_protocol.md`；定位符格式：`references/locator_format.md`。
- 最小示例（合成）：`examples/`，`bash examples/run_example.sh` 一键复跑
  （夹具 PDF 由 `make_fixtures.py` 生成，纯 ASCII，无第三方依赖）。

维护：作者随 Playground challenge-041f89c5 提交；Python ≥3.8；
PDF 解析依赖系统 pdftotext 或运行环境等效工具（缺失时如实登记）。
