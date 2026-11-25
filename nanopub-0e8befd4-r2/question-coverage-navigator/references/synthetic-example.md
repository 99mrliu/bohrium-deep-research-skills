# SYNTHETIC 合成示例说明

**所有样例只用于测试结构，不是正式结果、真实论文、真实纳米出版物或任何医学建议。**

## 文件角色

- `examples/sources/study.md`：含 F01–F20 的最小合成来源和补充检索记录。
- `examples/positive/input/task.md`：六个根问题与 EXACT 四字段契约，要求 24 个子问题闭合。
- `examples/positive/input/case.json`：原 ID 为 `synthetic-case-001`。
- `examples/positive/input/environment/resources.yaml`：本地材料及 64 请求/900 秒限制说明。
- `examples/positive/input/coverage.json`：20 条合成 claims、20 条 evidences、24 个子问题；直接报告、计算、推断和未报告均有实例。
- `examples/positive/work/result-skeleton.json`：工具生成的可填写骨架，不是答案。
- `examples/positive/output/result.json`：由 `build-result` 从已验证 coverage 真实生成。
- `examples/positive/output/coverage-report.json`：结果审计通过报告。
- `examples/negative/input/coverage.json`：从正例深拷贝，故意将 Q1.1 答案置空，并将其 claim/evidence 改成不存在的 ID。
- `examples/negative/output/coverage-report.json`：实际失败报告，`answer.missing` 一个、`id.dangling` 两个、模式支持不匹配一个。

## 可重复执行

在 Skill 根目录运行：

```bash
python3 -B scripts/create_synthetic_fixture.py
python3 -B scripts/run_examples.py
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

第一条会重置合成输入，第二条真实运行四个 CLI 步骤并验证预期退出码，第三条执行 34 项标准库回归测试。整个流程无网络访问。未报告 examples 只说明在最小合成来源内未报告，不代表任何外部知识状态。
