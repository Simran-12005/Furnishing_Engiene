"""Rules Engine + Formulas Engine (components 6 & 7).

Two small, safe evaluators:

  * eval_rule(rule, context) -> bool   — drives visibility / requirement of
    choices and measurements (Visibility + Requirement + Type-switch rules).
  * eval_expr(expr, context) -> number — the formula DSL (arithmetic, variables,
    functions ceil/floor/round/max/min/abs and if(cond, a, b)).

resolve(category, answers) ties them together: given the answers gathered so far
it returns which choices + measurements are currently visible/required and the
computed formula outputs. This is what the Session/Flow engine calls after every
user input.
"""
import ast
import math
import re

# --------------------------------------------------------------------------- DSL
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Name, ast.Load, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)

_FUNCS = {
    "ceil": lambda x: math.ceil(x),
    "floor": lambda x: math.floor(x),
    "round": lambda x, n=2: round(x, int(n)),
    "max": max,
    "min": min,
    "abs": abs,
    "_if": lambda cond, a, b: a if cond else b,
}


def _validate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"disallowed expression element: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
                raise ValueError("disallowed function call")


def eval_expr(expr: str, context: dict):
    """Evaluate a formula expression against a variable context. Raises on any
    missing variable or disallowed syntax (caller treats that as 'not yet computable')."""
    expr = re.sub(r"\bif\s*\(", "_if(", expr)        # if(...) -> _if(...)
    tree = ast.parse(expr, mode="eval")
    _validate(tree)
    namespace = {"__builtins__": {}}
    namespace.update(_FUNCS)
    namespace.update(context)
    return eval(compile(tree, "<formula>", "eval"), namespace, {})


# --------------------------------------------------------------------------- rules
def eval_rule(rule, context: dict) -> bool:
    """Evaluate a visibility/requirement rule. None/empty => always true.

    Supported shapes:
      {"all": [rule, ...]}  {"any": [rule, ...]}  {"not": rule}
      {"field": "x", "eq": v} / "neq" / "in" [..] / "gt" / "lt"
    """
    if not rule:
        return True
    if "all" in rule:
        return all(eval_rule(r, context) for r in rule["all"])
    if "any" in rule:
        return any(eval_rule(r, context) for r in rule["any"])
    if "not" in rule:
        return not eval_rule(rule["not"], context)
    value = context.get(rule.get("field"))
    if "eq" in rule:
        return value == rule["eq"]
    if "neq" in rule:
        return value != rule["neq"]
    if "in" in rule:
        return value in rule["in"]
    if "contains" in rule:                       # multi-select: option chosen?
        return rule["contains"] in (value or [])
    if "gt" in rule:
        return value is not None and value > rule["gt"]
    if "lt" in rule:
        return value is not None and value < rule["lt"]
    return True


def _to_number(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def _slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def resolve(category: dict, answers: dict) -> dict:
    """The heart of the interview: given the current answers, return the visible
    choices, the visible/required measurements, and the computed formula outputs."""
    choice_answers = (answers or {}).get("choices", {}) or {}
    meas_answers = (answers or {}).get("measurements", {}) or {}

    # context = choices + entered measurements (coerced to numbers).
    # Multi-select choices are exposed both as a list AND as per-option booleans
    # (<choice>_<slug> = 1/0) so formulas/rules can reference a single add-on,
    # e.g. addons_motorisation.
    context: dict = {}
    for c in category.get("choices", []):
        name = c["name"]
        if c.get("type") == "multi":
            selected = choice_answers.get(name) or []
            if isinstance(selected, str):
                selected = [selected]
            context[name] = selected
            for opt in c.get("options", []):
                context[f"{name}_{_slug(opt)}"] = 1 if opt in selected else 0
        else:
            v = choice_answers.get(name)
            if v not in (None, ""):
                context[name] = v
    for k, v in meas_answers.items():
        num = _to_number(v)
        if num is not None:
            context[k] = num

    visible_choices = [
        c for c in category.get("choices", []) if eval_rule(c.get("visible_if"), context)
    ]

    visible_measurements = []
    for m in category.get("measurements", []):
        if not eval_rule(m.get("visible_if"), context):
            continue
        required = bool(m.get("required")) or eval_rule(m.get("required_if"), context)
        vm = dict(m)
        vm["required"] = required
        visible_measurements.append(vm)

    # Formulas: repeat passes so a formula can depend on an earlier formula's output.
    formulas = category.get("formulas", [])
    computed: dict = {}
    for _ in range(len(formulas) + 1):
        progressed = False
        for f in formulas:
            name = f["name"]
            if name in computed:
                continue
            scope = {**context, **computed}
            if not eval_rule(f.get("visible_if"), scope):
                continue
            if any(dep not in scope for dep in f.get("depends_on", [])):
                continue
            try:
                value = eval_expr(f["expression"], scope)
            except Exception:
                continue
            rounding = f.get("rounding")
            if rounding == "ceil":
                value = math.ceil(value)
            elif rounding == "floor":
                value = math.floor(value)
            elif rounding == "round":
                value = round(value, 2)
            if f.get("unit") == "₹":           # money is always whole rupees
                value = int(round(value))
            computed[name] = value
            progressed = True
        if not progressed:
            break

    outputs = [
        {
            "name": f["name"],
            "label": f.get("label", f["name"]),
            "unit": f.get("unit", ""),
            "value": computed[f["name"]],
        }
        for f in formulas
        if f.get("output", True) and f["name"] in computed
    ]

    return {
        "category": {"id": category["id"], "name": category["name"]},
        "choices": visible_choices,
        "measurements": visible_measurements,
        "computed": outputs,
    }
