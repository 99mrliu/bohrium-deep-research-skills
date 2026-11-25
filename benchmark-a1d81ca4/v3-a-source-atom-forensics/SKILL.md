---
name: source-atom-forensics
description: >-
  当 /input/case.json 的 output_contract 要求交付恰好四项 source-conditioned
  benchmark-DRAFT，或要求把参考答案元素追溯到实际 JSON/JSONL/MD/TXT 段落与表格行、
  验证 node_id/quote/atom 覆盖时使用；触发词包括“四项题卡”“源节点索引”“原子证据”“规范化原文引文核验”。不用于 PDF 像素级 gold 定位、通用 ledger/dashboard、无源材料的自由科研作答，也不用于把字符串匹配宣称为独立语义判分。
---

# 源节点—答案原子证据取证

## 最短可靠路径（实际 DeepSeek Harness）

以下 `scripts/...` 与 `examples/...` 都相对本技能根目录调用；脚本只用 Python 3 标准库，无需安装依赖。不得把示例中的科学内容、节点 ID 或答案带入正式案例。

1. **先读原始约束和全部源材料。** 读取 `/input/case.json`、`/input/task.md`，按 case 中真实引用逐一检查所有材料文件及格式。本技能只处理实际提供的段落/表格文本，不把 PDF 画面当作本工作流的 gold。注意原始 `case_id`、完整 `output_contract`、材料范围和禁止事项；不得按领域标签猜内容。
2. **立即留下诚实的部分结果。** 在 `/app/work` 建立 `draft.json`，写入原始 `case_id`，并把**每一个**原始 `output_contract` 字段放在草稿顶层；尚无内容时使用类型相符的空容器并记录限制，成功版不得保留 `null` 占位。`Bank` 先为 `[]`，另含 `status`、`sources`、`uncertainty`、`change_records`、`limits`。不得漏字段，也不得用后续“标准模板”覆盖合同。
3. **先索引真实源字节。** 对 case 实际声明的 JSON/JSONL/MD/TXT 文件逐一调用：

   ```bash
   python3 scripts/source_map.py /input/<真实材料文件> --output /app/work/source_map.json
   ```

   多文件可依次列在同一命令；也可给目录，但目录只索引支持格式，其他格式仍须人工查明并列为限制。阅读 map 中的 `sources[].sha256`、节点 `path/locator/page/text`。空文件、坏 JSON、无字符串、缺失文件或非 UTF-8 会非零退出，不能据此声称成功。
4. **尽早导出 partial。** 用当前 map 和当前草稿运行下述 gate；此时四项不足失败是预期的，不能被改写为成功。随后显式导出：

   ```bash
   python3 scripts/evidence_gate.py --draft /app/work/draft.json --source-map /app/work/source_map.json --output /app/work/evidence_verdicts.json
   python3 scripts/finalize.py --case /input/case.json --draft /app/work/draft.json --source-map /app/work/source_map.json --evidence-verdict /app/work/evidence_verdicts.json --result /app/output/result.json --allow-partial --limits "尚未完成四项源证据核验"
   ```

   gate 失败返回 1；输入/解析错误返回 2。材料暂缺导致没有 map/verdict 时，`finalize.py --allow-partial` 可省掉相应参数，但必须写具体 `--limits`，仍不补造内容。若模型请求、900 秒预算或回复 token 将尽，停止扩写，保留当前 partial，并列清缺失项、已核节点、最后可读输出和人工接管点。
5. ** agent 真正读源并写草稿。** 逐段、逐表行阅读实际文本，独立撰写恰好四项 `Bank`。每项含 `id/task/scope&input_material`（实际键名是 `scope/input_material`）、`reference_answer/rubric/difficulty/data_license/evidence`。参考答案先拆成最小可判读的 `elements`，再为每个元素声明 `answer_element_ids` 对应的原子；每个原子只映射一个明确源节点。多节点支撑同一元素时拆成多个原子，不拼接跨节点 quote。绝不可直接抄写预写的正式科学答案；`examples` 仅验证接口。
6. **逐项做语义裁决。** quote 必须取自所声明节点的实际文本，允许的差异仅限 NFKC 与空白折叠。`atom.reason` 和 `evidence.reason` 写明为何主语、关系、单位、条件、否定及范围支撑该原子；对未报告、冲突和不可判断保持原状。数值原子的所有数字记号（含百分号形式）须逐字出现在 quote 中，默认不做单位换算或“同义数值”匹配。子串通过**不等于**语义正确。
7. **迭代核验再导出。** 每次修改草稿或源 map 后重跑 gate，避免陈旧 verdict；gate 会重读源字节并核对 SHA256。阅读 `evidence_verdicts.json` 的 item/atom 错误，修复零原子、未覆盖答案元素、孤儿映射、错节点、越界引文和不支持数值。最终：

   ```bash
   python3 scripts/source_map.py /input/<真实材料文件> --output /app/work/source_map.json
   python3 scripts/evidence_gate.py --draft /app/work/draft.json --source-map /app/work/source_map.json --output /app/work/evidence_verdicts.json
   python3 scripts/finalize.py --case /input/case.json --draft /app/work/draft.json --source-map /app/work/source_map.json --evidence-verdict /app/work/evidence_verdicts.json --result /app/output/result.json
   ```

8. **终检而非粉饰。** 检查 `/app/output/result.json`：原 `case_id`、所有原合同字段及所有提交内容字段仍在顶层，`sources` 有真实文件与字节哈希，`uncertainty/change_records` 未丢失。只有恰好四项全部通过新鲜 gate、动态合同检查通过时，`status` 才能为 `complete`；否则显式 `--allow-partial` 并说明限制。不得编造 DSH 分数或把 synthetic 技术日志当作独立语义验证。

## 合同、结构与字段

`finalize.py` 支持 `output_contract` 为：`list[str]`；含 `fields` 的 dict 且 fields 为 `list[str]`；fields 为 `list[dict(name=...)]`；以及直接 `field -> type/metadata` 映射（也接受 fields 为映射）。所有字段均保留且置于顶层，不能假定单一形状。完整题卡与原子 schema 见 `references/source_schema.md`，原子化、0/1/2 规则和人工语义责任见 `references/authoring_protocol.md`。

## 失败处理

- **缺输入、坏 UTF-8/JSON、空索引、源字节改变：** 脚本非零退出；报告实际失败文件与人工接管点，不能创建成功。
- **三项/五项、缺字段、零原子、答案元素未覆盖、孤儿 atom、quote 越界、数字不在 quote：** verdict `ok=false`，返回 1；finalizer 默认拒绝导出成功。
- **时间不足或语义未裁决：** 保留真实已完成部分，`status=partial`，在 `limits/uncertainty` 中明确是哪一项、哪个节点、哪一步未完成。
- **旧 map/verdict：** finalizer 以草稿和 map 字节哈希拒绝混用；重跑上述脚本而非手改通过标记。

## 完全合成的可运行边界示例

```bash
examples/run_example.sh [调用方指定的输出目录]
```

省略参数时使用 `mktemp`。示例在输出目录内建 `/app` 类似的 `work/` 与 `output/`，产出 source map、evidence verdicts、result.json，并确认“改 quote”和“少 atom”均被拒绝。示例所有内容和产物均为 SYNTHETIC，输出目录不写入技能包。
