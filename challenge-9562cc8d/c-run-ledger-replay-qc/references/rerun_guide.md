# 复跑与核验指南

## 自动复跑证明（每次运行自动执行）

`scripts/replay_check.py` 在流水线末尾自动：

1. 在系统临时目录新建独立 `work/`、`out/`；
2. 以 `RUN_CASE_REPLAY_CHILD=1` 环境变量完整复跑 `run_case.py`
   （子进程跳过复跑，防止递归；限时 600 秒）；
3. 收集两次运行的产物并分类比对：

| 产物类别 | 比对方式 | 理由 |
|---|---|---|
| 文本（statistics/cleaning/captions/check 等 JSON/Markdown） | 逐字节 | 计算结果必须确定 |
| PNG 位图 | 逐字节（SHA-256） | Agg 后端 + 固定种子下渲染确定 |
| SVG/PDF | 归一化后比对 | 剔除挥发性元数据（见下） |

4. 输出 `replay_report.json`：`all_passed`、逐文件哈希与一致性、
   不一致文件的首处差异偏移。

## 归一化规则（挥发性元数据清单）

- SVG：`<dc:date>` 创建时间；随机 clip-path/marker/path-collection/
  image id（`p…`/`m…`/`C…`/`image…` 哈希）；内嵌 base64 位图
  （PNG 编码时间戳）；
- PDF：`/CreationDate`、`/ModDate`、trailer `/ID` 随机文档标识。

归一化只做"剔除元数据"，不触碰任何图形内容（路径坐标、文本、样式），
比对的是两张图的实质内容。

## 人工复跑（第三方核验）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /tmp/rerun/work --out /tmp/rerun/out
diff <(jq -S . /app/output/statistics.json) <(jq -S . /tmp/rerun/out/statistics.json)
```

文本产物在任何机器、任何目录下应逐字节一致；图件在同一 matplotlib
版本下一致，跨版本可能有字体微调（记录于 run_manifest.json）。

## 复核数字

`check_report.json` 已包含重读源文件复算 mean/n/r 的结果；手工抽验
任一数字：`sqlite3 <db> "SELECT avg(<col>) FROM <table>"` 或
`awk -F,` 对 CSV 求均值，应与 statistics.json 在舍入内一致。
