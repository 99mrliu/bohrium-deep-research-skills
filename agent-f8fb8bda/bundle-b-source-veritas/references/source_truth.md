# 来源真实性（Source Truth）：伪造与幻影文献的成因、核验层级与回链率门槛

## 1. 为什么伪造/幻影文献在 LLM 综述中高发

1. **生成先验强于检索约束**：语言模型按"该领域应该存在的文献"补全引用，
   标题、作者、期刊、年份各自合理，组合起来却不存在（phantom reference）。
2. **DOI 是高频臆造点**：DOI 格式规整、语义密度低，模型极易编造出
   语法接近但从未注册的 DOI；malformed DOI 是更强的伪造信号。
3. **材料幻影**：给定一批本地材料时，模型可能引用"材料里那篇关于 X 的
   论文"，但材料中并无此文（origin=material 的 phantom）。
4. **结论—证据脱节的级联**：先写结论再补引用时，倾向于"找到"一句
   并不存在的原文来支撑，产生改写型假引用（not_verbatim）。
5. **元数据漂移**：同一文献多次出现时，年份/卷期/作者顺序被静默改写，
   形成 metadata_conflict，使读者无法回溯到唯一记录。

## 2. 核验层级（由强到弱）

| 层级 | 机制 | 能排除的失败 |
|-|-|-|
| L1 本地逐字（verbatim linkage） | quote_verify.py：归一化子串匹配到语料具体页 | 断链引用、改写型假引用、页码错误 |
| L2 材料内交叉（in-corpus identity） | refcheck.py R3：origin=material 必须匹配 corpus_index 中的文档标题 | 材料幻影 |
| L3 在线解析（online resolution） | refcheck.py R5：Crossref 解析 DOI | 未注册 DOI、DOI 张冠李戴 |

原则：**低层级未通过时，高层级结果不得用于补救叙事**——例如
quote 在本地语料中找不到，不能用"在线数据库里可能有"来保留结论。
L3 是增强信号而非判官：Crossref 未收录可能是 DataCite/预印本 DOI，
故 404 只降级 not_checked 并留痕，不单独定罪。

## 3. 材料外来源的处理纪律

- 凡非本案例材料（/input 语料）来源的文献，`origin` 必须标
  `"search"`，且在综合结论中**降权**：材料内证据可支撑主结论，
  材料外证据只能作为补充佐证，并注明检索来源与获取日期。
- 材料外来源无法通过 L1 逐字核验（不在语料中），其引用在
  evidence ledger 中预期为 not_verbatim/doc_missing；此类证据
  应放入 uncertainty 而非 evidence_matrix，或先将全文纳入语料
  再核验。
- 禁止把 origin=search 的文献改标为 material 以绕过 R3。

## 4. 回链率（linkage rate）的解释与门槛建议

`linkage_rate = verified 证据数 / 证据总数`，由 linkage_report.json
计算，可按 field 分组查看。

- **1.0**：交付门默认要求。每条写入结论的判断都有逐字出处。
- **page_mismatch 单独计数**：引用真实但页码错误，说明定位纪律
  松懈；修复成本极低（按 found_page 改页码），不允许带病交付。
- **建议门槛**：正式综述 ≥0.95 且核心结论（synthesis/conflicts
  区块）=1.0；低于 0.8 表明证据登记流程失效，应回到原文重新摘录
  而不是修补文本。
- 回链率不衡量语义充分性（引用是否真的支持结论），它只保证
  "有此原文"。语义充分性靠引用规则（见 quotation_rules.md）与
  冲突证据并列呈现来保障。
