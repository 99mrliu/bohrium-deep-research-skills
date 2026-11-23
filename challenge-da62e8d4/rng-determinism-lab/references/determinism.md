# 执行确定性取证参考（determinism reference）

本文件是 rng-determinism-lab 的知识底稿：非确定性来源分类、可观测信号与固定方法、
种子三分类登记法、以及 unstable 时的归因边界。所有结论仅服务于"同机重跑是否得到
同一个数"这一执行确定性问题，不构成与论文数值的任何比较结论。

## 1. 非确定性来源分类表

| 类别 | 典型来源 | 可观测信号 | 固定方法 |
|------|----------|------------|----------|
| 未播种 RNG | `random.*`、`np.random.*`、`torch.rand*` 调用而无对应 seed | code_audit 报"未播种 RNG"；replay 判 unstable 且首分数值即分叉 | 显式播种并把种子写进参数表；若候选不支持种子参数，只记录事实，不改码 |
| 种子来源不可复现 | `random.seed(time.time())`、`os.urandom`、`secrets.*` | seed 实参非字面量告警；risks 中出现 system_entropy / clock | 改为字面量种子（属改码，须题目允许并登记变更），否则登记为不可复现 |
| 哈希序（PYTHONHASHSEED） | `set(...)` / `frozenset(...)` 构造后遍历、`hash(str/bytes)`、dict 依赖 str 哈希的间接路径 | risks 中 hash_order；不设 PYTHONHASHSEED 时跨进程 unstable，设 0 后 identical | 固定 `PYTHONHASHSEED=0`（注意：必须在解释器启动前设置，replay.py 已强制）；长期方案是排序后遍历 |
| BLAS/线程数 | OpenBLAS/MKL/OMP 多线程下浮点归约顺序随线程调度变化 | 同机重放数值尾部（最后几位）抖动；设 `OMP_NUM_THREADS=1` 等后消失 | 固定 `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1` |
| 浮点归约顺序 | 并行 reduction、atomics、不同指令集路径（AVX/FMA） | 数值序列长度一致但个别元素末位不同；跨机型差异大于同机差异 | 同机固定线程数即可稳定；跨机差异属预期，需容差比较（超出本 Skill 范围） |
| GPU | cuDNN benchmark 模式、非确定性 kernel、atomicAdd | CPU 重放 identical 而 GPU unstable；`torch.backends.cudnn.benchmark=True` | `torch.use_deterministic_algorithms(True)`、`CUBLAS_WORKSPACE_CONFIG=:4096:8`、必要时改 CPU 重放 |
| 时间戳/时钟 | `time.time()`、`datetime.now()` 进入输出或文件名 | risks 中 clock；stdout 仅时间数字不同 → numerically_stable | 若时间只进输出：numerically_stable 可接受；若驱动逻辑：必须固定或打桩 |
| 并发调度 | threading/multiprocessing/asyncio/concurrent.futures | risks 中 concurrency；结果随完成顺序变化 | 收集结果后按确定性键排序再归约；或串行重放 |
| 外部进程/网络 | subprocess 调外部命令、socket、读外部服务 | risks 中 subprocess/network；stderr 出现外部命令输出 | 外部行为不在重放控制范围内：登记为边界外依赖，必要时 mock（属改码） |
| 环境变量依赖 | `os.environ.get` / `os.getenv` 读取配置 | risks 中 env_dependency | 把相关变量纳入 env_snapshot 登记并在重放时显式设定 |

## 2. 种子三分类登记法

复现报告中的每个种子必须归入以下三类之一，禁止含糊：

1. **论文明示（paper-specified）**：论文正文/附录明确给出的种子值。登记：数值 +
   论文位置（页/节/表）。
2. **代码默认（code-default）**：候选代码里写死的字面量种子。登记：数值 + 文件与行号
   （code_audit 的 seed_calls 直接给出）。注意：组织方合成代码 ≠ 作者原代码，代码默认
   种子不能当作"论文使用的种子"。
3. **自行设定（operator-chosen）**：候选不支持种子参数、为做受控重放而在运行侧固定
   的种子（如包装器设置的环境变量）。登记：数值 + 设定方式 + 明确标注"非论文/非原码"。

若代码用变量/环境变量做种子（seed_calls 中 arg_literal=false），必须追到实际取值再归类；
追不到就登记"种子来源不可复现"，这是一个诚实结论，不是失败。

## 3. unstable 时的归因边界

- **同机不稳定 ≠ 实现错误。** 它只说明"这份代码在这台机器上重跑不给出同一个数"。
  原因可能是未播种、哈希序、线程归约、GPU、时钟——需要按上表逐项排查。
- **先固定，再比较。** 在同机重放都不稳定时，任何"与论文数值不一致"的陈述都没有
  意义：你不知道差异来自论文还是来自噪声。正确顺序是：
  1. replay 判 unstable → 2. 按分类表固定可固定的来源（播种、PYTHONHASHSEED、
     线程数）→ 3. 重放至 identical / numerically_stable → 4. 才允许进入下游的
     指标比较与差异归因。
- **固定不了也要如实写。** 若候选不接受种子、或不稳定来自不可控外部依赖，就在
  result.json 中写明"同机执行不确定，比较结论不可信"，status 用 partial 并给出
  不确定性说明——这比硬凑一个比较数字诚实得多。
- **numerically_stable 的语义**：stdout 文本不同但数值序列完全一致（典型：耗时、
  时间戳不同）。这意味着"声明的数值指标"是可复现的，可进入比较；但应在来源定位中
  注明文本差异点。

## 4. 本 Skill 的证据边界

- code_audit 是静态分析：看不到动态 import、`eval`/`exec`、通过别名间接调用的 RNG
  （已覆盖常见 as 别名），也看不到 C 扩展内部的随机性。审计通过 ≠ 确定。
- replay 是机械比较：数值抽取用正则，会把行号、计数器等非指标数字一并抽取；
  unstable 的首分叉索引指向的是"抽取序列"中的位置，需人工核对语义。
- env_snapshot 只记录事实，不验证"装上这些版本就能复现"。
