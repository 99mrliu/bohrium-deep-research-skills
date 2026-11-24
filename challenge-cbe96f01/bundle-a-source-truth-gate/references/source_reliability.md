# 来源可靠性核查规则（source-truth-gate）

## 1. 来源等级（用于 confidence 校准，不用于直接判对错）

1. **一手正式出版物**：同行评审期刊正式版、会议正式论文集（有 DOI/ISBN）。
2. **索引数据库记录**：Crossref、PubMed、Scopus 元数据；用于核对条目真实性，不替代原文核读。
3. **预印本**：arXiv、bioRxiv、SSRN 等；可用但必须标注版本，且需查是否已有正式版。
4. **灰色文献**：技术报告、学位论文、标准、政府/机构文件；需核对发布机构与版本日期。
5. **不可核验来源**：无 DOI、无稳定链接、快照与公开索引均查无此条 → 按七态机处理，绝不判 verified。

等级只影响 confidence 上限：仅凭 2 级记录判"引用支持"时 confidence ≤ medium（未核读原文）。

## 2. 撤稿与更正核查流程

对每条已定位到可信记录的被引文献：

1. 记录状态字段：`published / corrected / retracted / preprint`。
2. `retracted` → 硬报警（`retraction_flagged`）：在 finding 中归入"学术规范"类，severity 至少 major；若论文结论实质依赖该文献，升 critical。检查撤稿时间是否早于本稿投稿时间（无法取得投稿时间则写明）。
3. `corrected` → minor finding：提示引用时应注明更正版本；若更正涉及被引结论本身，升 major。
4. 关注撤稿原因类型（诚实错误 vs 学术不端）只在可信记录直接给出时引用；不推测。

公开核查入口（联网时；访问日期写入 recheck 字段）：

- Crossref `https://api.crossref.org/works/<doi>`（`relation`、`update-to` 字段）。
- Retraction Watch Database（`retractiondatabase.org`，部分功能需注册，权限不足时写明）。
- 出版社文章页面（"Retraction notice"/"Correction"横幅）。

## 3. 预印本—正式版版本比对

1. 快照/在线记录给出 `version_of`（预印本 → 正式版 DOI）时：若条目引用的是预印本而正式版已存在 → `version_mismatch` 硬报警，finding 为规范问题 minor~major。
2. 版本不一致不止是引用格式问题：预印本与正式版的数值、结论可能不同。凡论文主张依赖该文献具体数值时，要求以正式版为准，无法取得正式版则标 待复核。
3. 反向情况（引用正式版但作者实际工作基于预印本）无法从条目本身发现，不做推测。

## 4. 伪造文献识别要点（suspected_fabricated 的语义）

判 `suspected_fabricated` 需要**组合证据**，单一信号不足以定性：

- 可信快照与（可用的）在线索引均查无此条，**且**
- DOI 语法无效或条目元数据无法解析（无作者、无年份、无标题段），**或**
- 条目内部自相矛盾（期刊名与 DOI 前缀注册机构不符、卷期页码模式异常）。

定性后仍写"suspected"，最终判定留给人；建议作者提供该文献原文或稳定链接。禁止仅凭"我没查到"就断言伪造——查不到的常见原因是快照覆盖不足，必须在 basis 中写明核查范围。
