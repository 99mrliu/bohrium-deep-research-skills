# 本地真实测试记录

范围：仅在当前 Skill 根目录读写；未读取或复用其他 bundle，未执行 Git commit/push。所有输入与输出均为 **SYNTHETIC 合成回归材料，不是正式竞赛结果**。

## 1. 语法与 33 条合成断言

从 Skill 根目录执行：

```bash
python3 -c 'from pathlib import Path; p=Path("scripts/layout_evidence.py"); compile(p.read_text(encoding="utf-8"), str(p), "exec"); print("syntax OK")'
python3 scripts/layout_evidence.py verify \
  --suite examples/synthetic/suite.json \
  --output examples/expected/verification-report.json
```

最终实际结果：

```text
syntax OK
suite=SYNTHETIC-EVIDENCE-RECOVERY-TESTS status=passed assertions=33 passed=33 failed=0 output=examples/expected/verification-report.json
```

退出码均为 0。断言由脚本从 JSON/TXT/MD 原始输入重新索引并定位，覆盖：显式双栏块顺序、跨栏与跨页、行尾断词两个投影、逐字空白/大小写限制、重复短语歧义、页眉页脚/图中文字排除、零基半开 offset、TXT form-feed、MD 页标记、空查询与未找到。

开发中的首次运行曾暴露 7 个失败（一个断词归一化实现问题及六个手工 offset 差 1）；修正实现/期望并重跑后才得到以上 33/33，通过结果不沿用初次失败快照。

## 2. 正向双栏端到端

```bash
python3 scripts/layout_evidence.py index \
  --input examples/synthetic/layout.json \
  --output examples/expected/layout-index.json
python3 scripts/layout_evidence.py locate \
  --index examples/expected/layout-index.json \
  --queries examples/synthetic/queries.json \
  --output examples/expected/location-report.json
```

实际输出与退出码：

```text
index=SYNTHETIC-TWO-COLUMN status=ok pages=2 issues=0 output=examples/expected/layout-index.json
case_id=SYNTHETIC-UNIQUE-QUOTES status=ok summary={"ambiguous": 0, "invalid": 0, "matched": 3, "not_found": 0, "total": 3} output=examples/expected/location-report.json
positive_index=0 positive_locate=0
```

实际报告保留：

- 原数组为右块穿插排列，但 `block_order` 使正文阅读顺序为 `p1-left-intro` → `p1-left-detail` → `p1-right-main`；
- `cross-\ncolumn order explicit` 的页 1 / `p1-left-intro` / 行 2–3 / document `[24,52)`，查询 `cross-column order explicit` 唯一命中，`fidelity_variant=hyphen_retained`；
- 左栏到右栏跨块引文的 document `[107,154)`，`spans_blocks=[p1-left-detail,p1-right-main]`；
- header/footer/figure_text 都保留但 `included=false`；无 unresolved issues。

## 3. TXT/MD 独立索引

```bash
python3 scripts/layout_evidence.py index \
  --input examples/synthetic/text.txt --synthetic \
  --output examples/expected/text-index.json
python3 scripts/layout_evidence.py index \
  --input examples/synthetic/markdown.md --synthetic \
  --output examples/expected/markdown-index.json
```

实际结果：

```text
index=text status=ok pages=2 issues=0 output=examples/expected/text-index.json
index=markdown status=ok pages=2 issues=0 output=examples/expected/markdown-index.json
text=0 markdown=0
```

TXT 和 MD 都是两页，逐页行索引与全局 offsets 已读回。MD 页标记未被当作正文；TXT 跨页引文在验证报告中具有两个 segments 且根 `page_char_start/end=null`。

## 4. 预期失败/歧义端到端

```bash
python3 scripts/layout_evidence.py index \
  --input examples/expected-failure/layout.json \
  --output examples/expected-failure/index.json
index_status=$?
python3 scripts/layout_evidence.py locate \
  --index examples/expected-failure/index.json \
  --queries examples/expected-failure/queries.json \
  --output examples/expected-failure/report.json
locate_status=$?
printf 'index_status=%s locate_status=%s\n' "$index_status" "$locate_status"
test "$index_status" -eq 2
test "$locate_status" -eq 2
```

实际输出：

```text
index=SYNTHETIC-EXPECTED-FAILURE-SCAN status=needs_review pages=2 issues=2 output=examples/expected-failure/index.json
case_id=SYNTHETIC-EXPECTED-FAILURE status=unresolved summary={"ambiguous": 1, "invalid": 0, "matched": 0, "not_found": 1, "total": 2} output=examples/expected-failure/report.json
negative_index=2 negative_locate=2
```

保留的报告 `examples/expected-failure/report.json` 明确包含：

- 同短语在 `left` 行 1 `[0,23)` 与 `right` 行 1 `[0,23)` 两处，状态 `ambiguous`；
- 页 2 `NO_TEXT_LAYER`、`SCAN_REQUIRES_OCR`；
- 扫描相关查询为 `not_found`，并附 `QUOTE_NOT_FOUND`，但 `semantic_entailment=not_evaluated`；
- `expected_failure=true`、`synthetic=true`、`formal_result=false`；不能据此声称扫描图像中没有查询文字。

## 5. 读回与结构审计

所有文本和生成报告均使用读文件工具完整读回，随后用 Python 标准库审计：UTF-8 解码、JSON 解析、frontmatter 键集合、目录/name 一致性、GitHub 两行、正/负报告摘要、source excerpt 与 segments offsets、无符号链接、允许的文件扩展名、文件数/单文件/总大小上限，以及不含个人机器绝对路径。最终审计命令与退出码会报告给协调方；此文件本身也纳入审计。

## 6. 明确限制

- 未在真实 PDF、真实扫描图像或外部 OCR 上测试；合成 JSON 只是模拟外部 bbox/PyMuPDF 块输入。脚本不直接解析 PDF、不做 OCR、不自动推断栏序，也不强制安装依赖。
- 物理块的 bbox、角色、block_order 需要上游提取器及 Agent 审核。缺顺序、扫描无文本层或未核 OCR 必须保留不确定性。
- offsets 是规范化 LF 阅读流和原物理行中的 Unicode code-point 零基半开区间，不是 UTF-8 字节或 PDF glyph offsets。
- fidelity 仅空白折叠与 ASCII 行尾连字符双候选，不做语义蕴含、大小写、同义词或 NFKC 变换。出现重复/未找到/无文本层时不包装为成功。
- 没有运行正式 case，故没有生成或伪造 `/app/output/result.json`。正式运行时按 `/input/task.md` 的真实 output_contract 生成，并原样保留 `/input/case.json` 的 case_id。
