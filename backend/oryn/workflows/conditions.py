"""A tiny, safe expression language for workflow conditions (no ``eval``).

Grammar:
    expr    := cmp (("and" | "or") cmp)*          # left to right, "and" binds tighter
    cmp     := path (op literal)?
    op      := == | != | > | >= | < | <=
    literal := number | 'string' | "string" | true | false | null
    path    := name ("." name)*                    # e.g. blackboard.qualified, trigger.amount

Missing paths resolve to ``None`` (so ``blackboard.x == null`` is true and comparisons are false),
which means a typo makes a branch not fire rather than crashing a durable workflow.
"""

import re
from dataclasses import dataclass
from typing import Any

_TOKEN = re.compile(
    r"\s*(?:(?P<num>-?\d+(?:\.\d+)?)|(?P<str>'[^']*'|\"[^\"]*\")|(?P<op>==|!=|>=|<=|>|<)"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*))"
)
_KEYWORDS = {"and", "or", "true", "false", "null"}


class ConditionSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class Cmp:
    path: str
    op: str | None
    value: Any


@dataclass(frozen=True)
class Ast:
    # Disjunction of conjunctions: [[cmp, cmp], [cmp]] == (a and b) or c
    any_of: tuple[tuple[Cmp, ...], ...]


def _tokenize(expr: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    expr = expr.rstrip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise ConditionSyntaxError(f"unexpected input at position {pos}: {expr[pos : pos + 12]!r}")
        kind = m.lastgroup or ""
        out.append((kind, m.group(kind)))
        pos = m.end()
    return out


def _literal(kind: str, text: str) -> Any:
    if kind == "num":
        return float(text) if "." in text else int(text)
    if kind == "str":
        return text[1:-1]
    if kind == "word" and text in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[text]
    raise ConditionSyntaxError(f"expected a literal, got {text!r}")


def parse(expr: str) -> Ast:
    toks = _tokenize(expr)
    if not toks:
        raise ConditionSyntaxError("empty condition")
    groups: list[list[Cmp]] = [[]]
    i = 0
    while True:
        if i >= len(toks) or toks[i][0] != "word" or toks[i][1] in _KEYWORDS:
            raise ConditionSyntaxError("expected a field path like blackboard.qualified")
        path = toks[i][1]
        i += 1
        op = value = None
        if i < len(toks) and toks[i][0] == "op":
            op = toks[i][1]
            i += 1
            if i >= len(toks):
                raise ConditionSyntaxError(f"missing value after {op}")
            value = _literal(*toks[i])
            i += 1
        groups[-1].append(Cmp(path, op, value))
        if i == len(toks):
            break
        joiner = toks[i]
        if joiner == ("word", "and"):
            pass
        elif joiner == ("word", "or"):
            groups.append([])
        else:
            raise ConditionSyntaxError(f"expected 'and' or 'or', got {joiner[1]!r}")
        i += 1
        if i == len(toks):
            raise ConditionSyntaxError(f"dangling '{joiner[1]}'")
    return Ast(tuple(tuple(g) for g in groups))


def _resolve(scope: dict[str, Any], path: str) -> Any:
    cur: Any = scope
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _num(x: Any) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cmp(c: Cmp, scope: dict[str, Any]) -> bool:
    left = _resolve(scope, c.path)
    if c.op is None:
        return bool(left)
    right = c.value
    if c.op in ("==", "!="):
        ln, rn = _num(left), _num(right)
        equal = (ln == rn) if (ln is not None and rn is not None and not isinstance(right, bool)) else left == right
        return equal if c.op == "==" else not equal
    ln, rn = _num(left), _num(right)
    if ln is None or rn is None:
        return False
    return {">": ln > rn, ">=": ln >= rn, "<": ln < rn, "<=": ln <= rn}[c.op]


def evaluate(expr: str | Ast, scope: dict[str, Any]) -> bool:
    ast = parse(expr) if isinstance(expr, str) else expr
    return any(all(_cmp(c, scope) for c in group) for group in ast.any_of)
