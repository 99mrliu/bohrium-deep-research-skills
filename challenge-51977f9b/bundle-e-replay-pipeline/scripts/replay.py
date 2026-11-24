#!/usr/bin/env python3
"""replay.py — 确定性重放与漂移检测（签名引擎二）。

manifest.json 结构：
{"steps": [{"step_id": "dedupe", "cmd": "python3 ... --output deduped.json",
            "outputs": ["deduped.json"]}, ...]}

行为：
- 在重放目录（--workdir，默认新建临时目录）中逐步骤执行 cmd（subprocess，超时 120s）。
- 每个步骤连续执行两次：两次产物哈希不一致 → 判定该步骤非确定性（V4）→ exit 3。
- 确定性步骤的产物哈希与 runlog 该步骤登记的 SHA-256 逐字节比对（按文件名匹配）：
  全部一致 → exit 0 输出 "replay: N identical, 0 differ"；
  任何漂移 → exit 3 指出首个漂移步骤及文件（V8）。
- 模型步骤（含 LLM 判断）不应进入 manifest；其产物应作为后续确定性步骤的冻结输入登记。

退出码：0=全部一致；2=输入缺失/非法（R1/R2/R5）；3=漂移或非确定性（V3–V8）。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

TIMEOUT = 120


def eprint(*a):
    print(*a, file=sys.stderr)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd, cwd):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, timeout=TIMEOUT,
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired:
        return None, "", "", True


def load_registered(runlog_path):
    """step_id -> {basename: sha256}（仅产物 outputs；同路径多次登记取最后）。"""
    reg = {}
    with open(runlog_path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError as ex:
                eprint(f"R2: runlog 第 {i} 行 JSON 非法: {ex}")
                sys.exit(2)
            step = e.get("step")
            if not step:
                continue
            m = reg.setdefault(step, {})
            for o in e.get("outputs", []):
                m[os.path.basename(o["path"])] = o["sha256"]
    return reg


def main():
    ap = argparse.ArgumentParser(
        description="按 manifest 重放确定性步骤，与 runlog 登记哈希逐字节比对，定位漂移。")
    ap.add_argument("--manifest", required=True, help="manifest.json 路径")
    ap.add_argument("--workdir", default=None, help="重放目录（默认新建临时目录）")
    ap.add_argument("--runlog", default="runlog.jsonl", help="runlog.jsonl 路径（默认当前目录）")
    args = ap.parse_args()

    if not os.path.isfile(args.manifest):
        eprint(f"R1: manifest 不存在: {args.manifest}")
        return 2
    try:
        with open(args.manifest, encoding="utf-8") as f:
            manifest = json.load(f)
        steps = manifest["steps"]
        assert isinstance(steps, list) and steps, "steps 必须是非空列表"
        for s in steps:
            assert isinstance(s["step_id"], str) and isinstance(s["cmd"], str)
            assert isinstance(s["outputs"], list) and s["outputs"], "每个步骤至少声明一个产物"
    except (json.JSONDecodeError, KeyError, AssertionError) as e:
        eprint(f"R2: manifest 结构非法: {e}")
        return 2
    if not os.path.isfile(args.runlog):
        eprint(f"R5: runlog 不存在: {args.runlog}（重放需要登记哈希作为比对基准）")
        return 2

    reg = load_registered(args.runlog)
    workdir = args.workdir or tempfile.mkdtemp(prefix="slr_replay_")
    os.makedirs(workdir, exist_ok=True)
    print(f"重放目录: {workdir}（共 {len(steps)} 个步骤，每步执行两次以检测非确定性）")

    identical = 0
    for s in steps:
        sid, cmd, outputs = s["step_id"], s["cmd"], s["outputs"]
        if sid not in reg:
            eprint(f"V5: 步骤 {sid} 在 runlog 中无产物登记，无法比对；请先 runlog record 登记该步骤")
            return 3
        runs = []
        for attempt in (1, 2):
            rc, out, err, timed_out = run_cmd(cmd, workdir)
            if timed_out:
                eprint(f"V6: 步骤 {sid} 重放超时（>{TIMEOUT}s）；该步骤可能依赖外部服务，"
                       f"应按 resume_guide.md 整改为离线确定性步骤")
                return 3
            if rc != 0:
                eprint(f"V3: 步骤 {sid} 重放命令失败（exit {rc}）: {cmd}")
                eprint(f"    stderr 摘录: {err.strip()[:400]}")
                return 3
            hashes = {}
            for o in outputs:
                p = os.path.join(workdir, o)
                if not os.path.isfile(p):
                    eprint(f"V7: 步骤 {sid} 重放后未生成声明的产物: {o}")
                    return 3
                hashes[os.path.basename(o)] = sha256_file(p)
            runs.append(hashes)
        # 非确定性检测：两次重放互比
        for base, h1 in runs[0].items():
            h2 = runs[1].get(base)
            if h1 != h2:
                eprint(f"V4: 步骤 {sid} 非确定性：两次重放产物 {base} 不一致"
                       f"（{h1[:12]}… vs {h2[:12]}…）。常见原因：产物写入时间戳/随机数/绝对路径，"
                       f"整改清单见 references/resume_guide.md")
                return 3
        # 与 runlog 登记哈希比对
        for base, h1 in runs[0].items():
            want = reg[sid].get(base)
            if want is None:
                eprint(f"V5: 步骤 {sid} 的产物 {base} 在 runlog 中无登记，无法比对")
                return 3
            if want != h1:
                eprint(f"V8: 漂移：步骤 {sid} 的产物 {base} 重放哈希 {h1[:12]}… "
                       f"≠ 登记 {want[:12]}…；首个漂移步骤 = {sid}")
                eprint(f"replay: {identical} identical, 1 differ")
                return 3
        identical += 1
        print(f"  - {sid}: 两次重放一致，且与登记一致（{len(outputs)} 个产物）")

    print(f"replay: {identical} identical, 0 differ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
