# 任务说明（合成示例）

案例目录提供 Crossref、Europe PMC、出版商记录、保留引用图与组织方本地
import_state 五份离线材料。请对多源文献记录做**状态卫生治理与版本归并**：

1. 识别撤回（retraction）、勘误（erratum/correction）、关注声明
   （expression of concern）、导入撤回（import_state withdrawn）等状态风险；
2. 将 preprint 与其正式出版版本（VoR）归并——候选集中一项研究只计一次，
   引用字段以 VoR 为准，preprint 保留为 alternate_version；
3. 对账 import_state：声称已导入但响应中不存在的标识符须隔离并报告；
4. 产出状态台账、状态报告、清洗后的候选池与 result.json。

**边界**：全部状态证据必须来自材料内部的显式字段/关系/图状态属性；
不得联网查询外部撤回数据库；查不到状态的记录标 `status_unverifiable`，
不得当作干净记录采信。
