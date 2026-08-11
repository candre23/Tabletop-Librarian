from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import ast
import math
import operator
import re
import yaml


class RuleEngineError(RuntimeError):
    pass


@dataclass(slots=True)
class RuleIssue:
    severity: str
    message: str
    rule_id: str | None = None

    def format(self) -> str:
        if self.rule_id:
            return f"{self.severity.upper()}: {self.rule_id}: {self.message}"
        return f"{self.severity.upper()}: {self.message}"


@dataclass(slots=True)
class ModifierDefinition:
    id: str
    default: float
    aggregate: str
    label: str


@dataclass(slots=True)
class LimitDefinition:
    id: str
    field: str
    maximum: str
    label: str
    message: str
    where: dict[str, Any] | None
    warn_at_remaining: int | None
    warning_message: str | None
    usage: str | None
    dependencies: set[str]


@dataclass(slots=True)
class CalculatedRule:
    id: str
    formula: str
    dependencies: set[str]


@dataclass(slots=True)
class ValidationRule:
    id: str
    expression: str
    message: str
    severity: str
    dependencies: set[str]


def _safe_count(value: Any) -> int:
    if isinstance(value, (list, tuple, dict, str)):
        return len(value)
    return 0


def _safe_rowsum(rows: Any, field_name: Any) -> float:
    if not isinstance(rows, list) or not isinstance(field_name, str):
        return 0
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get(field_name, 0)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value)
    return total



def _safe_rowsum_where(
    rows: Any,
    value_field: Any,
    match_field: Any,
    expected: Any,
) -> float:
    if (
        not isinstance(rows, list)
        or not isinstance(value_field, str)
        or not isinstance(match_field, str)
    ):
        return 0
    total = 0.0
    for row in rows:
        if not isinstance(row, dict) or row.get(match_field) != expected:
            continue
        value = row.get(value_field, 0)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value)
    return total

def _safe_rowcount(rows: Any, field_name: Any, expected: Any) -> int:
    if not isinstance(rows, list) or not isinstance(field_name, str):
        return 0
    return sum(
        1 for row in rows
        if isinstance(row, dict) and row.get(field_name) == expected
    )


def _safe_nonempty_count(rows: Any, field_name: Any) -> int:
    if not isinstance(rows, list) or not isinstance(field_name, str):
        return 0
    return sum(
        1 for row in rows
        if isinstance(row, dict) and bool(str(row.get(field_name, '')).strip())
    )


def _safe_resource_max(value: Any) -> float:
    if not isinstance(value, dict):
        return 0
    maximum = value.get('max', 0)
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
        return float(maximum)
    return 0


SAFE_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "count": _safe_count,
    "rowsum": _safe_rowsum,
    "rowsum_where": _safe_rowsum_where,
    "rowcount": _safe_rowcount,
    "nonempty_count": _safe_nonempty_count,
    "resource_max": _safe_resource_max,
}

BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


def _parse(expression: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise RuleEngineError("Expression must be a non-empty string.")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise RuleEngineError(f"Invalid expression syntax: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise RuleEngineError(
                f"Unsupported expression feature: {node.__class__.__name__}"
            )

        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise RuleEngineError("Private/special names are not allowed.")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise RuleEngineError("Only direct safe-function calls are allowed.")
            if node.func.id not in SAFE_FUNCTIONS:
                raise RuleEngineError(f"Function {node.func.id!r} is not allowed.")
            if node.keywords:
                raise RuleEngineError("Keyword arguments are not allowed.")

    return tree


def _dependencies(tree: ast.Expression) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id not in SAFE_FUNCTIONS
    }


def _evaluate(node: ast.AST, values: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, values)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in values:
            return values[node.id]
        if node.id in SAFE_FUNCTIONS:
            return SAFE_FUNCTIONS[node.id]
        raise RuleEngineError(f"Unknown field/reference {node.id!r}.")

    if isinstance(node, ast.BinOp):
        fn = BINOPS.get(type(node.op))
        if fn is None:
            raise RuleEngineError("Unsupported binary operator.")
        return fn(_evaluate(node.left, values), _evaluate(node.right, values))

    if isinstance(node, ast.UnaryOp):
        fn = UNARYOPS.get(type(node.op))
        if fn is None:
            raise RuleEngineError("Unsupported unary operator.")
        return fn(_evaluate(node.operand, values))

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for item in node.values:
                result = _evaluate(item, values)
                if not result:
                    return result
            return result

        if isinstance(node.op, ast.Or):
            for item in node.values:
                result = _evaluate(item, values)
                if result:
                    return result
            return result

    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, values)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = _evaluate(comparator, values)
            fn = COMPARISONS.get(type(op_node))
            if fn is None:
                raise RuleEngineError("Unsupported comparison operator.")
            if not fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.IfExp):
        branch = node.body if _evaluate(node.test, values) else node.orelse
        return _evaluate(branch, values)

    if isinstance(node, ast.Call):
        fn = _evaluate(node.func, values)
        return fn(*[_evaluate(arg, values) for arg in node.args])

    raise RuleEngineError(
        f"Unsupported expression node: {node.__class__.__name__}"
    )


def _format_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _format_expression(node: ast.AST, labels: dict[str, str]) -> str:
    target = node.body if isinstance(node, ast.Expression) else node
    if hasattr(ast, "unparse"):
        text = ast.unparse(target)
        for identifier in sorted(labels, key=len, reverse=True):
            text = re.sub(
                rf"\b{re.escape(identifier)}\b",
                labels[identifier],
                text,
            )
        text = text.replace("**", "^")
        text = text.replace("//", "⌊÷⌋")
        text = text.replace("*", "×")
        text = text.replace("/", "÷")
        return text

    if isinstance(target, ast.Constant):
        return _format_value(target.value)
    if isinstance(target, ast.Name):
        return labels.get(
            target.id,
            target.id.replace("_", " ").title(),
        )
    return "expression"


def _flatten_additive_terms(node: ast.AST, sign: int = 1) -> list[tuple[int, ast.AST]]:
    if isinstance(node, ast.Expression):
        return _flatten_additive_terms(node.body, sign)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (
            _flatten_additive_terms(node.left, sign)
            + _flatten_additive_terms(node.right, sign)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
        return (
            _flatten_additive_terms(node.left, sign)
            + _flatten_additive_terms(node.right, -sign)
        )
    return [(sign, node)]


def _ordered_dependencies(tree: ast.Expression) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in SAFE_FUNCTIONS:
            if node.id not in seen:
                seen.add(node.id)
                output.append(node.id)
    return output


def _calculation_order(calculated: dict[str, CalculatedRule]) -> list[str]:
    ids = set(calculated)
    graph = {
        rule_id: {dep for dep in rule.dependencies if dep in ids}
        for rule_id, rule in calculated.items()
    }

    output: list[str] = []
    active: list[str] = []
    done: set[str] = set()

    def visit(rule_id: str) -> None:
        if rule_id in done:
            return
        if rule_id in active:
            start = active.index(rule_id)
            cycle = active[start:] + [rule_id]
            raise RuleEngineError(
                "Circular calculated-field dependency: " + " -> ".join(cycle)
            )

        active.append(rule_id)
        for dep in sorted(graph[rule_id]):
            visit(dep)
        active.pop()
        done.add(rule_id)
        output.append(rule_id)

    for rule_id in sorted(graph):
        visit(rule_id)

    return output


class RuleEngine:
    def __init__(
        self,
        calculated: dict[str, CalculatedRule],
        validation: list[ValidationRule],
        modifiers: dict[str, ModifierDefinition] | None = None,
        limits: dict[str, LimitDefinition] | None = None,
    ) -> None:
        self.calculated = calculated
        self.validation = validation
        self.modifiers = modifiers or {}
        self.limits = limits or {}
        self.order = _calculation_order(calculated)
        self._calc_trees = {
            key: _parse(rule.formula) for key, rule in calculated.items()
        }
        self._validation_trees = {
            rule.id: _parse(rule.expression) for rule in validation
        }

    def _modifier_context(
        self,
        modifiers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        values = {
            modifier_id: definition.default
            for modifier_id, definition in self.modifiers.items()
        }

        if modifiers:
            for modifier_id, value in modifiers.items():
                if modifier_id in self.modifiers:
                    values[modifier_id] = value

        return values

    def _calculate_context(
        self,
        data: dict[str, Any],
        modifiers: dict[str, Any] | None = None,
        value_transform: Callable[[str, Any], Any] | None = None,
    ) -> dict[str, Any]:
        values = dict(data)

        if value_transform is not None:
            for field_id, value in list(values.items()):
                values[field_id] = value_transform(field_id, value)

        values.update(self._modifier_context(modifiers))

        for rule_id in self.order:
            value = _evaluate(self._calc_trees[rule_id], values)
            if value_transform is not None:
                value = value_transform(rule_id, value)
            values[rule_id] = value

        return values

    def _character_values(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in context.items()
            if key not in self.modifiers
        }

    def expression_dependencies(self, expression: str) -> list[str]:
        return _ordered_dependencies(_parse(expression))

    def format_expression(
        self,
        expression: str,
        labels: dict[str, str] | None = None,
    ) -> str:
        return _format_expression(_parse(expression), labels or {})

    def evaluate_expression(
        self,
        expression: str,
        data: dict[str, Any],
        *,
        modifiers: dict[str, Any] | None = None,
    ) -> Any:
        context = self._calculate_context(data, modifiers)
        return _evaluate(_parse(expression), context)

    def condition_dependencies(self, expression: str) -> set[str]:
        return _dependencies(_parse(expression))

    def evaluate_condition(
        self,
        expression: str,
        data: dict[str, Any],
    ) -> bool:
        return bool(_evaluate(_parse(expression), dict(data)))

    def calculate(
        self,
        data: dict[str, Any],
        *,
        modifiers: dict[str, Any] | None = None,
        value_transform: Callable[[str, Any], Any] | None = None,
    ) -> dict[str, Any]:
        return self._character_values(
            self._calculate_context(
                data,
                modifiers,
                value_transform=value_transform,
            )
        )

    def validate(
        self,
        data: dict[str, Any],
        *,
        modifiers: dict[str, Any] | None = None,
    ) -> list[RuleIssue]:
        values = self._calculate_context(data, modifiers)
        issues: list[RuleIssue] = []

        for rule in self.validation:
            if not bool(_evaluate(self._validation_trees[rule.id], values)):
                issues.append(
                    RuleIssue(rule.severity, rule.message, rule.id)
                )

        return issues

    def apply(
        self,
        data: dict[str, Any],
        *,
        modifiers: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[RuleIssue]]:
        context = self._calculate_context(data, modifiers)
        issues: list[RuleIssue] = []

        for rule in self.validation:
            if not bool(_evaluate(self._validation_trees[rule.id], context)):
                issues.append(
                    RuleIssue(rule.severity, rule.message, rule.id)
                )

        return self._character_values(context), issues


    def explain(
        self,
        data: dict[str, Any],
        *,
        modifiers: dict[str, Any] | None = None,
        modifier_sources: dict[str, list[dict[str, Any]]] | None = None,
        labels: dict[str, str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        labels = dict(labels or {})
        for modifier_id, definition in self.modifiers.items():
            labels.setdefault(modifier_id, definition.label)

        context = self._calculate_context(data, modifiers)
        sources = modifier_sources or {}
        explanations: dict[str, dict[str, Any]] = {}

        for rule_id in self.order:
            tree = self._calc_trees[rule_id]
            rule = self.calculated[rule_id]
            terms: list[dict[str, Any]] = []

            for sign, term_node in _flatten_additive_terms(tree):
                raw_value = _evaluate(term_node, context)
                signed_value = raw_value * sign if isinstance(raw_value, (int, float)) else raw_value
                term: dict[str, Any] = {
                    "label": _format_expression(term_node, labels),
                    "value": signed_value,
                }

                if isinstance(term_node, ast.Name) and term_node.id in self.modifiers:
                    modifier_id = term_node.id
                    term["modifier_id"] = modifier_id
                    term["aggregate"] = self.modifiers[modifier_id].aggregate
                    term["sources"] = list(sources.get(modifier_id, []))

                terms.append(term)

            inputs: list[dict[str, Any]] = []
            for dependency in _ordered_dependencies(tree):
                item: dict[str, Any] = {
                    "id": dependency,
                    "label": labels.get(
                        dependency,
                        dependency.replace("_", " ").title(),
                    ),
                    "value": context.get(dependency),
                }

                if dependency in self.modifiers:
                    item["kind"] = "modifier"
                    item["aggregate"] = self.modifiers[dependency].aggregate
                    item["sources"] = list(sources.get(dependency, []))
                elif dependency in self.calculated:
                    item["kind"] = "calculated"
                else:
                    item["kind"] = "field"

                inputs.append(item)

            explanations[rule_id] = {
                "field_id": rule_id,
                "value": context.get(rule_id),
                "formula": rule.formula,
                "formula_display": _format_expression(tree, labels),
                "terms": terms,
                "inputs": inputs,
            }

        return explanations


def load_rule_engine(
    path: Path | str | None,
    *,
    known_fields: set[str] | None = None,
) -> tuple[RuleEngine | None, list[RuleIssue]]:
    if path is None:
        return RuleEngine({}, [], {}, {}), []

    path = Path(path)
    issues: list[RuleIssue] = []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [RuleIssue("error", "Rules file does not exist.")]
    except yaml.YAMLError as exc:
        return None, [RuleIssue("error", f"Invalid YAML: {exc}")]
    except OSError as exc:
        return None, [RuleIssue("error", f"Could not read rules file: {exc}")]

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        return None, [RuleIssue("error", "Rules root must be a mapping/object.")]

    modifier_raw = raw.get("modifiers", {})
    limit_raw = raw.get("limits", {})
    calc_raw = raw.get("calculated", {})
    val_raw = raw.get("validation", {})

    if not isinstance(modifier_raw, dict):
        return None, [RuleIssue("error", "modifiers must be a mapping/object.")]
    if not isinstance(limit_raw, dict):
        return None, [RuleIssue("error", "limits must be a mapping/object.")]
    if not isinstance(calc_raw, dict):
        return None, [RuleIssue("error", "calculated must be a mapping/object.")]
    if not isinstance(val_raw, dict):
        return None, [RuleIssue("error", "validation must be a mapping/object.")]

    modifiers: dict[str, ModifierDefinition] = {}

    for modifier_id, definition in modifier_raw.items():
        if not isinstance(modifier_id, str) or not modifier_id:
            issues.append(
                RuleIssue("error", "Modifier id must be a non-empty string.")
            )
            continue

        if isinstance(definition, (int, float)) and not isinstance(definition, bool):
            default = float(definition)
            aggregate = "sum"
        elif isinstance(definition, dict):
            default = definition.get("default", 0)
            aggregate = str(definition.get("aggregate", "sum")).lower()
        else:
            issues.append(
                RuleIssue(
                    "error",
                    "Modifier must be numeric or a mapping/object.",
                    modifier_id,
                )
            )
            continue

        if not isinstance(default, (int, float)) or isinstance(default, bool):
            issues.append(
                RuleIssue("error", "Modifier default must be numeric.", modifier_id)
            )
            continue

        if aggregate not in {"sum", "max", "min"}:
            issues.append(
                RuleIssue(
                    "error",
                    "Modifier aggregate must be sum, max, or min.",
                    modifier_id,
                )
            )
            continue

        label = (
            definition.get("label")
            if isinstance(definition, dict)
            else None
        )
        if label is None:
            label = modifier_id.replace("_", " ").title()
        if not isinstance(label, str) or not label.strip():
            issues.append(
                RuleIssue("error", "Modifier label must be non-empty.", modifier_id)
            )
            continue

        modifiers[modifier_id] = ModifierDefinition(
            modifier_id,
            float(default),
            aggregate,
            label.strip(),
        )

    calculated: dict[str, CalculatedRule] = {}

    for rule_id, definition in calc_raw.items():
        formula = (
            definition
            if isinstance(definition, str)
            else definition.get("formula")
            if isinstance(definition, dict)
            else None
        )

        if not isinstance(rule_id, str) or not rule_id:
            issues.append(RuleIssue("error", "Calculated rule id must be a non-empty string."))
            continue
        if not isinstance(formula, str) or not formula.strip():
            issues.append(RuleIssue("error", "Calculated rule requires a formula.", rule_id))
            continue

        try:
            tree = _parse(formula)
        except RuleEngineError as exc:
            issues.append(RuleIssue("error", str(exc), rule_id))
            continue

        calculated[rule_id] = CalculatedRule(
            rule_id,
            formula.strip(),
            _dependencies(tree),
        )

    field_names = set(known_fields or set())

    for modifier_id in modifiers:
        if modifier_id in field_names or modifier_id in calculated:
            issues.append(
                RuleIssue(
                    "error",
                    "Modifier id collides with a character/calculated field.",
                    modifier_id,
                )
            )

    known = field_names | set(calculated) | set(modifiers)

    limits: dict[str, LimitDefinition] = {}

    for limit_id, definition in limit_raw.items():
        if not isinstance(limit_id, str) or not limit_id:
            issues.append(RuleIssue("error", "Limit id must be a non-empty string."))
            continue
        if not isinstance(definition, dict):
            issues.append(
                RuleIssue("error", "Limit definition must be a mapping/object.", limit_id)
            )
            continue

        field_id = definition.get("field")
        maximum = definition.get("maximum")
        label = definition.get("label")
        message = definition.get(
            "message",
            "{label}: {count} selected, but the current maximum is {maximum}.",
        )
        where = definition.get("where")
        warn_at_remaining = definition.get("warn_at_remaining")
        warning_message = definition.get("warning_message")
        usage = definition.get("usage")

        if not isinstance(field_id, str) or not field_id:
            issues.append(RuleIssue("error", "Limit requires a field.", limit_id))
            continue
        if field_id not in field_names:
            issues.append(
                RuleIssue("error", f"Unknown limit field {field_id!r}.", limit_id)
            )
            continue

        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            maximum = str(maximum)
        if not isinstance(maximum, str) or not maximum.strip():
            issues.append(
                RuleIssue("error", "Limit requires a maximum expression.", limit_id)
            )
            continue

        if label is None:
            label = field_id.replace("_", " ").title()
        if not isinstance(label, str) or not label.strip():
            issues.append(RuleIssue("error", "Limit label must be non-empty.", limit_id))
            continue
        if not isinstance(message, str) or not message.strip():
            issues.append(RuleIssue("error", "Limit message must be non-empty.", limit_id))
            continue
        if where is not None and not isinstance(where, dict):
            issues.append(RuleIssue("error", "Limit where must be a mapping/object.", limit_id))
            continue
        if warn_at_remaining is not None:
            if isinstance(warn_at_remaining, bool) or not isinstance(warn_at_remaining, int) or warn_at_remaining < 0:
                issues.append(
                    RuleIssue(
                        "error",
                        "warn_at_remaining must be a non-negative integer.",
                        limit_id,
                    )
                )
                continue
        if warning_message is not None and (
            not isinstance(warning_message, str) or not warning_message.strip()
        ):
            issues.append(
                RuleIssue("error", "warning_message must be non-empty.", limit_id)
            )
            continue
        if usage is not None and (not isinstance(usage, str) or not usage.strip()):
            issues.append(RuleIssue("error", "usage must be a non-empty expression.", limit_id))
            continue
        if usage is not None and where is not None:
            issues.append(RuleIssue("error", "usage limits cannot also define where.", limit_id))
            continue

        try:
            tree = _parse(maximum)
        except RuleEngineError as exc:
            issues.append(RuleIssue("error", str(exc), limit_id))
            continue

        deps = _dependencies(tree)
        if usage is not None:
            try:
                usage_tree = _parse(usage)
            except RuleEngineError as exc:
                issues.append(RuleIssue("error", str(exc), limit_id))
                continue
            deps |= _dependencies(usage_tree)
        unknown = sorted(deps - known)
        if unknown:
            issues.append(
                RuleIssue(
                    "error",
                    "Unknown field reference(s): " + ", ".join(unknown),
                    limit_id,
                )
            )
            continue

        limits[limit_id] = LimitDefinition(
            limit_id,
            field_id,
            maximum.strip(),
            label.strip(),
            message.strip(),
            where,
            warn_at_remaining,
            warning_message.strip() if isinstance(warning_message, str) else None,
            usage.strip() if isinstance(usage, str) else None,
            deps,
        )

    for rule_id, rule in calculated.items():
        unknown = sorted(rule.dependencies - known)
        if unknown:
            issues.append(
                RuleIssue(
                    "error",
                    "Unknown field reference(s): " + ", ".join(unknown),
                    rule_id,
                )
            )

    validation: list[ValidationRule] = []

    for rule_id, definition in val_raw.items():
        if not isinstance(rule_id, str) or not rule_id:
            issues.append(RuleIssue("error", "Validation rule id must be a non-empty string."))
            continue

        if isinstance(definition, str):
            expression = definition
            message = f"Validation rule {rule_id} failed."
            severity = "error"
        elif isinstance(definition, dict):
            expression = definition.get("rule")
            message = definition.get(
                "message",
                f"Validation rule {rule_id} failed.",
            )
            severity = str(definition.get("severity", "error")).lower()
        else:
            issues.append(
                RuleIssue("error", "Validation rule must be a string or mapping.", rule_id)
            )
            continue

        if not isinstance(expression, str) or not expression.strip():
            issues.append(RuleIssue("error", "Validation rule requires a rule expression.", rule_id))
            continue
        if not isinstance(message, str) or not message.strip():
            issues.append(RuleIssue("error", "Validation message must be non-empty.", rule_id))
            continue
        if severity not in {"error", "warning", "info"}:
            issues.append(RuleIssue("error", "severity must be error, warning, or info.", rule_id))
            continue

        try:
            tree = _parse(expression)
        except RuleEngineError as exc:
            issues.append(RuleIssue("error", str(exc), rule_id))
            continue

        deps = _dependencies(tree)
        unknown = sorted(deps - known)
        if unknown:
            issues.append(
                RuleIssue(
                    "error",
                    "Unknown field reference(s): " + ", ".join(unknown),
                    rule_id,
                )
            )
            continue

        validation.append(
            ValidationRule(
                rule_id,
                expression.strip(),
                message.strip(),
                severity,
                deps,
            )
        )

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    try:
        return RuleEngine(calculated, validation, modifiers, limits), issues
    except RuleEngineError as exc:
        return None, [RuleIssue("error", str(exc))]
