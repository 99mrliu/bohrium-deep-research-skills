# 02-crossdoc-identity-kg

挑战 阅读15（文献知识图谱构建，product-arena-10-760d1a0b）独立 Skill 包：
**跨文档实体身份裁决与合并门裁定**。

- `SKILL.md`：Skill 本体（用途、适用条件、调用方式、输入输出、异常处理）；
- `scripts/`：确定性脚本（仅 Python3 标准库）——规范化与候选键、
  三态身份裁决门、逐字引文核验、图谱构建（稳定 ID 裁决后分配）、
  查询执行、运行时编排、最小示例流水线、自检；
- `references/`：合并门策略、数据结构、适用边界与失败模式；
- `examples/minimal/`：合成最小示例（2 篇虚构短文、12 提及、12 关系、
  4 查询）及脚本生成的全部输出；
- `GITHUB_URL.txt`：作品公开链接。

快速验证：

```bash
python3 scripts/run_example.py
python3 scripts/selftest.py
```
