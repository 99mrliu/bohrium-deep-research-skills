# 溯源与门控规则（veracity policy）

本文件定义 source-veracity-gate 的真实性规则。所有规则由
`scripts/source_audit.py` 与 `scripts/build_result.py` 机器执行，不依赖人工自觉。

## 1. 先审计、后扩展

任何记录在进入引用图构建之前，其所在文件必须先进入来源注册表。
注册表条目包含：相对路径、sha1、字节数、判定格式、解析出的记录数、
失败原因（若有）。没有注册表条目的文件不允许向结果贡献记录。

## 2. 记录定位（locator）强制

- 每条规范化文献记录必须带 `locator: {file, pointer}`；pointer 为
  JSON 路径（如 `/message/items/0`）、JSONL 行号（`/line/12`）、
  表行号（`/row/3`）或 BibTeX 条目键（`/entry/key`）。
- 每条引用边必须带 `source: {file, pointer}`，指向产生该边的原始指针
  （某条 references 列表元素、某个边表行）。
- **门禁**：构建候选清单时，凡缺少有效 locator 的记录一律拦截，
  写入 `omissions` 与 `uncertainty`，不得进入 `candidates`。

## 3. 失败登记而非中断

- 文件级解析失败（JSON 损坏、格式不支持）→ 注册表记
  `status=failed/unparsed` 与原因，扫描继续。
- 行级解析失败（JSONL 坏行）→ 跳过该行，文件其余行照常解析。
- 引用目标无法解析到语料内记录 → 保留为 stub：只带原始指针
  （doi/label/raw_id）与首次出现定位，**绝不补造**作者、年份、标题。
  stub 不进入 candidates，写入 `stubs` 与 `omissions`。

## 4. 冲突台账

审计阶段自动检出并登记两类线索（不做裁决，只暴露）：

- **同 DOI 不同标题**：同一规范化 DOI 对应多个规范化标题——可能是
  元数据错误、版本混排或 DOI 盗用，全部列出标题与定位。
- **同标题不同 DOI**：同一规范化标题对应多个 DOI——可能是重复入库、
  预印本/期刊版并存或同名不同文，全部列出 DOI 与定位。

合并阶段另记 `merged-field-conflict`：被合并记录在某字段上有多个
非空不同值时，保留全部值与定位，写入 `uncertainty`。

## 5. 身份合并基线

- DOI 规范化：小写、去 `https://doi.org/`（含 `http://`、`dx.doi.org`、
  `doi:`）前缀、去首尾空白与尾部标点；规范化后精确匹配。
- 标题规范化：小写、去标点、坍缩空白；规范化后精确匹配。
- 两键都缺失的记录保持独立（按 locator 哈希给匿名 id）。
- 本基线**不做**作者-年份模糊 blocking 与版本谱系判定；疑似误合并
  只通过冲突台账暴露，交由下游或人工裁决。

## 6. 方向语义

- reference 边 = citing→cited（由某记录的 references 列表产生，
  `direction_restored: false`）。
- citation 边 = cited→citing。数据源只给参考文献列表时，用全语料
  反向索引恢复前向边（"target 被 rid 引用"），边上标
  `direction_restored: true`，source 仍指向原始 reference 指针。
- 显式 citations/cited-by 列表产生的 citation 边标
  `direction_restored: false`，并由它反向恢复 reference 边
  （标 `true`）。

## 7. 诚实交付

- `status` 只能是 ok / partial / failed，且必须与实际一致：
  种子未命中或无候选不得报 ok；有候选不得报 failed。
- **真实性瑕疵降级**：只要存在损坏/未判定的语料文件、合并字段冲突、
  未解析引用 stub、门禁拦截记录或 records_norm 坏行之一，即使扩展成功，
  `status` 也降为 partial，瑕疵逐条写入 `uncertainty`（"status 降级依据"）。
  ok 只留给"语料干净、种子命中、候选非空、零瑕疵"的运行。
- `output_contract` 逐字段镜像；未知语义字段诚实置 null 并在
  `uncertainty` 逐条注明，禁止猜测填充。
- 空结果、冲突、权限与材料缺失分别说明，互不掩盖。
- 默认离线：不提供联网开关；任何"需要联网才能补全"的事项写入
  `uncertainty`。
