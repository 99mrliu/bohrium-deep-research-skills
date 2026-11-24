# 失败分类表（Failure Taxonomy）

每类失败对应明确的 status 与披露写法。原则：**失败必须可见、可归因、不升级为谎言**。

| 失败类别 | 触发 | result.json 的 status | 披露写法 |
|---|---|---|---|
| 材料缺失 | manuscript-baseline.md 缺失 | `unable_to_determine` | status_note「基线稿缺失，无法执行修订」；uncertainty 记 `manuscript-baseline.md 缺失` |
| 材料缺失 | reviewer-comments.md 缺失 | `unable_to_determine` | uncertainty 记 `reviewer-comments.md 缺失，无意见可处理`；不得虚构意见 |
| 材料缺失 | case.json 缺失 | `unable_to_determine`（case_id=unknown） | status_note「case.json 缺失，无法判断任务契约」 |
| 锚点失败 | anchor_quote 在基线中找不到（ANCHOR_NOT_FOUND）或不唯一（ANCHOR_NOT_UNIQUE） | `partial` | changes.json failures + JUDGMENT LIST + change_record.md「失败」行；QC anchor 维 fail，finalize 报错；修复后 `--force apply` |
| 意见冲突 | 两条意见要求互相矛盾 | `partial` | 相关 req 取 `clarify`/`reject`，rationale 写明冲突双方；回复信如实说明「两条意见存在冲突，本次采取 … 因为 …」 |
| 意见有误 | 意见基于对基线的误读 | `success`/`partial`（视其余项） | `action=reject` + rationale 引基线原文为据；回复信礼貌说明，不得讥讽 |
| 无法补做 | 要求补实验/数据而运行期内不可得 | `partial` | `action=cannot` + `evidence_status=无法补做`；uncertainty 记「X.Y 无法补做：原因」；回复信段落必须含「无法」 |
| 权限不足 | /app/output 等目录不可写 | `partial`（尽力落盘） | 把能写的写到可写路径，uncertainty 记「路径 X 不可写，产物落于 Y」；run.log 留 traceback |
| 版本不匹配 | 输入文件中途变化（指纹失效） | 视重跑结果 | run.log 出现非 SKIP 重跑属正常；status 里说明「输入在运行期间变化，已对受影响阶段重跑」 |
| 运行失败 | 任一阶段抛异常 | `partial` | 单步失败不阻断后续；[FAIL] 进 run.log 与 JUDGMENT LIST；finalize 重算时计入 uncertainty |
| QC 失败 | qc_report overall=fail | `partial` 且 finalize 退出 1 | FINALIZE-ERROR 列出原因；修复后对对应阶段 `--force` 重跑，不允许绕过 QC 手改 result.json |

## 披露写法的统一句式

- uncertainty 条目：`<req_id 或对象> <失败类别>：<原因>；<已采取的处置>`。
  例：`2.1 无法补做：无法获得数据集 D3 授权，运行期内无法补做；已在回复信中如实说明。`
- change_records 失败条目：`status` 形如 `failed:ANCHOR_NOT_FOUND`，与 changes.json 完全一致（脚本镜像，禁止手改）。

## 禁止的「假修复」

- 手改 revised-manuscript.md 绕过 edits.json（三方一致性检查会抓到）。
- 手改 result.json 的 status（finalize 会按字段级证据重算并覆盖）。
- 删除 qc_report.json 或 state 文件伪装通过（finalize 视缺失为错误）。
