# plan.json 编写规程

## 阶段划分原则
1. 一个阶段 = 一个有明确输入/输出的原子动作（扫描、归一化、统计、异常检测、
   趋势分析、撰写、渲染、校验）。不要把整个分析塞进一个阶段——那等于放弃恢复能力。
2. `inputs` 必须列全（含脚本文件本身，这样脚本改动也会使阶段失效重跑）。
3. `outputs` 只列该阶段真实写出的文件；漏列会使 STALE 检测失效。
4. `on_fail: continue` 只用于「失败也有价值」的阶段（如探测性检查）；
   主链路上的阶段一律 `stop`。

## 本题推荐骨架（按案例套用）
```json
{"stages": [
  {"id": "scaffold",   "cmd": "python3 .../result_kit.py scaffold --case /input/case.json --out /app/output/result.json", "inputs": ["/input/case.json"], "outputs": ["/app/output/result.json"], "timeout_s": 30},
  {"id": "inventory",  "cmd": "<盘点脚本>", "inputs": ["/input"], "outputs": ["/app/work/inventory.json"], "timeout_s": 120},
  {"id": "compute",    "cmd": "<统计/复算脚本>", "inputs": ["/input", "/app/work/inventory.json"], "outputs": ["/app/work/stats.json"], "timeout_s": 300},
  {"id": "draft",      "cmd": "<由 Agent 撰写后 checkpoint>", "inputs": ["/app/work/stats.json"], "outputs": ["/app/output/result.json"], "timeout_s": 60},
  {"id": "verify",     "cmd": "python3 .../result_kit.py verify --case /input/case.json --out /app/output/result.json", "inputs": ["/input/case.json", "/app/output/result.json"], "outputs": [], "timeout_s": 30}
]}
```
「撰写」这类 Agent 动作无法包成 shell 命令时：Agent 完成撰写后用
`result_kit.py checkpoint --stage draft ...` 代替，并在 plan 中保留占位说明。

## 幂等恢复的行为约定
- SKIP 的判定 = manifest 存在 + exit=0 + cmd 未变 + 全部 input 哈希一致。
- 改 plan 中某阶段的 cmd → 该阶段与下游全部重跑（这是特性：防止新旧结果拼接）。
- manifest 是复核证据的一部分，随 /app/work 保留，不删除。
