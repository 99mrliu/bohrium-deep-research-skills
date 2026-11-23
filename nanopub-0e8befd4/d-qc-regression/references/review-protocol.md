# 复核与状态协议

## 1. 判读（adjudication）记录格式

对每条 review 断言，在台账中写：

```json
{"id": "A-014", "adjudication": {
   "decision": "keep|fix|drop|downgrade",
   "reason": "为什么该 W_* 在此可接受/如何修复",
   "reviewer": "agent", "checked_against": "page 2, Table 1"}}
```

原则：判读理由必须引用原文位置，不接受「看起来没问题」。

## 2. 状态机

```
草稿 → qc_gate → 有 reject ──修复──> 复检 ──0 reject──┐
                 └─不修────> 禁止 success（partial）   │
        有 review ──逐条 adjudication──> 0 open review ─┤
        有特殊条目（not_reported/conflict/受阻区域）    │
                 └─全部写入 result.json 边界字段 ───────┤
                                                       ↓
                              status = success | partial | blocked
```

- `success`：请求范围全覆盖、0 reject、0 未判读 review、无未声明边界；
- `partial`：有缺口——必须列出：未覆盖区域、未裁定冲突、降级条目、
  人工接管位置（哪个文件哪一页什么问题）；
- `blocked`：材料不可得/无文本层且 OCR 失败——写明尝试过的工具与失败输出。

## 3. 三类边界条目的写法

| 类型 | 字段 | 要求 |
|-|-|-|
| 未报告 | status=not_reported + searched_scope | 检索范围具体到章节/表/图 |
| 无法判断 | uncertainty 条目 | 写明是证据不足、冲突还是提取失败 |
| 材料冲突 | status=conflict + conflict_with | 双方断言都保留并各自带来源 |

任何「无法判断」不得写成事实句进入断言列表。

## 4. 回归纪律

- 每次修改 qc_gate.py 后重跑 run_regression.py；漏检任何一例即回退或补规则；
- 新增错误类型时：先在 fixtures.json 加合成反例（先红），再实现检测（变绿）；
- 回归报告随交付物保存，证明本次交付所过之门的检测力。

## 5. 与平台预算的配合

- 门与回归不耗模型请求；把模型预算留给读原文与修断言；
- 900 秒内优先级：草稿 result.json → 过门 → 修 reject → 判读 review →
  回归自证 → 完善文档字段。任一时刻中断都应留下诚实 partial。
