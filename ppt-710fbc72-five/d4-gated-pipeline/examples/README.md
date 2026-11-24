# 示例（合成示例）

> 本目录演示使用的是 **合成示例**：输入由 `scripts/make_synthetic_case.py` 现场生成
> （template.pptx 用 python-pptx 默认版式，paper.pdf 用 matplotlib 现场排版，
> 内容为虚构论文 "SparProtein"），**不是正式测试案例，输出仅为示意**。

## 运行

```bash
bash examples/run_example.sh
```

全程非交互，所有产物写到 `$(mktemp -d)` 临时目录，**不会写回 bundle**。
脚本依次演示：

1. `make_synthetic_case.py --out $TMP/input`：生成 case.json / task.md / paper.pdf
   （4 文本页含可核验数字 + 2 图页）/ template.pptx。
2. `run_case.py prepare`：S0–S4。随后立即校验 `$TMP/output/result.json`
   是合法 partial（status=partial、contract 字段齐全）——这证明"任意时刻被杀
   都有合法 partial"。
3. `fill_example_plan.py --work $TMP/work`：代替 Agent 完成 plan 编辑
   （真实运行中这一步由 Agent 做）。
4. `run_case.py finish`：S5–S9，产出 deck.pptx / deck.pdf / preview/*.png /
   qa_gates.json / pipeline_manifest.json / result.json。
5. **断点续跑演示**：删除 S6–S9 检查点后重跑 finish，日志中 S0–S5 打印
   `skip Sn (checkpoint valid)`，S6–S9 重新执行。
6. `run_case.py status`：打印阶段表、门禁状态、续跑提示。

## 预期产物（临时目录 output/ 下）

```
result.json            status=success（合成案例应六门禁全 pass）
deck.pptx              6 页，按模板 Title Slide / Title and Content 版式构建
deck.pdf               页数与 pptx 一致（export-page-parity）
preview/slide-*.png    每页渲染预览
qa_gates.json          六个机器门禁 + overall
pipeline_manifest.json 阶段墙钟 / 产物 sha256 / 续跑指令 / 工具版本
```

## 接口说明

```
python3 scripts/run_case.py prepare --input DIR --work DIR --output DIR
python3 scripts/run_case.py finish  --input DIR --work DIR --output DIR
python3 scripts/run_case.py status  --input DIR --work DIR --output DIR
```

`--input` 需含 case.json（case_id + output_contract.fields）与 task.md；
论文/模板路径以 case.json `materials` 声明为准，缺省按扩展名发现。
