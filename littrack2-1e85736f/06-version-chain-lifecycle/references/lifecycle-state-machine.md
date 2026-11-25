# 生命周期状态机定义与转换规则

## 状态集合

| 状态 | 含义 | 判定条件（链内视角） |
| --- | --- | --- |
| `preprint_only` | 仅有预印本（单版本） | 链内只有 kind=preprint 记录，最大版本号 = 1，无发表/事件信号 |
| `published` | 已有正式发表版 | 链内存在 kind=journal-article 记录，无撤稿/勘误/关注声明信号 |
| `revised` | 预印本出了新版本且尚未见正式版 | 链内只有 preprint，最大 arXiv 版本号 > 1 |
| `corrected` | 存在勘误（erratum/correction） | 链内有 correction-notice 记录、`is-correction-of`/`has-correction` 关系或 `update-to: correction` |
| `expression_of_concern` | 存在关注声明 | 链内有 `is-expression-of-concern-of`/`has-expression-of-concern` 关系 |
| `retracted` | 已撤稿（终止态） | 链内有 retraction-notice 记录、`is-retraction-of`/`has-retraction` 关系、`update-to: retraction`，或版本注释含 retract/withdrawn |

## 转换规则（正常推进）

```
preprint_only --(v1→v2…)--> revised
preprint_only --(被期刊接收)--> published
revised       --(被期刊接收)--> published
published     --(新版/更新)--> revised（较少见，以 published 为主态时保留 published 证据）
```

事件性转换（可从任意非终止态进入，优先级高于正常推进）：

```
任意状态 --(correction)--> corrected
任意状态 --(EoC)--> expression_of_concern
任意状态 --(retraction)--> retracted
```

## 裁决优先级

同一链同时满足多个条件时，按下列优先级取最高者
（保证撤稿永远不会被"已发表"掩盖）：

```
retracted > expression_of_concern > corrected > published > revised > preprint_only
```

## 预警语义映射

| 链状态 / 信号 | 预警类型 | 优先级 |
| --- | --- | --- |
| retracted / 撤稿信号 | `retraction_notice` | `critical` |
| corrected / expression_of_concern | `correction_notice` | `high` |
| 链内 >1 条记录（版本推进：预印本→正式版、v1→v2） | `version_update` | `normal` |
| 单记录链 | `new_work` | `normal` |

约束：

1. 每条链在窗口内至多产出一条预警（取语义最重的那条）。
2. 预警排序：critical → high → normal；同级按 chain_id 字典序，保证确定性。
3. 撤稿预警不可被任何去重、合并、抑制逻辑移除；若链同时是"新版本"与
   "撤稿"，预警类型必须是 `retraction_notice`。
4. 元数据贫乏（无 DOI 且无 arXiv id，或无标题）的链不做状态断言，进入
   `unresolved` 并使整体 status 降为 `partial`。
