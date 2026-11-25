# 本地真实测试记录

测试环境：Python 3.12.14（目标兼容 Python 3.9+ 标准库）；未访问网络，未读取其他 bundle，未使用 Git 提交或推送。

## 1. 合成端到端

从 Skill 根目录执行：

```bash
python3 -B scripts/create_synthetic_fixture.py
python3 -B scripts/run_examples.py
```

真实观察：

- fixture 创建：`Created 20 synthetic claims and 24 subquestions`。
- 正例 `skeleton`：退出 0，生成 result skeleton。
- 正例 `build-result`：退出 0，消息 `Validated result written`，生成 `examples/positive/output/result.json`。
- 正例 `audit`：退出 0，输出 `{"ok": true, "errors": 0}`。
- 负例 `validate`：退出 1，测试器确认此非零值是预期结果；输出 `{"ok": false, "errors": 4}`。
- runner 总体验证：正例 `positive_ok=true`，负例 `negative_ok=false`；负例错误码包含 `answer.missing`、`answer_mode.support_mismatch`、`id.dangling`。

正例报告统计：30 个覆盖单元（6 根问题、24 子问题）、20 claims、20 evidences、1 source；重复 ID=0，悬空 ID=0。负例报告保留 1 个缺失答案、2 个悬空 ID 和 1 个由悬空证据引起的 direct-support 不匹配。

## 2. 回归测试

```bash
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

最终结果：`Ran 34 tests`、`OK`。覆盖缺失/空答案、各命名空间重复 ID、question/claim 悬空链、未报告范围、模式支持、推导/理由、状态上限、置信度、source uncertainty、change_records、任务契约优先级、JSON Schema 风格回退契约、EXACT 多/少字段、case ID 变化、陈旧 result、重命名答案键的 manifest、局部重复链接、父子状态与 JSON Pointer 转义。

## 3. 语法与打包约束

使用 Python 3.12.14 标准库 `ast.parse(feature_version=(3, 9))` 检查全部 Python 文件，`json.loads` 检查全部 JSON，并严格 UTF-8 解码全部文本；使用 Ruby Psych `YAML.safe_load` 实际解析 frontmatter。最终结果：

- `utf8_json_python39_ast=PASS`；`frontmatter_yaml=PASS`，键仅为 `description,name`，name 与目录一致。
- GITHUB_URL 两行检查和 positive result 的 EXACT 键集合均通过。
- 26 个文件；最大单文件 <500KiB；全目录 <2MiB；符号链接 0。
- 只允许 `.md/.txt/.json/.yaml/.py`，无 NUL、无 `__pycache__`、无 `.pyc/.pyo`。

本机没有另行执行 Python 3.9 解释器；3.9 保证范围是所用标准库 API 设计和 AST 语法兼容检查，实际运行版本是 3.12.14。

## 4. 解释边界

测试证明结构工具和保存路径可执行，不证明合成科学内容真实。所有输入输出均标 SYNTHETIC；负例失败不是交付故障，而是必须保留的预期失败证据。实际任务仍须人工核对原文语义、计算与推断边界。
