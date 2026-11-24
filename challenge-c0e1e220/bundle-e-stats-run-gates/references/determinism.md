# 确定性约定（determinism）

replay_diff 的判定标准：同一输入 + 同一 decisions.json + 同一参数，换目录完整复跑后，
除声明的易变字段外，work/ 与 output/ 全部产物**逐字节 sha256 一致**。
为达到这一点，本 bundle 遵守以下硬约定。

## 1. 随机数
- 唯一起源：`random.Random(20240501)`（statcore_e.BOOTSTRAP_SEED），每个结局的
  bootstrap 独立播种一次，B=2000 固定。
- 禁止：`random` 全局实例、`numpy.random` 不播种、`time` 参与任何数值路径。
- Python 的 random 模块跨版本序列稳定（文档保证 Mersenne Twister 兼容性）。

## 2. 序与遍历
- 所有 JSON 输出 `json.dump(..., sort_keys=True, indent=2, ensure_ascii=False)` + 单个换行结尾。
- 任何 set 迭代前先 `sorted(...)`；组标签排序用数值感知的 natural key
  （可转 float 按数值，否则按字符串，元组首元区分避免混排）。
- 字典只按插入序使用，关键输出前一律 sort_keys。
- 注意 PYTHONHASHSEED 随机化：绝不直接迭代 set 进产物。

## 3. 浮点输出
- JSON 中的浮点保持双精度原值（Python repr 最短回环表示自 3.1 起稳定）；
  NaN/Inf 一律转 null（sanitize），不产生非法 JSON。
- 展示层格式集中两处（statcore_e.fmt_p / fmt_effect，gate_check 复用同一实现）：
  - p：`p < 0.0001`（p<0.0001 时）或 `p = %.4f`；
  - 效应量：`%s = %.4f`（kind ∈ hedges_g/eta2/omega2/eps2/rank_biserial）。
  report.md 只经这两个函数写数字，G6 才能双向核对。

## 4. 易变字段（显式声明，除此之外不得存在）
- `result.json → reproducibility.timestamp_utc`
- `manifest.json → generated_at_utc`
- manifest 对 JSON 产物登记"剥离易变字段后的规范字节 sha256"（registered_hash），
  因此 manifest 本身跨次运行确定；replay_diff 可用
  `--volatile-json-path a.b.c` 追加声明（新增易变字段必须同时更新两份 DEFAULT_VOLATILE）。

## 5. 路径与参数归一化
- manifest.pipeline.argv 中 --input/--work/--output 的值替换为 <INPUT>/<WORK>/<OUTPUT>
  占位符，--plan 归一化为 basename；复跑目录不同不影响 manifest 一致性。
- manifest.inputs/stages/outputs 只记 basename + 哈希 + 大小。

## 6. 环境记录（不要求跨机一致）
- python 版本、platform 字符串写入 result.reproducibility 与 manifest.environment，
  用于审计；replay 判定在同机进行，跨机浮点一致性不作承诺（同代码同数据在同机确定）。

## 7. 常见漂移源排查（replay_diff FAIL 时）
1. 新增时间戳/随机 ID 写进产物 → 挪进 timestamp_utc 或删除；
2. set 未排序迭代 / dict 依赖环境序 → 改 sorted；
3. 从环境变量/绝对路径拼内容 → 归一化；
4. 浮点经字符串往返（str(float)）→ 直接序列化；
5. 子进程并发写同一文件 → 顺序写 + seq.log 登记。
