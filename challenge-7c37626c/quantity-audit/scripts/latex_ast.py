#!/usr/bin/env python3
"""A small LaTeX math subset -> AST parser for numerical audit.

Supported: identifiers, Greek commands, numbers, + - * / (explicit and
implicit multiplication), \\frac, \\sqrt, \\exp \\log \\ln \\sin \\cos,
subscripts (symbol names), superscripts (powers), \\left( \\right), {groups},
and function application f(x). Top-level '=' splits LHS/RHS.

AST: ('num', float) ('sym', name) ('add',a,b) ('mul',a,b) ('div',a,b)
     ('pow',a,b) ('func',name,arg) ('apply',f,arg)
Stdlib only.
"""
import re

GREEK = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "zeta": "zeta", "eta": "eta", "theta": "theta",
    "iota": "iota", "kappa": "kappa", "lambda": "lambda", "mu": "mu",
    "nu": "nu", "xi": "xi", "pi": "pi", "rho": "rho", "sigma": "sigma",
    "tau": "tau", "upsilon": "upsilon", "phi": "phi", "chi": "chi",
    "psi": "psi", "omega": "omega",
    "Gamma": "Gamma", "Delta": "Delta", "Theta": "Theta", "Lambda": "Lambda",
    "Xi": "Xi", "Pi": "Pi", "Sigma": "Sigma", "Phi": "Phi", "Psi": "Psi",
    "Omega": "Omega",
}
FUNCTIONS = {"exp", "log", "ln", "sin", "cos", "tan", "sqrt", "abs"}
WRAP_CMDS = {"mathrm", "text", "mathbf", "boldsymbol", "operatorname", "rm"}


class ParseError_(ValueError):
    pass


def tokenize(s):
    i, n = 0, len(s)
    out = []
    while i < n:
        ch = s[i]
        if ch.isspace() or ch in "~;!,":
            i += 1
            continue
        if ch == "\\":
            m = re.match(r"\\([a-zA-Z]+|.)", s[i:])
            out.append(("cmd", m.group(1)))
            i += 1 + len(m.group(1))
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and s[i + 1].isdigit()):
            m = re.match(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", s[i:])
            out.append(("num", float(m.group(0))))
            i += len(m.group(0))
            continue
        if ch.isalpha():
            out.append(("ident", ch))
            i += 1
            continue
        out.append(("op", ch))
        i += 1
    out.append(("end", None))
    return out


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.pos = 0

    def peek(self):
        return self.toks[self.pos]

    def next(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def expect_op(self, ch):
        kind, val = self.next()
        if kind != "op" or val != ch:
            raise ParseError_("expected %r, got %r" % (ch, val))

    # expr := term (('+'|'-') term)*
    def expr(self):
        node = self.term()
        while self.peek() == ("op", "+") or self.peek() == ("op", "-"):
            op = self.next()[1]
            rhs = self.term()
            node = ("add", node, ("mul", ("num", -1.0), rhs) if op == "-" else rhs)
        return node

    # term := factor (explicit or implicit factor)*
    def term(self):
        node = self.factor()
        while True:
            kind, val = self.peek()
            if kind == "op" and val == "*":
                self.next()
                node = ("mul", node, self.factor())
            elif kind == "op" and val == "/":
                self.next()
                node = ("div", node, self.factor())
            elif self._starts_factor(self.peek()):
                node = ("mul", node, self.factor())
            else:
                return node

    @staticmethod
    def _starts_factor(tok):
        kind, val = tok
        if kind in ("num", "ident"):
            return True
        if kind == "cmd" and val not in ("left", "right"):
            return True
        if kind == "op" and val in ("(", "{", "{"):
            return True
        return False

    # factor := base ('_' script)? ('^' power)?  | unary minus
    def factor(self):
        if self.peek() == ("op", "-"):
            self.next()
            return ("mul", ("num", -1.0), self.factor())
        node = self.base()
        sub = None
        while True:
            kind, val = self.peek()
            if kind == "op" and val == "_":
                self.next()
                sub = self.atom_text()
                continue
            if kind == "op" and val == "^":
                self.next()
                power = self.factor()
                node = ("pow", node, power)
                continue
            break
        if sub is not None:
            node = self._attach_sub(node, sub)
        return node

    def _attach_sub(self, node, sub):
        if node[0] == "sym":
            return ("sym", "%s_%s" % (node[1], sub))
        if node[0] == "pow" and node[1][0] == "sym":
            return ("pow", ("sym", "%s_%s" % (node[1][1], sub)), node[2])
        if node[0] == "apply" and node[1][0] == "sym":
            return ("apply", ("sym", "%s_%s" % (node[1][1], sub)), node[2])
        raise ParseError_("subscript on non-symbol: %r" % (node,))

    def atom_text(self):
        """Read a subscript argument: {group} or single atom -> text."""
        kind, val = self.peek()
        if kind == "op" and val == "{":
            self.next()
            txt = self._collect_text()
            self.expect_op("}")
            return txt
        if kind == "cmd":
            self.next()
            return GREEK.get(val, val)
        if kind == "ident":
            self.next()
            return val
        if kind == "num":
            self.next()
            v = ("%.6g" % val)
            return v
        raise ParseError_("bad subscript atom %r" % (val,))

    def _collect_text(self):
        parts = []
        while self.peek() != ("op", "}"):
            kind, val = self.next()
            if kind == "cmd":
                if val in WRAP_CMDS:
                    self.expect_op("{")
                    parts.append(self._collect_text())
                    self.expect_op("}")
                else:
                    parts.append(GREEK.get(val, val))
            elif kind == "op" and val == "_":
                parts.append("_")
            elif kind == "op" and val == "^":
                parts.append("^")
            else:
                parts.append(str(val) if kind != "num" else ("%.6g" % val))
        return "".join(parts)

    # base := '(' expr ')' | \left( expr \right) | '{' expr '}' | cmd | num | ident
    def base(self):
        kind, val = self.next()
        if kind == "num":
            return ("num", val)
        if kind == "ident":
            node = ("sym", val)
            return self._maybe_apply(node)
        if kind == "op" and val == "(":
            node = self.expr()
            self.expect_op(")")
            return node
        if kind == "op" and val == "{":
            node = self.expr()
            self.expect_op("}")
            return node
        if kind == "cmd":
            if val in ("frac", "dfrac", "tfrac"):
                self.expect_op("{")
                num = self.expr()
                self.expect_op("}")
                self.expect_op("{")
                den = self.expr()
                self.expect_op("}")
                return ("div", num, den)
            if val == "left":
                kind2, val2 = self.next()
                node = self.expr()
                kind3, _ = self.next()  # \right
                if kind3 != "cmd":
                    raise ParseError_("expected \\right")
                self.next()  # closing fence char
                return node
            if val in ("cdot", "times"):
                raise ParseError_("operator %s cannot start a factor" % val)
            if val in GREEK:
                node = ("sym", GREEK[val])
                return self._maybe_apply(node)
            if val in FUNCTIONS:
                arg = self._func_arg()
                if val == "sqrt":
                    return ("pow", arg, ("num", 0.5))
                return ("func", val, arg)
            if val in WRAP_CMDS:
                self.expect_op("{")
                txt = self._collect_text()
                self.expect_op("}")
                return ("sym", txt)
            raise ParseError_("unsupported command \\%s" % val)
        raise ParseError_("unexpected token %r %r" % (kind, val))

    def _func_arg(self):
        kind, val = self.peek()
        if kind == "cmd" and val == "left":
            self.next()
            self.next()  # fence char
            node = self.expr()
            self.next()  # \right
            self.next()  # fence char
            return node
        if kind == "op" and val in "({":
            close = ")" if val == "(" else "}"
            self.next()
            node = self.expr()
            self.expect_op(close)
            return node
        return self.factor()

    def _maybe_apply(self, node):
        """f ( x ) -> apply; only when '(' directly follows the identifier."""
        if self.peek() == ("op", "("):
            save = self.pos
            self.next()
            try:
                arg = self.expr()
                self.expect_op(")")
                return ("apply", node, arg)
            except ParseError_:
                self.pos = save
        return node


def parse_formula(latex):
    """Parse 'LHS = RHS' -> (lhs_ast, rhs_ast); or single expression."""
    toks = tokenize(latex)
    depth = 0
    eq_at = None
    for i, (kind, val) in enumerate(toks):
        if kind == "op":
            if val in "({":
                depth += 1
            elif val in ")}":
                depth -= 1
            elif val == "=" and depth == 0 and eq_at is None:
                eq_at = i
    if eq_at is None:
        p = Parser(toks)
        node = p.expr()
        if p.peek() != ("end", None):
            raise ParseError_("trailing tokens: %r" % (p.peek(),))
        return None, node
    left = Parser(toks[:eq_at] + [("end", None)])
    right = Parser(toks[eq_at + 1:])
    lhs = left.expr()
    if left.peek() != ("end", None):
        raise ParseError_("trailing tokens in LHS")
    rhs = right.expr()
    if right.peek() != ("end", None):
        raise ParseError_("trailing tokens in RHS")
    return lhs, rhs


def ast_symbols(node):
    """All symbol names used in the AST (incl. applied function name)."""
    out = set()

    def walk(n):
        tag = n[0]
        if tag == "sym":
            out.add(n[1])
        elif tag in ("add", "mul", "div", "pow"):
            walk(n[1]); walk(n[2])
        elif tag == "func":
            walk(n[2])
        elif tag == "apply":
            if n[1][0] == "sym":
                out.add(n[1][1])
            walk(n[2])

    if node is not None:
        walk(node)
    return out
