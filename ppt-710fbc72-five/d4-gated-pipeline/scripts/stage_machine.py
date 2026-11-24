"""stage_machine.py — gated-pipeline-deck 的阶段机核心库。

提供：检查点读写、输入指纹(sha256)、幂等跳过、失败记录、
/app/output/pipeline_manifest.json 与 qa_gates.json 的增量维护、工具探测。

本文件只被同目录脚本导入，不单独运行。全部依赖为标准库。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

# 阶段表：(id, 名称)。顺序即流水线顺序。
STAGES = [
    ("S0", "bootstrap-deps"),
    ("S1", "read-inputs"),
    ("S2", "extract-source"),
    ("S3", "dissect-template"),
    ("S4", "plan-skeleton"),
    ("S5", "plan-gate"),
    ("S6", "build-deck"),
    ("S7", "export-render"),
    ("S8", "qa-gate"),
    ("S9", "finalize-result"),
]

# 机器门禁固定顺序。status 取值: pass | fail | degraded
GATE_ORDER = [
    "contract-fields-present",
    "evidence-anchors-resolve",
    "numbers-verbatim-vs-source",
    "template-layouts-used",
    "export-page-parity",
    "preview-pages-rendered",
]

SKILL_NAME = "gated-pipeline-deck"
SKILL_VERSION = "1.0.0"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_paths(paths) -> str:
    """对一组输入文件求联合指纹：路径+内容。缺失文件计入 MISSING 标记。"""
    h = hashlib.sha256()
    for p in paths:
        p = os.path.abspath(p)
        h.update(p.encode("utf-8") + b"\0")
        if os.path.isfile(p):
            h.update(sha256_file(p).encode("ascii"))
        else:
            h.update(b"MISSING")
        h.update(b"\n")
    return h.hexdigest()


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


class StageFailure(Exception):
    """阶段失败。message 说明原因；hint 给出精确的恢复命令。"""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


class Ctx:
    """一次流水线运行的上下文。"""

    def __init__(self, input_dir: str, work: str, output: str, command: str):
        self.input_dir = os.path.abspath(input_dir)
        self.work = os.path.abspath(work)
        self.output = os.path.abspath(output)
        self.command = command
        self.skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.checkpoints_dir = os.path.join(self.work, "checkpoints")
        self.gates_dir = os.path.join(self.work, "gates")
        os.makedirs(self.checkpoints_dir, exist_ok=True)
        os.makedirs(self.gates_dir, exist_ok=True)
        os.makedirs(self.output, exist_ok=True)

    # ---- 路径助手 ----
    def ckpt_path(self, sid: str) -> str:
        return os.path.join(self.checkpoints_dir, f"{sid}.json")

    def failed_path(self, sid: str) -> str:
        return os.path.join(self.checkpoints_dir, f"{sid}.failed.json")

    def result_path(self) -> str:
        return os.path.join(self.output, "result.json")

    def qa_gates_path(self) -> str:
        return os.path.join(self.output, "qa_gates.json")

    def manifest_path(self) -> str:
        return os.path.join(self.output, "pipeline_manifest.json")

    def default_resume_cmd(self) -> str:
        return (
            f"python3 {self.skill_root}/scripts/run_case.py finish "
            f"--input {self.input_dir} --work {self.work} --output {self.output}"
        )

    # ---- 检查点 ----
    def skip_if_valid(self, sid: str, inputs) -> bool:
        rec = read_json(self.ckpt_path(sid))
        if rec and rec.get("status") == "ok" and rec.get("inputs_sha") == sha256_paths(inputs):
            print(f"skip {sid} (checkpoint valid)", flush=True)
            return True
        return False

    def complete(self, sid: str, name: str, inputs, outputs, wall: float, extra: dict | None = None):
        rec = {
            "stage": sid,
            "name": name,
            "status": "ok",
            "inputs_sha": sha256_paths(inputs),
            "outputs": [str(o) for o in (outputs or [])],
            "wall_time_s": round(wall, 3),
            "at": now_iso(),
        }
        if extra:
            rec.update(extra)
        write_json(self.ckpt_path(sid), rec)
        fp = self.failed_path(sid)
        if os.path.isfile(fp):
            os.remove(fp)
        print(f"done {sid} {name} ({wall:.1f}s)", flush=True)

    def fail(self, sid: str, name: str, exc: BaseException):
        hint = getattr(exc, "hint", None) or (
            f"{self.default_resume_cmd()}  # 将从 {sid} 断点续跑"
        )
        write_json(self.failed_path(sid), {
            "stage": sid,
            "name": name,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "resume_hint": hint,
            "at": now_iso(),
        })
        print(f"FAIL {sid} {name}: {exc}", flush=True)
        print(f"RESUME: {hint}", flush=True)
        # 诚实性钩子：失败也要让 result.json 反映当前流水线状态
        result = read_json(self.result_path())
        if result:
            if result.get("status") == "success":
                result["status"] = "partial"
            log = result.setdefault("change_log", [])
            if isinstance(log, list):
                log.append({"stage": sid, "at": now_iso(), "status": "failed",
                            "note": f"最近一次运行在 {sid} 失败：{exc}；"
                                    f"当前交付物对应上一次成功状态，恢复见 {self.failed_path(sid)}"})
            unc = result.setdefault("uncertainty", [])
            if isinstance(unc, list):
                unc.append(f"{sid} 最近运行失败（{type(exc).__name__}）：修复后重跑 finish；"
                           "现有交付物是上一次成功运行的产物。")
            write_json(self.result_path(), result)
        update_manifest(self)
        sys.exit(1)


# ---- result.json 增量更新（partial-first） ----

def update_result(ctx: Ctx, patch: dict | None = None, append_log: dict | None = None,
                  add_uncertainty=None, clear_uncertainty_prefix: str | None = None) -> dict:
    result = read_json(ctx.result_path(), default={}) or {}
    if patch:
        result.update(patch)
    if clear_uncertainty_prefix is not None:
        unc = result.get("uncertainty")
        if isinstance(unc, list):
            result["uncertainty"] = [u for u in unc if not str(u).startswith(clear_uncertainty_prefix)]
    if add_uncertainty:
        unc = result.setdefault("uncertainty", [])
        if isinstance(unc, list):
            for u in add_uncertainty:
                if u not in unc:
                    unc.append(u)
    if append_log is not None:
        log = result.setdefault("change_log", [])
        if not isinstance(log, list):
            log = result["change_log"] = []
        log.append(append_log)
    write_json(ctx.result_path(), result)
    return result


# ---- qa_gates.json 增量维护 ----

def init_qa_gates(ctx: Ctx, case_id: str) -> dict:
    gates = {
        "case_id": case_id,
        "gates": [
            {"gate": g, "status": "degraded", "evidence_path": None,
             "detail": "not yet evaluated"}
            for g in GATE_ORDER
        ],
        "overall": "degraded",
        "updated_at": now_iso(),
    }
    write_json(ctx.qa_gates_path(), gates)
    return gates


def save_gate(ctx: Ctx, gate: str, status: str, evidence_path: str | None, detail: str) -> dict:
    if status not in ("pass", "fail", "degraded"):
        raise ValueError(f"bad gate status {status}")
    gates = read_json(ctx.qa_gates_path())
    if not gates or "gates" not in gates:
        gates = init_qa_gates(ctx, "unknown")
    found = False
    for entry in gates["gates"]:
        if entry["gate"] == gate:
            entry.update(status=status, evidence_path=evidence_path, detail=detail)
            found = True
    if not found:
        gates["gates"].append({"gate": gate, "status": status,
                               "evidence_path": evidence_path, "detail": detail})
    rank = {"pass": 0, "degraded": 1, "fail": 2}
    ordered = [e for g in GATE_ORDER for e in gates["gates"] if e["gate"] == g]
    extras = [e for e in gates["gates"] if e["gate"] not in GATE_ORDER]
    gates["gates"] = ordered + extras
    gates["overall"] = max((e["status"] for e in gates["gates"]), key=lambda s: rank[s])
    gates["updated_at"] = now_iso()
    write_json(ctx.qa_gates_path(), gates)
    return gates


# ---- 工具探测（结果缓存于 work/tools.json，S0 写入） ----

def detect_tools() -> dict:
    tools = {"python": {"version": platform.python_version(), "path": sys.executable}}
    degraded = []
    for mod, name, pkg in [("pptx", "python-pptx", "python-pptx"),
                           ("pymupdf", "pymupdf", "PyMuPDF"),
                           ("fitz", "pymupdf", "PyMuPDF"),
                           ("PIL", "pillow", "pillow")]:
        if name in tools:
            continue
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", None) or getattr(m, "VersionBind", "unknown")
            tools[name] = {"version": str(ver), "pip_package": pkg}
        except ImportError:
            continue
    for name in ("python-pptx", "pymupdf", "pillow"):
        if name not in tools:
            tools[name] = {"version": None, "missing": True}
            degraded.append(f"{name} (python 包缺失且 pip 安装失败)")
    soffice = None
    for cand in ("/opt/homebrew/bin/soffice", shutil.which("soffice") or ""):
        if cand and os.path.isfile(cand):
            soffice = cand
            break
    if soffice:
        ver = "unknown"
        try:
            r = subprocess.run([soffice, "--version"], capture_output=True, text=True, timeout=120)
            ver = (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            pass
        tools["soffice"] = {"path": soffice, "version": ver}
    else:
        tools["soffice"] = {"path": None, "missing": True}
        degraded.append("soffice (LibreOffice 缺失：无法导出 PDF，将记 degraded)")
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        ver = "unknown"
        try:
            r = subprocess.run([pdftoppm, "-v"], capture_output=True, text=True, timeout=30)
            ver = (r.stderr or r.stdout).strip().splitlines()[0]
        except (OSError, subprocess.TimeoutExpired, IndexError):
            pass
        tools["pdftoppm"] = {"path": pdftoppm, "version": ver}
    else:
        tools["pdftoppm"] = {"path": None, "missing": True}
        degraded.append("pdftoppm (缺失：PNG 预览将退回 pymupdf 栅格化)")
    return {"tools": tools, "degraded_tools": degraded, "detected_at": now_iso()}


# ---- pipeline_manifest.json（每个阶段完成后重写，partial-first） ----

def update_manifest(ctx: Ctx) -> dict:
    tools_state = read_json(os.path.join(ctx.work, "tools.json"),
                            default={"tools": {}, "degraded_tools": ["tools.json 尚未生成（S0 未完成）"]})
    produced_by = {}
    stage_rows = []
    for sid, name in STAGES:
        ck = read_json(ctx.ckpt_path(sid))
        failed = read_json(ctx.failed_path(sid))
        if failed and not ck:
            status = "failed"
        elif ck:
            status = "ok"
        else:
            status = "pending"
        if ck:
            for o in ck.get("outputs", []):
                produced_by[os.path.abspath(o)] = sid
        stage_rows.append({
            "stage": sid,
            "name": name,
            "status": status,
            "wall_time_s": (ck or {}).get("wall_time_s"),
            "at": (ck or {}).get("at") or (failed or {}).get("at"),
            "checkpoint": os.path.relpath(ctx.ckpt_path(sid), ctx.output) if ck else None,
            "error": (failed or {}).get("error"),
            "resume": (failed or {}).get("resume_hint") or (
                f"重跑：{ctx.default_resume_cmd()}  # {sid} 会自动从缺失/失效的检查点续跑"
            ),
        })
    artifacts = []
    for root, _dirs, files in os.walk(ctx.output):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ctx.output)
            if fn == "pipeline_manifest.json":
                artifacts.append({"path": rel, "sha256": None, "bytes": os.path.getsize(p),
                                  "produced_by": "S9 (本文件，自刷新不记 sha)"})
                continue
            who = produced_by.get(os.path.abspath(p))
            if rel == "result.json":
                who = "S1..S9 (每阶段增量重写)"
            elif rel == "qa_gates.json":
                who = "S1 初始化 / S5,S8 更新"
            artifacts.append({"path": rel, "sha256": sha256_file(p),
                              "bytes": os.path.getsize(p),
                              "produced_by": who or "unknown"})
    result = read_json(ctx.result_path(), default={}) or {}
    manifest = {
        "skill": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "case_id": result.get("case_id"),
        "generated_at": now_iso(),
        "command_context": {"input": ctx.input_dir, "work": ctx.work, "output": ctx.output},
        "stages": stage_rows,
        "artifacts": artifacts,
        "tools": tools_state.get("tools", {}),
        "degraded_tools": tools_state.get("degraded_tools", []),
        "budget": {
            "model_requests_budget": 64,
            "wall_time_budget_s": 900,
            "expected_model_calls": "<=6 (prepare 1 次 + 编辑 slide_plan.json 1-3 次 + finish 1 次 + 状态/核对 1 次)",
            "script_only_stages": [s for s, _ in STAGES if s != "S4"],
            "model_stage": "S4 与 S5 之间：Agent 编辑 /app/work/slide_plan.json（唯一需要创作的步骤）",
        },
        "resume_instructions": {
            "通用": "任何阶段失败或中断后，重跑同一条 finish 命令即可；输入未变的阶段会打印 'skip Sn (checkpoint valid)' 并跳过。",
            "强制重跑某阶段": "删除 /app/work/checkpoints/S<n>.json 后重跑 finish。",
            "输入变化": "输入文件 sha256 变化会自动使下游检查点失效并重跑。",
        },
    }
    write_json(ctx.manifest_path(), manifest)
    return manifest
