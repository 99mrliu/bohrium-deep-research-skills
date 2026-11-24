---
name: dr-source-veritas
description: 深度研究与文献综述中的上游来源真实性门控——每条结论必须绑定可在原文语料中逐字找回的引用、每条文献身份必须经一致性核验，回链率可计算可复核；触发词：深度研究、文献综述、证据回链、deep research、evidence linkage、quote verification、reference check。
---

# dr-source-veritas：上游来源真实性门控（Source Veritas）

## 1. 用途与边界

本 Skill 面向深度研究（deep research）与文献综述任务，从机制上消除两类高发失败：
（a）结论句在原文语料中找不到对应段落的"断链引用"；
（b）引用了不存在的文献（幻影文献 / phantom reference、伪造 DOI）。
手段是把机械可判定的核验全部下沉到三个确定性 Python 脚本（仅标准库），
以退出码形成硬门控：`0` 通过，`1` 门控违例（stdout 逐项失败清单），`2` 用法/IO 错误。

本 Skill 不负责单篇精读、元数据方法学审查与写作润色；它保证的是
**结论—引用—文献身份**这一链条的可核验性。规则细节见
`references/source_truth.md` 与 `references/quotation_rules.md`。

## 2. 环境与前置条件

- python3（≥3.10，仅标准库）；宿主 PATH 中有 `pdftotext`。
- 材料在 `/input`（`case.json`、`task.md`、真实 PDF 等；PDF 无预提取答案层，
  必须按实际文件内容读取，不得依据目录标签推断）。
- 工作目录 `/app/work`，最终产物 `/app/output`（必须含 `result.json`）。
- 以下设 `SKILL_DIR=/skills/weekly-skill`（平台安装路径）。

## 3. 五阶段流程协议（六要点 → result.json 区块映射）

六要点映射：问题拆解→`decomposition`；检索覆盖→`search_coverage`；
证据回链→`evidence_matrix`（每条含 doc/page/quote/status）；
冲突证据→`conflicts`；综合结论→`synthesis`；研究空白→`research_gaps`。
字段名以各案例 `case.json` 的 `output_contract` 为准，下述仅为语义角色。

### 阶段一：契约初始化（contract init）

防御式读取 `case.json`，动态取得 `case_id` 与 `output_contract` 要求的
全部字段名，先写出一版 `status: "partial"` 的 `result.json` 骨架，
后续每完成一个阶段就地增量更新（防止超时丢失全部成果）：

```bash
python3 - <<'EOF'
import json
try:
    with open('/input/case.json', encoding='utf-8') as f:
        case = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    case = {}
    print('[WARN] case.json 读取失败:', e)
cid = case.get('case_id') or case.get('id') or 'unknown'
oc = case.get('output_contract') or {}
fields = list(oc.keys()) if isinstance(oc, dict) else list(oc or [])
print('case_id =', cid); print('contract fields =', fields)
EOF
```

禁止在脚本或产物中硬编码契约字段名；一律以上述方式动态读取。

### 阶段二：问题拆解（decomposition）

将 `task.md` 的研究问题拆为可独立检索的子问题清单（对象/机制/方法/
时间范围/比较关系），标注子问题间依赖；每个子问题指派将填充的契约字段。
通用做法：每个子问题必须给出"可回链证据才算回答"的判定标准。

### 阶段三：检索执行（retrieval & corpus build）

先对本地材料建语料（PDF 解析、页级定位、身份候选抽取）：

```bash
python3 $SKILL_DIR/scripts/corpus_build.py --materials /input --workdir /app/work
```

- exit 0：语料就绪，产物在 `/app/work/corpus/`（`corpus_index.json`、
  `identity_candidates.json`、`text/<doc_id>.txt`）。
- exit 1：全部材料不可解析——按 stdout 失败清单说明，语料类结论
  全部降级为 partial 并在 uncertainty 中注明。
- 后续检索补充的材料外文献一律记 `origin: "search"`，结论中降权
  （见 `references/source_truth.md`）。检索覆盖按子问题×来源记录到
  `search_coverage`：已查来源、命中数、停止条件、未覆盖缺口。

### 阶段四：证据与综合（evidence & synthesis）

每条拟写入结论的判断，先登记为证据台账一行，再跑两道门。

1) 证据台账 `/app/work/evidence_ledger.jsonl`，每行：

```json
{"evidence_id": "E1", "doc": "paper_x", "page": 3, "quote": "<逐字原文>", "field": "synthesis", "note": "支撑哪条结论"}
```

`quote` 必须逐字摘自语料（允许跨行，脚本会做连字符换行修复），
`field` 填该证据服务的契约区块。引用规则见 `references/quotation_rules.md`。

2) 引用核验门（evidence linkage gate）：

```bash
python3 $SKILL_DIR/scripts/quote_verify.py --ledger /app/work/evidence_ledger.jsonl --corpus /app/work/corpus
```

- exit 0：全部 verified，`linkage_report.json` 给出总回链率与按 field
  分组回链率，写入 `evidence_matrix`。
- exit 1：按 stdout 清单逐条修复——`page_mismatch` 改页码；
  `not_verbatim` 回到原文重新逐字摘录或删除该结论；
  `doc_missing` 检查 doc_id（以 `corpus_index.json` 为准）。
  修复后重跑，直至 exit 0；预算不足时保留 verified 子集，
  未回链条目移入 uncertainty 并将 status 标为 partial。

3) 文献清单 `/app/work/references.json`（每条含
   `ref_id,title,authors,year,doi,venue,origin∈{material,search}`），
   然后跑身份核验门（reference identity gate）：

```bash
python3 $SKILL_DIR/scripts/refcheck.py --refs /app/work/references.json --corpus /app/work/corpus
```

可选在线核验（无网 5 秒超时自动降级 not_checked，不影响其它检查）：

```bash
python3 $SKILL_DIR/scripts/refcheck.py --refs /app/work/references.json --corpus /app/work/corpus --online
```

- exit 0：无硬状态，`sources` 区块可引用全部文献。
- exit 1：存在 `material_phantom` / `suspected_fabricated` /
  `metadata_conflict`——这些文献**不得**进入结论与 sources；
  剔除或修正后重跑，并在 uncertainty 中如实记录剔除原因。

冲突证据处理：互相矛盾的结论各自绑定 verified 引用后并列写入
`conflicts`，说明证据强度与适用条件，不得单方取舍或"尚存争议"了之。
研究空白必须区分检索缺口（search_coverage 未覆盖）与凭空判断，
写入 `research_gaps` 并注明类型。

### 阶段五：交付门（delivery gate）

写入 `/app/output/result.json`（`ensure_ascii=False, indent=2`）前自检：

1. `case_id` 与 case.json 原样一致；`output_contract` 全部字段齐备。
2. `evidence_matrix` 每条 status=verified（以最新 linkage_report 为准）。
3. `sources` 中无硬状态文献（以最新 refcheck_report 为准）。
4. `status` ∈ {complete, partial, failed}；partial/failed 必须在
   `uncertainty` 说明限度（哪些子问题未覆盖、哪些证据未回链及原因）。
5. 将三个脚本产物（corpus_index、linkage_report、refcheck_report）
   一并复制到 `/app/output/` 作为可复核附件。

## 4. 脚本接口速查

| 脚本 | 功能 | 关键参数（默认值） | 门控 |
|-|-|-|-|
| `scripts/corpus_build.py` | 建语料+身份候选 | `--materials /input` `--workdir /app/work` | 1=无可解析文档 |
| `scripts/quote_verify.py` | 逐字引用核验 | `--ledger …/evidence_ledger.jsonl` `--corpus /app/work/corpus` `--outdir` | 1=存在非 verified |
| `scripts/refcheck.py` | 文献身份核验 R1–R5 | `--refs …/references.json` `--corpus /app/work/corpus` `--online` | 1=存在硬状态 |

全部脚本 `--help` 可查；IO 错误一律 exit 2 并在 stderr/stdout 说明。

## 5. 异常处理与预算策略

- PDF 解析失败：corpus_build 自动 `pdftotext -layout` → 去 `-layout`
  两级重试，仍失败标 `unparseable`；该文结论降级并在 uncertainty 注明。
- 网络不可用：`--online` 自动降级 `not_checked`，本地 R1–R4 不受影响。
- 预算紧张（64 请求/900 秒）：先保"全部结论 verified"这一底线，
  再扩检索覆盖；每阶段结束就地更新 result.json 骨架。
- 一键自洽演示（合成示例，含门控开火变例）：
  `bash examples/run_example.sh`，产物在 `examples/output_demo/`。
  示例中的 `paper_gamma.pdf` 由 `examples/make_gamma_pdf.py`（matplotlib）在演示开始时
  现场生成、演示结束自动删除——bundle 本体为纯 UTF-8 文本，不含二进制；该 PDF 仅用于
  实测 pdftotext 解析路径，其抽取文本与核验产物保留在 `output_demo/` 供目检。

## 6. 限制

- 逐字核验是子串级证据回链，不判断引用是否支持结论的语义充分性。
- Crossref 未收录（404）不单独定罪，降级 not_checked（可能为
  DataCite/预印本 DOI）；在线核验仅为增强信号。
- 扫描版无文本层 PDF 会标 unparseable；如需 OCR 须借助宿主 OCR 工具
  先行转换，本 Skill 不内置 OCR。
