#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step_table.py — 基于 commands.json 生成"输入→命令→输出→判断条件"步骤表骨架。

纯标准库、确定性、无网络。脚本只负责骨架与顺序建议：
- 顺序：优先按日志时间戳（source_kind=log 的 command 线索）排序；
  脚本命令若能匹配到日志记录则继承其时间线位置，匹配不到则排在其后并诚实标注；
  无任何时间戳日志时，按 file:line 出现顺序排列并明确标注"顺序待人工确认"。
- 判断条件列一律留作"待模型补全"，本脚本不臆造。

用法：
    python3 scripts/step_table.py --commands <commands.json> --out <steps.md>
"""
import argparse
import json
import os
import re
import sys

NAME_RULES = [
    (re.compile(r"download|wget|curl|kaggle|huggingface", re.I), "数据获取"),
    (re.compile(r"preprocess|preprocess|clean|prepare|tokeniz|build_vocab|normalize", re.I), "数据预处理"),
    (re.compile(r"train|fit|finetune|fine-tune", re.I), "模型训练"),
    (re.compile(r"eval|validat|test\b", re.I), "模型评估"),
    (re.compile(r"predict|infer|generat|decode", re.I), "推理/生成"),
    (re.compile(r"install|setup|pip|conda", re.I), "环境准备"),
]

IN_FLAGS = ("--input", "--input-file", "--input_file", "--data", "--data-dir", "--data_dir",
            "--data-path", "--data_path", "--dataset", "--train-file", "--train_file",
            "--ckpt", "--checkpoint", "--model")
OUT_FLAGS = ("--output", "--output-dir", "--output_dir", "--out", "--out-dir",
             "--save", "--save-dir", "--model-out")

WS_RE = re.compile(r"\s+")


def norm(text):
    return WS_RE.sub(" ", text.strip())


def split_flag(token):
    if token.startswith("--") and "=" in token:
        k, v = token.split("=", 1)
        return k, v
    return token, None


def flag_value(tokens, flags):
    for i, tok in enumerate(tokens):
        k, v = split_flag(tok)
        if k in flags:
            if v is not None:
                return v
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                return tokens[i + 1]
    return ""


def infer_name(text, idx):
    # 优先按程序名（.py/.sh 脚本名或首个 token）判断，避免参数值（如 clean.csv）误判
    tokens = text.split()
    probe = " ".join([t for t in tokens if t.endswith((".py", ".sh"))] or tokens[:1])
    for rx, name in NAME_RULES:
        if rx.search(probe):
            return name
    for rx, name in NAME_RULES:
        if rx.search(text):
            return name
    return "步骤%d（名称待模型补全）" % idx


def main():
    ap = argparse.ArgumentParser(description="生成方法-实验步骤表骨架")
    ap.add_argument("--commands", required=True, help="command_mine.py 产出的 commands.json")
    ap.add_argument("--out", required=True, help="输出 steps.md 路径")
    args = ap.parse_args()

    if not os.path.isfile(args.commands):
        print("ERROR: 找不到 %s，请先运行 command_mine.py" % args.commands, file=sys.stderr)
        return 2
    with open(args.commands, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])

    commands = [it for it in items if it["type"] == "command"]
    script_cmds = [it for it in commands if it["source_kind"] != "log"]
    log_cmds = [it for it in commands if it["source_kind"] == "log" and it.get("log_time")]
    log_cmds.sort(key=lambda it: (it["log_time"], it["file"], it["line"]))

    notes = []
    steps = []

    if log_cmds:
        notes.append("顺序依据：日志时间线（%s 等 %d 条带时间戳的执行记录）。"
                     % (log_cmds[0]["file"], len(log_cmds)))
        used = set()
        for it in script_cmds:
            ntext = norm(it["text"])
            match_idx = None
            for j, lc in enumerate(log_cmds):
                if j in used:
                    continue
                ltext = norm(lc["text"])
                if ntext == ltext or ntext in ltext or ltext.endswith(ntext):
                    match_idx = j
                    break
            if match_idx is not None:
                used.add(match_idx)
                steps.append({"item": it, "order_key": (0, match_idx, 0),
                              "log_time": log_cmds[match_idx]["log_time"], "in_log": True})
            else:
                steps.append({"item": it, "order_key": (1, it["file"], it["line"]),
                              "log_time": None, "in_log": False})
        orphan_logs = [lc for j, lc in enumerate(log_cmds) if j not in used]
        for lc in orphan_logs:
            notes.append("警告：日志 %s 中的命令 `%s` 未在任何脚本中找到对应，请人工核对。"
                         % ("%s:%d" % (lc["file"], lc["line"]), norm(lc["text"])))
        unmatched = [s for s in steps if not s["in_log"]]
        for s in unmatched:
            notes.append("警告：脚本命令 `%s`（%s:%d）未在日志中出现，其顺序位置为推测。"
                         % (norm(s["item"]["text"]), s["item"]["file"], s["item"]["line"]))
    else:
        notes.append("顺序依据：未发现带时间戳的执行日志，以下顺序仅为 file:line 出现顺序，"
                     "**顺序待人工确认**。")
        for it in script_cmds:
            steps.append({"item": it, "order_key": (0, it["file"], it["line"]),
                          "log_time": None, "in_log": False})

    steps.sort(key=lambda s: str(s["order_key"]))

    if not steps:
        notes.append("警告：commands.json 中没有 type=command 的线索，步骤表为空。"
                     "请人工从材料中补录命令后重跑，或在正文中诚实说明命令不可得。")

    lines = []
    lines.append("# 方法与实验步骤表（骨架）")
    lines.append("")
    lines.append("> 由 step_table.py 自动生成。`判断条件` 列留待模型依据材料补全；")
    lines.append("> 本脚本不臆造任何命令、输入或输出。")
    lines.append("")
    for note in notes:
        lines.append("- %s" % note)
    lines.append("")
    lines.append("| 步骤号 | 名称 | 输入 | 命令/操作 | 预期输出 | 判断条件（待模型补全） | 来源 |")
    lines.append("|---:|---|---|---|---|---|---|")
    for i, s in enumerate(steps, start=1):
        it = s["item"]
        tokens = norm(it["text"]).split()
        inp = flag_value(tokens, IN_FLAGS) or "（待模型补全）"
        outp = flag_value(tokens, OUT_FLAGS) or "（待模型补全）"
        name = infer_name(it["text"], i)
        src = "%s:%d" % (it["file"], it["line"])
        if s["log_time"]:
            src += "；日志 %s" % s["log_time"]
        if not s["in_log"] and log_cmds:
            src += "；未匹配日志"
        cmd = norm(it["text"]).replace("|", "\\|")
        lines.append("| %d | %s | %s | `%s` | %s | 待补：依据材料写明退出码/产物存在性/指标阈值等 | %s |"
                     % (i, name, inp, cmd, outp, src))
    lines.append("")
    lines.append("## 下一步")
    lines.append("")
    lines.append("1. 模型逐行补全 `判断条件`：可观察、可判定的标准（如退出码为 0、`data/clean.csv` 存在、")
    lines.append("   日志出现 `eval done`、指标不低于某阈值），并为每个判断条件标注材料来源。")
    lines.append("2. 模型据此撰写章节正文，保持步骤号与命令原样，不得改写任何 flag。")
    lines.append("3. 写完后运行 repro_check.py 核验命令一致性与顺序一致性。")
    lines.append("")

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("step_table: 生成 %d 步骨架 -> %s（日志线索 %d 条）"
          % (len(steps), args.out, len(log_cmds)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
