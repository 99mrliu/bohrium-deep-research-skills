#!/usr/bin/env python3
"""op.py — opjournal-deck-surgeon step 2: the operation journal.

Every change to the deck is an append-only op with a mandatory "why".
Ops are validated AT COMMIT TIME against the paper text (numbers must hit
their anchor page) so bad content never enters the journal.

Usage:
  python3 op.py init                     create journal bound to v000 base
  python3 op.py add work/ops_round1.json append a list of ops from a JSON file
  python3 op.py list                     human-readable journal
  python3 op.py rollback N               drop the last N ops (they remain in
                                         journal.rejected.jsonl for audit)

Op schema (each op MUST carry "why"; bullets carry "anchor"):
  {"op":"add_slide","role":"result","layout":"title|body","why":...}
  {"op":"set_title","slide":N,"text":...,"why":...}
  {"op":"set_bullets","slide":N,"items":[{"text":...,"anchor":"p3|fig1|tab2"}],"why":...}
  {"op":"set_notes","slide":N,"text":...,"why":...}
  {"op":"insert_figure","slide":N,"fig":"fig1","why":...}
  {"op":"remove_slide","slide":N,"why":...}
  {"op":"replace_text","slide":N,"find":...,"by":...,"anchor":"p3","why":...}
"""
import json, os, re, sys

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
JOURNAL = None
NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?")
CJK_RE = re.compile(r"[一-鿿]")
ANCHOR_RE = re.compile(r"^(p\d+|fig\d+|tab\d+)$")
VALID_OPS = {"add_slide", "set_title", "set_bullets", "set_notes",
             "insert_figure", "remove_slide", "replace_text"}


def jpath(name="journal.jsonl"):
    return os.path.join(WORK, name)


def load_ctx():
    ctx = {"pages": {}, "caps": {}}
    try:
        for p in json.load(open(os.path.join(WORK, "paper_pages.json"), encoding="utf-8")):
            ctx["pages"][p["page"]] = p["text"]
    except Exception:
        pass
    try:
        for c in json.load(open(os.path.join(WORK, "captions.json"), encoding="utf-8")):
            ctx["caps"][c["id"]] = c
    except Exception:
        pass
    return ctx


def check_text_numbers(text, anchor, ctx):
    """Return list of problems for numbers not found at the anchor."""
    probs = []
    if not anchor:
        return ["缺 anchor"]
    if not ANCHOR_RE.match(anchor):
        return [f"锚点格式非法 '{anchor}'"]
    if anchor.startswith("p"):
        scope = ctx["pages"].get(int(anchor[1:]))
        if scope is None:
            return [f"锚定页 {anchor} 超出论文页数"]
    else:
        c = ctx["caps"].get(anchor)
        if not c:
            return [f"图表 {anchor} 不存在于论文"]
        scope = ctx["pages"].get(c["page"], "")
    flat = scope.replace(",", "")
    for tok in NUM_RE.findall(text):
        if tok == "0" or len(tok) >= 8:
            continue
        if tok in scope or tok.rstrip("%") in flat:
            continue
        all_txt = "\n".join(ctx["pages"].values()).replace(",", "")
        where = "论文他页" if (tok in all_txt or tok.rstrip("%") in all_txt) else "论文中不存在"
        probs.append(f"数字 {tok} 未命中 {anchor}（{where}）")
    return probs


def validate(op, ctx):
    probs = []
    kind = op.get("op")
    if kind not in VALID_OPS:
        return [f"未知操作 '{kind}'（允许: {sorted(VALID_OPS)}）"]
    if not str(op.get("why", "")).strip():
        probs.append("缺 why（每次修改必须记录理由）")
    if kind in ("set_title", "set_bullets", "set_notes", "insert_figure",
                "remove_slide", "replace_text"):
        if not isinstance(op.get("slide"), int) or op["slide"] < 1:
            probs.append("slide 必须为正整数")
    if kind == "add_slide":
        if op.get("layout", "body") not in ("title", "body"):
            probs.append("layout 只能 title/body")
        if op.get("role") not in ("title", "background", "method", "result",
                                  "comparison", "limitation", "conclusion", None):
            probs.append("role 非法")
    if kind == "set_bullets":
        items = op.get("items") or []
        if not items:
            probs.append("items 为空")
        if len(items) > 6:
            probs.append(f"{len(items)} 条 bullet > 6")
        for it in items:
            t = it.get("text", "")
            cjk = len(CJK_RE.findall(t))
            if cjk > 60 or (cjk == 0 and len(t) > 90):
                probs.append("bullet 过长")
            probs += check_text_numbers(t, it.get("anchor", ""), ctx)
    if kind == "insert_figure":
        c = ctx["caps"].get(op.get("fig", ""))
        if not c:
            probs.append(f"图 {op.get('fig')} 不存在")
        elif c.get("crop_status") != "ok":
            probs.append(f"图 {op.get('fig')} 无可用裁剪（{c.get('crop_status')}）")
    if kind == "replace_text":
        if not op.get("find"):
            probs.append("replace_text 缺 find")
        if op.get("anchor"):
            probs += check_text_numbers(op.get("by", ""), op["anchor"], ctx)
    if kind == "set_notes":
        nums = check_text_numbers(op.get("text", ""), op.get("anchor", ""), ctx) \
            if op.get("anchor") else []
        probs += nums
    return probs


def read_journal():
    ops = []
    if os.path.exists(jpath()):
        for line in open(jpath(), encoding="utf-8"):
            line = line.strip()
            if line:
                ops.append(json.loads(line))
    return ops


def cmd_init():
    if os.path.exists(jpath()):
        print("journal 已存在；如需重来请删除 work/journal.jsonl")
        return
    os.makedirs(WORK, exist_ok=True)
    head = {"op": "init", "base": "versions/v000_base.pptx",
            "why": "冻结底稿，之后一切改动入册"}
    with open(jpath(), "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
    print("journal initialized")


def cmd_add(path):
    ops = json.load(open(path, encoding="utf-8"))
    if isinstance(ops, dict):
        ops = [ops]
    ctx = load_ctx()
    existing = read_journal()
    seq = len(existing)
    accepted, rejected = [], []
    for op in ops:
        probs = validate(op, ctx)
        if probs:
            rejected.append({"op": op, "problems": probs})
        else:
            seq += 1
            op["_seq"] = seq
            accepted.append(op)
    with open(jpath(), "a", encoding="utf-8") as f:
        for op in accepted:
            f.write(json.dumps(op, ensure_ascii=False) + "\n")
    if rejected:
        with open(jpath("journal.rejected.jsonl"), "a", encoding="utf-8") as f:
            for r in rejected:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"accepted": len(accepted), "rejected": len(rejected)},
                     ensure_ascii=False))
    for r in rejected:
        print("REJECTED:", json.dumps(r, ensure_ascii=False)[:400])


def cmd_list():
    for op in read_journal():
        seq = op.get("_seq", 0)
        kind = op["op"]
        tgt = op.get("slide", "-")
        print(f"#{seq:03d} {kind:<14} slide={tgt} why={op.get('why','')}")


def cmd_rollback(n):
    ops = read_journal()
    if n >= len(ops):
        print("rollback 幅度超过 journal 长度（init 不可回退）")
        return
    keep, drop = ops[:-n], ops[-n:]
    with open(jpath(), "w", encoding="utf-8") as f:
        for op in keep:
            f.write(json.dumps(op, ensure_ascii=False) + "\n")
    with open(jpath("journal.rejected.jsonl"), "a", encoding="utf-8") as f:
        for op in drop:
            op["_rolled_back"] = True
            f.write(json.dumps(op, ensure_ascii=False) + "\n")
    print(f"rolled back {len(drop)} ops; 重新运行 apply.py 重建演示稿")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "init":
        cmd_init()
    elif cmd == "add":
        cmd_add(sys.argv[2])
    elif cmd == "list":
        cmd_list()
    elif cmd == "rollback":
        cmd_rollback(int(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)
