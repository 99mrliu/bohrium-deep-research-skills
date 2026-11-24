# 仲裁与冻结政策（slr-dual-screen）

## 1. 仲裁人资格

- 仲裁人必须是**未参与该记录 A/B 判定**的第三视角。Agent 场景下：以全新上下文
  扮演仲裁人，输入仅为【该记录原文 + criteria 条款 + 双方判定与理由】，不得携带
  A 或 B 的中间推理过程。
- 仲裁人不得修改 criteria.json 来为个案让路；条款问题走版本纪律，个案问题走仲裁。
- 同一轮所有分歧宜由同一仲裁人裁决，保证尺度一致；更换仲裁人须写 change_records。

## 2. 仲裁行（adjudication.jsonl）最低信息

schema：`{record_id, round, final_decision, rationale, arbitrator}`

- `final_decision`：include / exclude（仲裁不得再产出 uncertain——仲裁的职责
  就是终结不确定）；
- `rationale`：**≥ 20 个字符**，且必须包含三要素：①引用的条款编号；②记录中
  的关键事实（题录/全文的具体内容）；③为何支持 final_decision。只写"经讨论
  决定纳入"视为无效（A2 违规）；
- 每条分歧**有且仅有一条**仲裁（A1）；对不存在分歧的记录强加仲裁一律拒绝
  （A3，防止无据改判）。

## 3. 冻结语义

全部分歧仲裁完成后，adjudicate.py 生成 frozen_set.json：

- `included_ids`：纳入记录 id 排序列表；
- `counts`：各轮计数、决策总数、仲裁总数、纳入/排除数；
- `resolution`：每条记录的终判来源（consensus / adjudication）；
- `content_sha256`：对【全部决策 + 全部仲裁 + 纳入列表】的规范化 JSON 计算的
  SHA-256。任何事后改动（改一条理由、增删一个 id）都会使 `--verify` 失败（V1）。

冻结的含义：**从此刻起，纳入集与支撑它的全部判定记录为只读证据**。

## 4. 解冻流程（确需修改时）

冻结不是不许改，而是不许"悄悄改"。解冻必须：

1. 在 result.json.change_records 写入：{time, field:"frozen_set", action:"unfreeze",
   reason, old_sha256}；
2. 修改决策/仲裁/条款（条款修改同时触发版本纪律与受影响记录重筛）；
3. 重新运行 screen_check → kappa → adjudicate --force 生成新冻结文件；
4. change_records 再写一条 {action:"refreeze", new_sha256, diff: 纳入集变化}。

新旧两个 SHA-256 同时留痕，使任何评审都能定位"纳入集在哪一刻、因为什么、
从什么变成什么"。
