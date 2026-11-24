#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""command_mine.py — 从案例材料中挖掘真实命令行、环境、种子、数据与依赖线索。

纯标准库、确定性、无网络。只读取材料，不修改、不臆造：
每条提取结果都带 file:line 来源，类型为 command / env / seed / data / dep 之一。

用法：
    python3 scripts/command_mine.py --case <材料目录> --out <输出目录>

产物：
    <输出目录>/commands.json   机器可读，items 列表，每项含 id/type/text/file/line/source_kind/log_time
    <输出目录>/commands.md     人工可读表格
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 识别规则

EXEC_RE = re.compile(
    r"^(python3?|pip3?|conda|bash|sh|zsh|wget|curl|git|kaggle|"
    r"huggingface-cli|hf|make|cmake|gcc|g\+\+|nvidia-smi|export|"
    r"source|cd|mkdir|tar|unzip|java|node|Rscript|perl|awk|sed)\b"
)

TS_RE = re.compile(r"\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\]?")

SEED_RES = [
    re.compile(r"--seed[ =](\d+)"),
    re.compile(r"--random[-_]seed[ =](\d+)"),
    re.compile(r"\bseed\s*=\s*(\d+)"),
    re.compile(r"\bSEED\s*=\s*(\d+)"),
    re.compile(r"manual_seed\(\s*(\d+)"),
    re.compile(r"random\.seed\(\s*(\d+)"),
    re.compile(r"(?:np|numpy)\.random\.seed\(\s*(\d+)"),
    re.compile(r"set_seed\(\s*(\d+)"),
]

VERSION_RES = [
    re.compile(r"[Pp]ython\s*3\.\d+(?:\.\d+)?"),
    re.compile(r"torch\s*[=<>~ ]*\s*\d+\.\d+[\w.\-+]*"),
    re.compile(r"transformers\s*[=<>~ ]*\s*\d+\.\d+[\w.\-+]*"),
    re.compile(r"CUDA\s*(?:Version)?\s*:?\s*\d+\.\d+", re.IGNORECASE),
    re.compile(r"\bcu\d{3,4}\b"),
]

GPU_RES = [
    re.compile(r"NVIDIA\s+[A-Za-z0-9\-]+(?:-[A-Za-z0-9\-]+)*"),
    re.compile(r"\b(?:A100|V100|H100|H800|A800|RTX\s?\d{4}\w*|L40S?|T4|P100)\b"),
    re.compile(r"CUDA_VISIBLE_DEVICES\s*=\s*\S+"),
    re.compile(r"cuda:\d+"),
]

URL_RE = re.compile(r"https?://[^\s)\]\"']+")

DATA_CMD_RE = re.compile(r"^(wget|curl|kaggle|huggingface-cli|hf|aria2c|rsync)\b")

DATA_FLAG_RE = re.compile(r"--(?:data(?:[-_](?:dir|path|file))?|input(?:[-_]file)?|dataset)[ =](\S+)")

DEP_LINE_RE = re.compile(r"^[A-Za-z0-9_\-\.\[\]]+\s*[=<>~!]")  # requirements.txt 风格

SHELL_SKIP_RE = re.compile(r"^(set\s+-|fi\b|then\b|else\b|done\b|do\b|if\b|for\b|while\b|echo\b)")

CJK_RE = re.compile(r"[一-鿿]")

FENCE_RE = re.compile(r"^\s*```(\w*)")


# ---------------------------------------------------------------- 工具函数

def iter_files(root):
    """确定性顺序遍历材料文件。"""
    picked = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            picked.append(os.path.join(dirpath, name))
    return sorted(picked)


def file_kind(relpath):
    base = os.path.basename(relpath)
    low = base.lower()
    ext = os.path.splitext(low)[1]
    if ext == ".sh":
        return "script"
    if low in ("makefile", "gnumakefile") or ext == ".mk":
        return "makefile"
    if ext in (".md", ".markdown", ".rst") or low.startswith("readme"):
        return "doc"
    if ext == ".log":
        return "log"
    if ext == ".py":
        return "python"
    if low.startswith("requirements") or low in (
        "environment.yml", "environment.yaml", "pyproject.toml", "pipfile", "setup.py",
    ):
        return "depfile"
    if ext in (".yml", ".yaml") and "env" in low:
        return "depfile"
    return "other"


def join_continuations(lines):
    """拼接反斜杠续行，返回 [(起始行号(1基), 拼接后文本)]。"""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        start = i + 1
        text = lines[i].rstrip("\n")
        while text.rstrip().endswith("\\") and i + 1 < n:
            text = text.rstrip()[:-1].rstrip() + " " + lines[i + 1].strip()
            i += 1
        out.append((start, text))
        i += 1
    return out


def cut_at_cjk(text):
    """截断到第一个含 CJK 的空白分词之前（ prose 中命令后接中文叙述）。"""
    toks = text.split()
    kept = []
    for tok in toks:
        if CJK_RE.search(tok):
            break
        kept.append(tok)
    return " ".join(kept)


# ---------------------------------------------------------------- 提取器

class Miner:
    def __init__(self):
        self.items = []

    def add(self, type_, text, file, line, source_kind, log_time=None):
        text = text.strip()
        if not text:
            return
        self.items.append({
            "type": type_,
            "text": text,
            "file": file,
            "line": line,
            "source_kind": source_kind,
            "log_time": log_time,
        })

    # -- 通用：从任意一行文本中找种子 / 版本 / GPU / URL 线索
    def scan_clues(self, text, file, line, source_kind, log_time=None):
        for rx in SEED_RES:
            m = rx.search(text)
            if m:
                self.add("seed", "seed=%s" % m.group(1), file, line, source_kind, log_time)
                break
        matched = set()
        for rx in VERSION_RES:
            for m in rx.finditer(text):
                sig = m.group(0).strip()
                if sig.lower() not in matched:
                    matched.add(sig.lower())
                    self.add("env", sig, file, line, source_kind, log_time)
        for rx in GPU_RES:
            for m in rx.finditer(text):
                sig = m.group(0).strip()
                if sig.lower() not in matched:
                    matched.add(sig.lower())
                    self.add("env", sig, file, line, source_kind, log_time)
        for m in URL_RE.finditer(text):
            self.add("data", m.group(0), file, line, source_kind, log_time)

    # -- shell 风格命令行（.sh / Makefile / doc 代码块）
    def classify_shell(self, cmd, file, line, source_kind, log_time=None):
        head = cmd.split(None, 1)[0] if cmd.split() else ""
        if cmd.startswith("export ") or cmd.startswith("CUDA_VISIBLE_DEVICES="):
            self.add("env", cmd, file, line, source_kind, log_time)
        elif DATA_CMD_RE.match(cmd):
            self.add("data", cmd, file, line, source_kind, log_time)
        elif head in ("pip", "pip3", "conda") and " install" in (" " + cmd):
            self.add("dep", cmd, file, line, source_kind, log_time)
        elif head == "nvidia-smi":
            self.add("env", cmd, file, line, source_kind, log_time)
        elif EXEC_RE.match(cmd) and not SHELL_SKIP_RE.match(cmd):
            self.add("command", cmd, file, line, source_kind, log_time)
        else:
            return
        self.scan_clues(cmd, file, line, source_kind, log_time)
        m = DATA_FLAG_RE.search(cmd)
        if m:
            self.add("data", m.group(1), file, line, source_kind, log_time)

    def parse_shell_text(self, lines, file, source_kind, strip_makefile_tab=False):
        for lineno, text in join_continuations(lines):
            s = text.strip()
            if strip_makefile_tab and text.startswith("\t"):
                s = text.strip()
            if not s or s.startswith("#"):
                continue
            if SHELL_SKIP_RE.match(s):
                continue
            self.classify_shell(s, file, lineno, source_kind)

    # -- 各类文件
    def mine_script(self, path, rel):
        with open(path, encoding="utf-8", errors="replace") as f:
            self.parse_shell_text(f.readlines(), rel, "script")

    def mine_makefile(self, path, rel):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        cmds = [ln for ln in lines if ln.startswith("\t")]
        self.parse_shell_text(cmds, rel, "makefile")

    def mine_doc(self, path, rel):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        # 1) 围栏代码块按 shell 解析
        in_block, buf, buf_start = False, [], 0
        for idx, ln in enumerate(lines, start=1):
            m = FENCE_RE.match(ln)
            if m:
                if not in_block:
                    in_block, buf, buf_start = True, [], idx + 1
                else:
                    self.parse_shell_text(buf, rel, "doc")
                    in_block, buf = False, []
                continue
            if in_block:
                buf.append(ln)
        if in_block:
            self.parse_shell_text(buf, rel, "doc")
        # 2) 正文中的版本 / GPU / URL / 种子线索
        for idx, ln in enumerate(lines, start=1):
            if FENCE_RE.match(ln):
                continue
            self.scan_clues(ln, rel, idx, "doc")

    def mine_log(self, path, rel):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for idx, ln in enumerate(lines, start=1):
            raw = ln.rstrip("\n")
            ts = None
            m = TS_RE.search(raw)
            if m:
                ts = m.group(1).replace("T", " ")
            # "$ cmd" 形式的执行记录
            dm = re.search(r"\$\s+(\S.*)$", raw)
            if dm:
                cmd = cut_at_cjk(dm.group(1).strip())
                if EXEC_RE.match(cmd):
                    self.classify_shell(cmd, rel, idx, "log", log_time=ts)
                    continue
            self.scan_clues(raw, rel, idx, "log", ts)

    def mine_python(self, path, rel):
        with open(path, encoding="utf-8", errors="replace") as f:
            for idx, ln in enumerate(f, start=1):
                s = ln.strip()
                if not s or s.startswith("#!"):
                    continue
                hit = False
                for rx in SEED_RES:
                    m = rx.search(s)
                    if m:
                        self.add("seed", "seed=%s" % m.group(1), rel, idx, "python")
                        hit = True
                        break
                for rx in GPU_RES[:3]:
                    if rx.search(s):
                        self.add("env", s, rel, idx, "python")
                        hit = True
                        break
                if not hit and re.search(r"__version__\s*=", s):
                    self.add("env", s, rel, idx, "python")

    def mine_depfile(self, path, rel):
        base = os.path.basename(rel).lower()
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for idx, ln in enumerate(lines, start=1):
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if base.startswith("requirements") or base == "pipfile":
                if DEP_LINE_RE.match(s) or re.match(r"^[A-Za-z0-9_\-\.]+$", s):
                    self.add("dep", s, rel, idx, "depfile")
            elif base.endswith((".yml", ".yaml")):
                if s.startswith("- ") and DEP_LINE_RE.match(s[2:].strip()):
                    self.add("dep", s[2:].strip(), rel, idx, "depfile")
            else:
                self.scan_clues(s, rel, idx, "depfile")


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="从材料中挖掘命令/环境/种子/数据/依赖线索")
    ap.add_argument("--case", required=True, help="案例材料目录")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    if not os.path.isdir(args.case):
        print("ERROR: 材料目录不存在: %s" % args.case, file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)

    miner = Miner()
    dispatch = {
        "script": Miner.mine_script,
        "makefile": Miner.mine_makefile,
        "doc": Miner.mine_doc,
        "log": Miner.mine_log,
        "python": Miner.mine_python,
        "depfile": Miner.mine_depfile,
    }
    scanned = 0
    for path in iter_files(args.case):
        rel = os.path.relpath(path, args.case)
        kind = file_kind(rel)
        fn = dispatch.get(kind)
        if fn is None:
            continue
        try:
            fn(miner, path, rel)
            scanned += 1
        except OSError as exc:
            print("WARN: 跳过不可读文件 %s: %s" % (rel, exc), file=sys.stderr)

    # 稳定排序并编号
    kind_rank = {"script": 0, "makefile": 1, "doc": 2, "log": 3, "python": 4, "depfile": 5}
    miner.items.sort(key=lambda it: (kind_rank.get(it["source_kind"], 9), it["file"], it["line"],
                                     it["type"], it["text"]))
    for i, it in enumerate(miner.items, start=1):
        it["id"] = i

    by_type = {}
    for it in miner.items:
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1

    doc = {
        "meta": {
            "root": args.case,
            "scanned_files": scanned,
            "item_count": len(miner.items),
            "by_type": by_type,
            "generated_by": "command_mine.py (stdlib-only, deterministic, offline)",
        },
        "items": miner.items,
    }
    json_path = os.path.join(args.out, "commands.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(args.out, "commands.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 命令与环境线索挖掘结果\n\n")
        f.write("材料目录：`%s`；扫描文件数：%d；线索总数：%d。\n\n"
                % (args.case, scanned, len(miner.items)))
        f.write("类型统计：%s\n\n" % (", ".join("%s=%d" % kv for kv in sorted(by_type.items())) or "无"))
        f.write("| id | 类型 | 内容 | 来源 | 日志时间 |\n")
        f.write("|---:|---|---|---|---|\n")
        for it in miner.items:
            text = it["text"].replace("|", "\\|")
            f.write("| %d | %s | `%s` | %s:%d | %s |\n"
                    % (it["id"], it["type"], text, it["file"], it["line"], it["log_time"] or "-"))

    print("command_mine: 扫描 %d 个文件，提取 %d 条线索 -> %s / %s"
          % (scanned, len(miner.items), json_path, md_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
