#!/usr/bin/env python3
"""plan_check.py — 检索计划机器门控校验。

校验 retrieval_plan.json（结构：waves[]，每 wave 含 actions[]；
action = {action_id, sq_id 或 sq_ids, query, source_scope, stop_condition, wave}）。

检查项：
    P1  SQ 依赖 DAG 无环（拓扑排序 / DFS，成环时打印环路径）
    P2  每个 SQ 至少 1 个 action；每 action 的 query/source_scope/stop_condition
        三键非空；每 action 至少关联 1 个 SQ
    P3  跨 action 检索式归一化（小写、空白压缩、去停用词 and/or）后完全相同
        → 违例；提示改用"一次检索、多 SQ 标注"（sq_ids 列表）
    P4  波次与依赖一致：SQ-x 依赖 SQ-y ⇒ SQ-y 全部 action 的波次不得晚于
        SQ-x 最早 action 的波次；action.wave 字段须与所在波次编号一致
    P5  action 总数 ≤ --max-actions（默认 25）

退出码：
    0  全部通过
    1  门控违例（stdout 逐项打印 P 编号清单）
    2  用法 / IO / JSON 解析错误
"""
import argparse
import json
import os
import re
import sys

STOPWORDS = ("and", "or")


def normalize_query(query):
    """小写、去停用词 and/or（整词）、空白压缩。"""
    q = query.lower()
    q = re.sub(r"\b(?:and|or)\b", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def load_json(path, what):
    if not os.path.isfile(path):
        print("[ERROR] %s 不存在：%s" % (what, path), file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print("[ERROR] %s 解析失败：%s" % (what, exc), file=sys.stderr)
        sys.exit(2)


def action_sq_ids(action):
    """统一取出 action 关联的 SQ 列表（兼容 sq_id 单值与 sq_ids 列表）。"""
    ids = []
    if isinstance(action.get("sq_ids"), list):
        ids.extend(str(x) for x in action["sq_ids"] if x is not None)
    elif action.get("sq_id") is not None:
        ids.append(str(action["sq_id"]))
    # 去重保序
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def find_cycle(deps):
    """deps: {sq: [dep, ...]}；返回环路径列表（如 ['SQ-2','SQ-3','SQ-2']）或 None。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in deps}
    stack = []

    def dfs(node):
        color[node] = GRAY
        stack.append(node)
        for nxt in deps.get(node, []):
            if nxt not in color:
                color[nxt] = WHITE
                deps[nxt] = deps.get(nxt, [])
            if color[nxt] == GRAY:
                idx = stack.index(nxt)
                return stack[idx:] + [nxt]
            if color[nxt] == WHITE:
                res = dfs(nxt)
                if res:
                    return res
        stack.pop()
        color[node] = BLACK
        return None

    for node in sorted(deps):
        if color[node] == WHITE:
            res = dfs(node)
            if res:
                return res
    return None


def main():
    parser = argparse.ArgumentParser(description="检索计划机器门控校验（P1-P5）")
    parser.add_argument("--plan", default="/app/work/retrieval_plan.json",
                        help="retrieval_plan.json 路径")
    parser.add_argument("--decomp", default="/app/output/decomposition.json",
                        help="decomposition.json 路径（提供 SQ 全集与 depends_on；"
                             "缺失时 P1 与 P4 的依赖子项跳过并提示）")
    parser.add_argument("--max-actions", type=int, default=25,
                        help="action 总数上限（默认 25）")
    args = parser.parse_args()

    plan = load_json(args.plan, "retrieval_plan.json")
    if not isinstance(plan, dict) or not isinstance(plan.get("waves"), list):
        print("[ERROR] plan 结构非法：顶层须为含 waves 列表的对象", file=sys.stderr)
        return 2

    decomp = None
    if os.path.isfile(args.decomp):
        decomp = load_json(args.decomp, "decomposition.json")
    else:
        print("[SKIP] 未找到 decomposition.json（%s）：P1 与 P4 的依赖子项跳过"
              % args.decomp)

    # ---- 展开 actions ----------------------------------------------------
    actions = []          # (action_dict, wave_no)
    for idx, wave in enumerate(plan["waves"], start=1):
        if not isinstance(wave, dict) or not isinstance(wave.get("actions"), list):
            print("[ERROR] plan 结构非法：waves[%d] 须含 actions 列表" % (idx - 1),
                  file=sys.stderr)
            return 2
        wave_no = wave.get("wave", idx)
        for act in wave["actions"]:
            if not isinstance(act, dict):
                print("[ERROR] waves[%d] 内存在非对象 action" % (idx - 1),
                      file=sys.stderr)
                return 2
            actions.append((act, wave_no))

    violations = []  # (pcode, message)

    # ---- SQ 全集与依赖 ---------------------------------------------------
    sq_universe = []
    deps = {}
    if decomp and isinstance(decomp.get("sub_questions"), list):
        for sq in decomp["sub_questions"]:
            if isinstance(sq, dict) and sq.get("id"):
                sid = str(sq["id"])
                sq_universe.append(sid)
                d = sq.get("depends_on", [])
                deps[sid] = [str(x) for x in d] if isinstance(d, list) else []
    for act, _ in actions:
        for sid in action_sq_ids(act):
            if sid not in sq_universe:
                sq_universe.append(sid)
                deps.setdefault(sid, [])

    sq_actions = {sid: [] for sid in sq_universe}
    for act, wave_no in actions:
        for sid in action_sq_ids(act):
            sq_actions.setdefault(sid, []).append((act, wave_no))

    # ---- P1：依赖 DAG 无环 ----------------------------------------------
    if decomp is not None:
        cycle = find_cycle({k: list(v) for k, v in deps.items()})
        if cycle:
            violations.append(("P1", "SQ 依赖存在环：%s" % " -> ".join(cycle)))

    # ---- P2：覆盖与三键非空 ----------------------------------------------
    for sid in sq_universe:
        if not sq_actions.get(sid):
            violations.append(("P2", "SQ %s 没有任何检索 action" % sid))
    for act, _ in actions:
        aid = act.get("action_id", "<missing action_id>")
        if not action_sq_ids(act):
            violations.append(("P2", "action %s 未关联任何 SQ（缺 sq_id/sq_ids）" % aid))
        for key in ("query", "source_scope", "stop_condition"):
            val = act.get(key)
            if not isinstance(val, str) or not val.strip():
                violations.append(("P2", "action %s 缺少非空键 %s" % (aid, key)))

    # ---- P3：归一化后检索式重复 ------------------------------------------
    norm_map = {}
    for act, _ in actions:
        q = act.get("query")
        if not isinstance(q, str) or not q.strip():
            continue
        nq = normalize_query(q)
        norm_map.setdefault(nq, []).append(str(act.get("action_id")))
    for nq, ids in norm_map.items():
        if len(ids) > 1:
            violations.append((
                "P3",
                "检索式归一化后重复：actions %s 归一化结果均为 %r；"
                "同一检索应只执行一次并用 sq_ids 列表同时标注多个 SQ"
                % (", ".join(ids), nq)))

    # ---- P4：波次与依赖一致 ----------------------------------------------
    for act, wave_no in actions:
        aw = act.get("wave", wave_no)
        if aw != wave_no:
            violations.append((
                "P4", "action %s 的 wave 字段（%r）与所在波次编号（%r）不一致"
                % (act.get("action_id"), aw, wave_no)))
    if decomp is not None:
        for sx, dlist in deps.items():
            for sy in dlist:
                if not sq_actions.get(sx) or not sq_actions.get(sy):
                    continue
                max_wave_y = max(w for _, w in sq_actions[sy])
                min_wave_x = min(w for _, w in sq_actions[sx])
                if max_wave_y > min_wave_x:
                    violations.append((
                        "P4",
                        "波次与依赖冲突：%s 依赖 %s，但 %s 的 action 最晚排在波次 %s，"
                        "晚于 %s 的最早波次 %s" % (sx, sy, sy, max_wave_y, sx, min_wave_x)))

    # ---- P5：预算 ---------------------------------------------------------
    if len(actions) > args.max_actions:
        violations.append((
            "P5", "action 总数 %d 超过预算 --max-actions %d"
            % (len(actions), args.max_actions)))

    # ---- 汇总 -------------------------------------------------------------
    if violations:
        by_p = {}
        for pcode, msg in violations:
            by_p.setdefault(pcode, []).append(msg)
        print("GATE FAILED: %s" % " ".join(sorted(by_p)))
        for pcode in sorted(by_p):
            for msg in by_p[pcode]:
                print("[%s] %s" % (pcode, msg))
        return 1
    print("GATE PASSED: P1-P5 全部通过（actions=%d, SQs=%d, max_actions=%d）"
          % (len(actions), len(sq_universe), args.max_actions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
