#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rerun_consistency.py — process-qc-guard 复跑一致性审计。

重新执行指定的机器阶段命令（--cmd 可多次，或 --from-checkpoints 读检查点登记的命令），
对声明产物做 sha256 前后对比与文本 diff 摘要，判定 STABLE / DRIFT。

--cmd 格式："标签 | 命令 | 产物1,产物2"（产物路径相对 --work-dir）。
DRIFT 时输出：漂移文件清单、diff 前 5 行、可能原因分类（时间戳/随机数/字典序/环境依赖）
与消除建议；结果写 consistency_report[_tag].json 与 .md。
--inject-drift：自检模式，生成含 wall-clock 时间戳的演示产物以演示 DRIFT 检出。

退出码：0=STABLE，3=DRIFT，1=内部错误；绝不因命中而崩溃。
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA = "process-qc-guard/rerun_consistency@1"
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{9,}\.\d+|epoch", re.I)
HEX_RE = re.compile(r"\b[0-9a-f]{16,}\b", re.I)
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2,
                                       sort_keys=True) + "\n")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def parse_cmd_spec(spec):
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 3 or not parts[0] or not parts[1]:
        raise ValueError("--cmd 格式须为：标签 | 命令 | 产物1,产物2")
    outputs = [o.strip() for o in parts[2].split(",") if o.strip()]
    return {"label": parts[0], "cmd": parts[1], "outputs": outputs}


def classify_cause(old_text, new_text):
    """漂移原因粗分类，返回 (cause, advice)。"""
    if TS_RE.search(new_text) and TS_RE.search(new_text) != TS_RE.search(old_text):
        return ("时间戳", "产物含 wall-clock 时间；改用逻辑序号或固定内容，禁止 time/date 直写。")
    if TS_RE.search(new_text):
        return ("时间戳", "产物疑似含时间信息；改用逻辑序号或内容哈希作版本标识。")
    try:
        if json.loads(old_text) == json.loads(new_text):
            return ("字典序/序列化顺序", "JSON 语义相同但键序漂移；json.dumps(..., sort_keys=True) 固定序。")
    except Exception:
        pass
    if UUID_RE.search(new_text) or (HEX_RE.search(new_text) and HEX_RE.search(new_text).group()
                                    not in old_text):
        return ("随机数", "产物含随机标识；固定种子或改用内容寻址（sha256）。")
    home = os.path.expanduser("~")
    if home and home in new_text and home not in old_text:
        return ("环境依赖", "产物混入本机绝对路径/HOME；一律写相对路径。")
    return ("未知/环境依赖", "对比运行环境（PATH、locale、工具版本）；将外部输入固定在 manifest。")


def diff_first5(old_text, new_text):
    diff = list(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                     lineterm="", n=1))
    return diff[:5]


def run_stage(work_dir, spec, timeout=300):
    """执行单个机器阶段并对比产物哈希，返回阶段报告。"""
    resolved = [os.path.join(work_dir, o) for o in spec["outputs"]]
    before = {o: sha256_file(p) for o, p in zip(spec["outputs"], resolved)}
    old_texts = {o: read_text(p) for o, p in zip(spec["outputs"], resolved)}
    run_error = None
    try:
        proc = subprocess.run(spec["cmd"], shell=True, cwd=work_dir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
        if proc.returncode != 0:
            run_error = "命令退出码 %d：%s" % (proc.returncode,
                                              proc.stderr.decode("utf-8", "replace")[:200])
    except Exception as exc:
        run_error = "%s: %s" % (type(exc).__name__, exc)
    after = {o: sha256_file(p) for o, p in zip(spec["outputs"], resolved)}

    outputs, drifted = [], []
    for o in spec["outputs"]:
        status = "STABLE" if before[o] == after[o] else "DRIFT"
        if before[o] is None and after[o] is None:
            status = "MISSING"
        outputs.append({"path": o, "before": before[o], "after": after[o],
                        "status": status})
        if status == "DRIFT":
            cause, advice = classify_cause(old_texts[o], read_text(resolved[spec["outputs"].index(o)]))
            drifted.append({"path": o, "cause": cause, "advice": advice,
                            "diff_first5": diff_first5(old_texts[o],
                                                       read_text(os.path.join(work_dir, o)))})
    return {"label": spec["label"], "cmd": spec["cmd"], "run_error": run_error,
            "outputs": outputs, "drifted": drifted}


def load_registered_cmds(work_dir):
    """从 checkpoints 读取登记的复跑命令（cmd + outputs）。"""
    specs = []
    d = os.path.join(work_dir, "checkpoints")
    if not os.path.isdir(d):
        return specs
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            continue
        cmd = doc.get("cmd")
        outs = [o.get("path") for o in doc.get("outputs", []) if o.get("path")]
        if cmd and outs:
            rel = [os.path.relpath(o, work_dir) for o in outs]
            specs.append({"label": "ckpt:" + doc.get("stage", fn), "cmd": cmd,
                          "outputs": rel})
    return specs


def inject_drift(work_dir):
    """自检模式：构造含 wall-clock 时间戳的演示产物，用于演示 DRIFT 检出。"""
    demo_dir = os.path.join(work_dir, "_consistency_demo")
    os.makedirs(demo_dir, exist_ok=True)
    art = os.path.join(demo_dir, "drift_artifact.txt")
    with open(art, "w", encoding="utf-8") as f:
        f.write("baseline\n")
    py = ("import time,pathlib;"
          "pathlib.Path(r'%s').write_text('tick %%f\\n' %% time.time(), encoding='utf-8')"
          % art)
    spec = "inject-drift-demo | python3 -c \"%s\" | %s" % (
        py, os.path.relpath(art, work_dir))
    return parse_cmd_spec(spec)


def write_reports(work_dir, tag, report):
    suffix = ("_" + tag) if tag else ""
    jpath = os.path.join(work_dir, "consistency_report%s.json" % suffix)
    atomic_write_json(jpath, report)
    lines = ["# 复跑一致性报告", "",
             "- 判定：**%s**" % report["verdict"], ""]
    for st in report["stages"]:
        lines.append("## 阶段 %s" % st["label"])
        lines.append("- 命令：`%s`" % st["cmd"])
        if st.get("run_error"):
            lines.append("- 执行告警：%s" % st["run_error"])
        for o in st["outputs"]:
            lines.append("  - `%s`：%s" % (o["path"], o["status"]))
        for d in st["drifted"]:
            lines.append("  - 漂移 `%s`：原因=%s；建议=%s" % (d["path"], d["cause"], d["advice"]))
            lines.append("    ```diff")
            lines.extend("    " + l for l in d["diff_first5"])
            lines.append("    ```")
        lines.append("")
    mpath = os.path.join(work_dir, "consistency_report%s.md" % suffix)
    atomic_write_text(mpath, "\n".join(lines))
    return jpath, mpath


def main(argv=None):
    ap = argparse.ArgumentParser(description="process-qc-guard 复跑一致性审计（STABLE/DRIFT）。")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--cmd", action="append", default=[],
                    help="机器阶段命令，格式：标签 | 命令 | 产物1,产物2（可多次）")
    ap.add_argument("--from-checkpoints", action="store_true",
                    help="改从 checkpoints 读取登记的复跑命令")
    ap.add_argument("--inject-drift", action="store_true",
                    help="自检模式：生成时间戳演示产物以演示 DRIFT 检出")
    ap.add_argument("--tag", default="", help="报告文件名后缀标签，如 stable/drift")
    args = ap.parse_args(argv)

    try:
        specs = []
        if args.inject_drift:
            specs.append(inject_drift(args.work_dir))
        if args.from_checkpoints:
            specs.extend(load_registered_cmds(args.work_dir))
        for spec in args.cmd:
            specs.append(parse_cmd_spec(spec))
        if not specs:
            print(json.dumps({"ok": False, "reason": "未提供任何复跑命令（--cmd/--from-checkpoints/--inject-drift）"},
                             ensure_ascii=False))
            return 1

        stages = [run_stage(args.work_dir, s) for s in specs]
        drift_files = [d for st in stages for d in st["drifted"]]
        verdict = "DRIFT" if drift_files else "STABLE"
        report = {"schema": SCHEMA, "verdict": verdict, "stages": stages,
                  "drift_files": [d["path"] for d in drift_files],
                  "causes": [{"path": d["path"], "cause": d["cause"],
                              "advice": d["advice"]} for d in drift_files]}
        jpath, mpath = write_reports(args.work_dir, args.tag, report)
        print(json.dumps({"ok": True, "verdict": verdict,
                          "drift_files": report["drift_files"],
                          "report_json": jpath, "report_md": mpath},
                         ensure_ascii=False, indent=2))
        return 3 if verdict == "DRIFT" else 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
