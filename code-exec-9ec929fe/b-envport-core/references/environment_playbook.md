# 环境配置 playbook（envport-core）

## 依赖声明与版本锁定

- 核心计算：**零第三方依赖**。Python 标准库（csv/sqlite3/math/hashlib/json/
  argparse）覆盖清洗、统计、查询。p 值经不完全贝塔函数连分式实现，
  与 scipy.stats.t.sf 在 1e-10 量级一致（连分式收敛阈值 3e-14）。
- 唯一可选依赖：matplotlib（仅渲染）。在任何"requirements"中把它标为
  optional，并写明缺失时的行为（SKIPPED_no_matplotlib + 绘图数据 CSV）。
- 若评审环境要求锁定文件：给出 `requirements.txt` 为空 + 一行注释
  `# core: stdlib only; optional: matplotlib>=3.5 (rendering only)`。

## 降级与替代阶梯

| 缺失 | 影响 | 降级行为 | 替代方案 |
|-|-|-|-|
| matplotlib | 图无法渲染 | SKIPPED 回执 + 数据 CSV | 在有 matplotlib 的机器上用数据 CSV 复绘 |
| numpy/pandas | 无 | 不需要 | — |
| scipy | 无 | t 检验 p 值由内置不完全贝塔函数计算 | — |
| 网络 | 无 | 全流程离线 | — |
| Python 3.8+ 不可得 | 核心不可运行 | 报告 failed + 原因 | 用平台 scientific-python 资源，provenance 记录实际版本 |

## 确定性检查清单

1. `env` 快照落盘（Python 版本、平台、可选库有无、LANG/TZ）。
2. 输入文件 sha256 进入 profile 与 provenance —— 复核者先核对哈希再谈数字。
3. 无随机源：本引擎不使用 random/numpy.random；若你自己的补充代码涉及
   随机（自助法、抽样），必须显式设种子并把种子写进 provenance。
4. 每条命令追加到 `run_log.jsonl`（子命令、状态、耗时）；finalize 把其路径
   并入 provenance，复核者可逐条重放。
5. 浮点输出不做字符串拼接进图题以外的地方；统计结果以 JSON 数值传递。

## 路径与编码纪律

- 所有路径来自命令行参数，代码内不出现任何机器特定绝对路径。
- 读取文本按 utf-8-sig → utf-8 → gb18030 顺序尝试并在 profile 中记录实际
  编码；写出统一 UTF-8。
- CSV 方言用 Sniffer 探测，失败回退逗号；不假设表头无空格（读取时 strip）。

## 常见"跑不起来"根因速查

- `MISSING_COLUMN`：列名与数据字典/表头不一致 → 先跑 profile 看真实表头，
  用 rules.rename 对齐，不要改数据文件。
- `EMPTY_TABLE`：文件只有表头或编码错误读出空 → 看 profile 的 encoding 字段。
- `SQL_READONLY`：查询含 INSERT/UPDATE/DELETE/DROP → 改写为 SELECT；
  引擎以只读 URI 打开数据库，从机制上杜绝写操作。
- `SQL_FAILED: no such table` → 用 profile 的表清单核对，不要猜表名。
- `TTEST_GROUP_TOO_SMALL` / `CORR_TOO_FEW_PAIRS` / `OLS_TOO_FEW_ROWS`：
  样本量不足，报告该检验不可行（partial + 原因），不要硬算。
