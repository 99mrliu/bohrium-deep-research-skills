# patent-number-family-resolver 使用与方法说明

## 简介

本 Skill 把专利号定位、传真著录字段抽取与同族归并实现为确定性脚本管线，供 Agent 在"专利与技术文献检索"任务中调用。所有号码解析与归并判断由代码完成，结果带定位与事件日志，可被他人按记录复跑。

## 依赖与安装

- Python 3（仅标准库）；传真 PDF 抽取依赖系统 `pdftotext`（poppler）。
- 无安装步骤：直接以 `python3 scripts/<name>.py` 调用；各脚本亦可 `import` 作为库使用。

## 各脚本功能

| 脚本 | 功能 |
|-|-|
| `scripts/patent_numbers.py` | 号码规范化库/CLI：`normalize` 单号规范化（US/WO/EP/CN/JP/KR，公开/授权/申请/优先权），`find` 从文本抽取疑似号码并处置 OCR 粘连 |
| `scripts/scan_corpus.py` | `index` 自动发现语料并建号码索引；`query` 按号码（精确 + 同序号跨种类关联）或关键词（主题降级模式）匹配，命中带 file+locator |
| `scripts/extract_facsimile.py` | 传真首页 INID 字段抽取：pdftotext -layout → INID 切段 → 字段解析（号码规范化、日期 ISO 化、分类号切分），OCR 异常全部记录 evidence_events |
| `scripts/merge_family.py` | 简单族（优先权集合全同）与扩展族（共享≥1 优先权的连通分量）双口径归并；去重、冲突字段保留、无优先权记录告警 |
| `scripts/scaffold_result.py` | 生成 `/app/output/result.json` 骨架，镜像 `output_contract` 全部字段，未填充项列入 uncertainty |
| `scripts/selfcheck.py` | 25 项断言自测（正例全链路 + 负例拦截），exit 0 为通过 |

## 输入输出

- 输入：`/input/case.json`（case_id、查询、`output_contract`）、`/input/task.md`、组织方提供的语料（JSON/CSV/TXT/PDF 传真件）。
- 输出：`/app/output/result.json`（见 `templates/result_fields.md`）+ `/app/work/` 下的中间产物（num_index.json、query_hits.json、fields_*.json、family.json、fill.json）。

## 适用场景与限制

- 适用：号码定位、著录项抽取、同族归并与口径说明、检索证据留痕。
- 限制：关键词模式为字面匹配，无语义扩展；优先权缺失时族归属不确定；不核验法律状态（一律标注"官方登记未核验"）；OCR 粘连多解时不拆分。

## 失败处置

所有脚本的非零退出码含义：`2`=输入/环境缺失（语料空、pdftotext 不可用等），`1`=查询含非法号码或自测失败。失败信息打印到 stdout 的 JSON 中，Agent 应把失败原因写入 result.json 的 uncertainty，不得跳过不报。

## 自查

```bash
python3 scripts/selfcheck.py   # 25 项断言；夹具为虚构示例（illustrative）
```

## 维护信息

规则表与脚本逻辑保持同步：`rules/number_formats.md` ↔ `patent_numbers.py`，`rules/family_scope.md` ↔ `merge_family.py`，`rules/ocr_boundary.md` ↔ `patent_numbers.try_split_merged` / `extract_facsimile`。修改任一侧时同步另一侧并重跑 selfcheck。
