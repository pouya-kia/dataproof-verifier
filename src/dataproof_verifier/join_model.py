"""A separate, deliberately tiny two-table NoUndo contract.

The published one-table/Z3 contract is unchanged. This module admits only
explicit INNER/LEFT equijoins and uses complete finite search plus DuckDB checking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations_with_replacement, product
from math import comb
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError

from dataproof_verifier.models import (
    Row,
    Spec,
    SpecError,
    UnsupportedError,
    legal_world,
    parse_spec,
    serial_value,
)

MAX_COMBINED_WORLDS = 500
_NAME = re.compile(r"[a-z_][a-z_0-9]*\Z")


@dataclass(frozen=True)
class Ref:
    table: int
    column: str


@dataclass(frozen=True)
class JoinAggregate:
    kind: str
    value: JoinScalar | None


@dataclass(frozen=True)
class JoinScalar:
    kind: str
    typ: str
    args: tuple[Any, ...]


@dataclass(frozen=True)
class JoinProjection:
    name: str
    ref: Ref | None
    aggregate: JoinAggregate | None


@dataclass(frozen=True)
class JoinPredicate:
    op: str
    operands: tuple[Ref | int | str | JoinPredicate, ...]


@dataclass(frozen=True)
class JoinQuery:
    join_kind: str
    on: tuple[tuple[Ref, Ref], ...]
    group_by: tuple[Ref, ...]
    where: JoinPredicate | None
    projections: tuple[JoinProjection, ...]


@dataclass(frozen=True)
class JoinSpec:
    tables: tuple[Spec, Spec]
    view_sql: str
    metric_sql: str
    timeout_ms: int
    output_dir: Path


World = tuple[tuple[Row, ...], tuple[Row, ...]]


def _simple(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise SpecError(f"{label} must be a lowercase simple SQL identifier")
    return value


def parse_join_spec(raw: Any, source: Path | None = None) -> JoinSpec:
    if not isinstance(raw, dict):
        raise SpecError("join spec must be an object")
    if set(raw) - {"tables", "view", "metric", "timeout_ms", "output_dir"}:
        raise SpecError("unknown join spec fields")
    tables_raw = raw.get("tables")
    if not isinstance(tables_raw, list) or len(tables_raw) != 2:
        raise SpecError("exactly two tables are required")
    tables: list[Spec] = []
    for item in tables_raw:
        if not isinstance(item, dict):
            raise SpecError("table must be an object")
        if set(item) - {"name", "columns", "primary_key", "unique", "max_rows"}:
            raise SpecError("unknown table fields")
        max_rows = item.get("max_rows")
        if type(max_rows) is not int or not 0 <= max_rows <= 2:
            raise SpecError("per-table max_rows must be 0..2")
        schema = {key: value for key, value in item.items() if key != "max_rows"}
        table = parse_spec(
            {
                "table": schema,
                "views": ["SELECT 1"],
                "metric": "SELECT 1",
                "max_rows": max_rows,
            },
            allow_string=True,
        )
        _simple(table.table, "table name")
        if len(table.columns) > 3:
            raise SpecError("at most three columns per table")
        for col in table.columns:
            _simple(col.name, "column name")
            if len(col.domain) > 3:
                raise SpecError("at most three effective values per column, including NULL")
        tables.append(table)
    if tables[0].table == tables[1].table:
        raise SpecError("table names must differ")
    view, metric = raw.get("view"), raw.get("metric")
    if not isinstance(view, str) or not isinstance(metric, str):
        raise SpecError("view and metric must be SQL strings")
    timeout = raw.get("timeout_ms", 10000)
    if type(timeout) is not int or not 1 <= timeout <= 30000:
        raise SpecError("timeout_ms must be 1..30000")
    output = raw.get("output_dir", "artifacts/join")
    if not isinstance(output, str) or not output:
        raise SpecError("output_dir must be a path")
    path = Path(output)
    if source is not None and not path.is_absolute():
        path = (source.parent / path).absolute()
    spec = JoinSpec((tables[0], tables[1]), view, metric, timeout, path)
    # Reject analytically large cross-products before materializing worlds.
    if analytical_world_bound(spec) > MAX_COMBINED_WORLDS:
        raise UnsupportedError(f"analytical combined-world bound exceeds {MAX_COMBINED_WORLDS}")
    return spec


def analytical_world_bound(spec: JoinSpec) -> int:
    total = 1
    for table in spec.tables:
        row_count = 1
        for col in table.columns:
            row_count *= len(col.domain)
        total *= sum(comb(row_count + size - 1, size) for size in range(table.max_rows + 1))
    return total


def canonical_spec(spec: JoinSpec) -> dict[str, Any]:
    tables = []
    for table in spec.tables:
        tables.append(
            {
                "name": table.table,
                "max_rows": table.max_rows,
                "columns": [
                    {
                        "name": col.name,
                        "type": col.type,
                        "nullable": col.nullable,
                        "domain": [serial_value(value) for value in col.domain],
                    }
                    for col in table.columns
                ],
                "primary_key": list(table.primary_key),
                "unique": [list(key) for key in table.unique],
            }
        )
    return {
        "tables": tables,
        "view": spec.view_sql,
        "metric": spec.metric_sql,
        "timeout_ms": spec.timeout_ms,
    }


def _table(node: exp.Expression, expected: str) -> str:
    if not isinstance(node, exp.Table) or node.name != expected or node.db or node.catalog:
        raise UnsupportedError("query must read the two declared local tables in order")
    if any(value for key, value in node.args.items() if key not in {"this", "alias"}):
        raise UnsupportedError("unsupported table source option")
    if not node.alias:
        raise UnsupportedError("both joined tables require explicit aliases")
    return _simple(node.alias, "table alias")


def _ref(node: exp.Expression, spec: JoinSpec, aliases: tuple[str, str]) -> Ref:
    if not isinstance(node, exp.Column) or not node.table or node.db or node.catalog:
        raise UnsupportedError("joined columns must be directly alias-qualified")
    if any(value for key, value in node.args.items() if key not in {"this", "table"}):
        raise UnsupportedError("unsupported column expression")
    if node.table not in aliases:
        raise UnsupportedError("unknown table alias")
    name = _simple(node.name, "column")
    index = aliases.index(node.table)
    spec.tables[index].column(name)
    return Ref(index, name)


def _scalar(node: exp.Expression, spec: JoinSpec, aliases: tuple[str, str]) -> JoinScalar:
    if isinstance(node, exp.Paren):
        return _scalar(node.this, spec, aliases)
    if isinstance(node, exp.Column):
        ref = _ref(node, spec, aliases)
        return JoinScalar("ref", spec.tables[ref.table].column(ref.column).type, (ref,))
    if isinstance(node, exp.Null):
        return JoinScalar("null", "NULL", ())
    if isinstance(node, (exp.Literal, exp.Neg)):
        value = _operand(node, spec, aliases)
        if isinstance(value, Ref):
            raise AssertionError("literal parser returned a column")
        return JoinScalar("literal", "INTEGER" if type(value) is int else "STRING", (value,))
    if isinstance(node, (exp.Add, exp.Sub)):
        left = _scalar(node.this, spec, aliases)
        right = _scalar(node.expression, spec, aliases)
        if left.typ != "INTEGER" or right.typ != "INTEGER":
            raise UnsupportedError("arithmetic requires two INTEGER operands")
        result = JoinScalar("add" if isinstance(node, exp.Add) else "sub", "INTEGER", (left, right))
        low, high = _int_limits(result, spec)
        if low < -(2**31) or high >= 2**31:
            raise UnsupportedError("integer arithmetic may overflow the 32-bit domain")
        return result
    if isinstance(node, exp.Cast):
        if type(node) is not exp.Cast:
            raise UnsupportedError("only strict CAST is supported")
        if any(value for key, value in node.args.items() if key not in {"this", "to"}):
            raise UnsupportedError("unsupported CAST option")
        child = _scalar(node.this, spec, aliases)
        target = node.args.get("to")
        if not isinstance(target, exp.DataType):
            raise UnsupportedError("CAST target must be an admitted type")
        if (
            target.this != exp.DataType.Type.INT
            or target.args.get("expressions") is not None
            or target.args.get("nested") not in {None, False}
        ):
            raise UnsupportedError("only identity CAST(... AS INTEGER) is supported")
        if child.typ != "INTEGER":
            raise UnsupportedError("CAST may not coerce between types")
        return JoinScalar("identity_cast", "INTEGER", (child,))
    if isinstance(node, exp.Case):
        if any(value for key, value in node.args.items() if key not in {"this", "ifs", "default"}):
            raise UnsupportedError("unsupported CASE option")
        base = _scalar(node.this, spec, aliases) if node.this is not None else None
        if base is not None and base.typ not in {"INTEGER", "STRING"}:
            raise UnsupportedError("simple CASE base type is unsupported")
        arms: list[tuple[JoinPredicate | JoinScalar, JoinScalar]] = []
        for arm in node.args.get("ifs") or []:
            if not isinstance(arm, exp.If):
                raise UnsupportedError("unsupported CASE arm")
            if any(value for key, value in arm.args.items() if key not in {"this", "true"}):
                raise UnsupportedError("unsupported CASE arm option")
            condition: JoinPredicate | JoinScalar
            if base is None:
                condition = _predicate(arm.this, spec, aliases)
            else:
                condition = _scalar(arm.this, spec, aliases)
                if condition.typ != base.typ:
                    raise UnsupportedError("simple CASE types do not match")
            result = _scalar(arm.args["true"], spec, aliases)
            arms.append((condition, result))
        if not 1 <= len(arms) <= 3:
            raise UnsupportedError("CASE requires one to three WHEN arms")
        default = (
            _scalar(node.args["default"], spec, aliases)
            if node.args.get("default") is not None
            else JoinScalar("null", "NULL", ())
        )
        types = {result.typ for _, result in arms} | {default.typ}
        types.discard("NULL")
        if len(types) != 1 or not types <= {"INTEGER", "STRING"}:
            raise UnsupportedError("CASE branches must share INTEGER or STRING type")
        return JoinScalar("case", types.pop(), (base, tuple(arms), default))
    raise UnsupportedError(f"unsupported scalar expression: {type(node).__name__}")


def _int_limits(value: JoinScalar, spec: JoinSpec) -> tuple[int, int]:
    if value.kind == "literal":
        item = value.args[0]
        assert type(item) is int
        return item, item
    if value.kind == "ref":
        ref = value.args[0]
        assert isinstance(ref, Ref)
        domain = spec.tables[ref.table].column(ref.column).domain
        values = [item for item in domain if type(item) is int]
        assert len(values) == sum(item is not None for item in domain)
        return (min(values), max(values)) if values else (0, 0)
    if value.kind == "identity_cast":
        return _int_limits(value.args[0], spec)
    if value.kind in {"add", "sub"}:
        a, b = (_int_limits(child, spec) for child in value.args)
        return (a[0] + b[0], a[1] + b[1]) if value.kind == "add" else (a[0] - b[1], a[1] - b[0])
    if value.kind == "case":
        _, arms, default = value.args
        limits = [_int_limits(item, spec) for _, item in arms if item.typ == "INTEGER"]
        if default.typ == "INTEGER":
            limits.append(_int_limits(default, spec))
        return min(low for low, _ in limits), max(high for _, high in limits)
    raise UnsupportedError("unsupported integer bound expression")


def _aggregate(node: exp.Expression, spec: JoinSpec, aliases: tuple[str, str]) -> JoinAggregate:
    if isinstance(node, exp.Count):
        if node.expressions or any(
            value for key, value in node.args.items() if key not in {"this", "big_int"}
        ):
            raise UnsupportedError("COUNT has unsupported arguments")
        arg = node.this
        if isinstance(arg, exp.Star) and not any(arg.args.values()):
            return JoinAggregate("count_star", None)
        if isinstance(arg, exp.Distinct) and len(arg.expressions) == 1:
            return JoinAggregate("count_distinct", _scalar(arg.expressions[0], spec, aliases))
        return JoinAggregate("count", _scalar(arg, spec, aliases))
    if isinstance(node, (exp.Sum, exp.Min, exp.Max)) and node.this is not None:
        if any(value for key, value in node.args.items() if key != "this"):
            raise UnsupportedError("numeric aggregate has unsupported arguments")
        value = _scalar(node.this, spec, aliases)
        if value.typ != "INTEGER":
            raise UnsupportedError("numeric aggregate requires INTEGER")
        return JoinAggregate(type(node).__name__.lower(), value)
    raise UnsupportedError(f"unsupported expression: {type(node).__name__}")


def _operand(node: exp.Expression, spec: JoinSpec, aliases: tuple[str, str]) -> Ref | int | str:
    if isinstance(node, exp.Column):
        return _ref(node, spec, aliases)
    if isinstance(node, exp.Literal) and node.is_string:
        value = node.this
        if (
            isinstance(value, str)
            and 1 <= len(value) <= 32
            and all(32 <= ord(char) <= 126 for char in value)
        ):
            return value
    if isinstance(node, exp.Literal) and not node.is_string and node.this.isdigit():
        value = int(node.this)
        if value < 2**31:
            return value
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        literal = node.this
        if not literal.is_string and literal.this.isdigit():
            value = -int(literal.this)
            if -(2**31) <= value:
                return value
    raise UnsupportedError("WHERE operands must be direct columns or finite typed literals")


def _predicate(node: exp.Expression, spec: JoinSpec, aliases: tuple[str, str]) -> JoinPredicate:
    if isinstance(node, exp.Paren):
        return _predicate(node.this, spec, aliases)
    if isinstance(node, (exp.And, exp.Or)):
        return JoinPredicate(
            type(node).__name__.lower(),
            (_predicate(node.this, spec, aliases), _predicate(node.expression, spec, aliases)),
        )
    if isinstance(node, exp.Not):
        return JoinPredicate("not", (_predicate(node.this, spec, aliases),))
    if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
        return JoinPredicate("is_null", (_ref(node.this, spec, aliases),))
    comparisons = {
        exp.EQ: "eq",
        exp.NEQ: "neq",
        exp.LT: "lt",
        exp.LTE: "lte",
        exp.GT: "gt",
        exp.GTE: "gte",
    }
    for kind, op in comparisons.items():
        if isinstance(node, kind):
            left = _operand(node.this, spec, aliases)
            right = _operand(node.expression, spec, aliases)
            if not isinstance(left, Ref) and not isinstance(right, Ref):
                raise UnsupportedError("WHERE comparison needs a source column")
            types = {
                spec.tables[item.table].column(item.column).type
                for item in (left, right)
                if isinstance(item, Ref)
            }
            if len(types) != 1:
                raise UnsupportedError("WHERE comparison operands have incompatible types")
            typ = next(iter(types))
            if any(
                not isinstance(item, Ref)
                and (
                    (typ == "INTEGER" and type(item) is not int)
                    or (typ == "DATE")
                    or (typ == "STRING" and type(item) is not str)
                )
                for item in (left, right)
            ):
                raise UnsupportedError("WHERE comparison operands have incompatible types")
            if typ == "STRING" and op not in {"eq", "neq"}:
                raise UnsupportedError("STRING supports only binary equality and inequality")
            return JoinPredicate(op, (left, right))
    raise UnsupportedError(f"unsupported WHERE predicate: {type(node).__name__}")


def _transparent_sources(node: exp.Select, spec: JoinSpec) -> exp.Select:
    """Expand only row-preserving column renames, never a general SQL rewrite.

    A projection-only SELECT has a one-to-one bag mapping to its source rows.
    This allows the existing two-table evaluator to use base-column references;
    DuckDB still runs the untouched original SQL for independent checking.
    """
    node = node.copy()
    definitions: dict[str, tuple[str, dict[str, str]]] = {}
    with_clause = node.args.get("with_")
    if with_clause is not None:
        if (
            not isinstance(with_clause, exp.With)
            or with_clause.args.get("recursive")
            or not 1 <= len(with_clause.expressions) <= 2
            or any(
                value
                for key, value in with_clause.args.items()
                if key not in {"expressions", "recursive"}
            )
        ):
            raise UnsupportedError("only one or two nonrecursive projection CTEs are supported")

    def direct_projection(query: exp.Expression) -> tuple[str, dict[str, str]]:
        if not isinstance(query, exp.Select) or any(
            value for key, value in query.args.items() if key not in {"expressions", "from_"}
        ):
            raise UnsupportedError("CTE/derived table must be a projection-only SELECT")
        source = query.args.get("from_")
        if not isinstance(source, exp.From) or not isinstance(source.this, exp.Table):
            raise UnsupportedError("CTE/derived table requires one local table source")
        if any(value for key, value in source.args.items() if key != "this"):
            raise UnsupportedError("unsupported nested FROM option")
        source_table = source.this
        if source_table.db or source_table.catalog:
            raise UnsupportedError("external table source is unsupported")
        if any(value for key, value in source_table.args.items() if key not in {"this", "alias"}):
            raise UnsupportedError("unsupported nested table option")
        table_alias = source_table.args.get("alias")
        if isinstance(table_alias, exp.TableAlias) and table_alias.args.get("columns"):
            raise UnsupportedError("nested source column-alias lists are unsupported")
        name = _simple(source_table.name, "nested source")
        source_alias = source_table.alias or name
        if name in definitions:
            base, inherited = definitions[name]
        elif name in {table.table for table in spec.tables}:
            base = name
            inherited = {
                col.name: col.name
                for table in spec.tables
                if table.table == name
                for col in table.columns
            }
        else:
            raise UnsupportedError("CTE dependency must be an earlier CTE or declared table")
        mapping: dict[str, str] = {}
        if not 1 <= len(query.expressions) <= 3:
            raise UnsupportedError("projection CTE requires one to three direct columns")
        for item in query.expressions:
            actual = item.this if isinstance(item, exp.Alias) else item
            if not isinstance(actual, exp.Column) or actual.db or actual.catalog:
                raise UnsupportedError("projection CTE admits only direct columns")
            if actual.table and actual.table != source_alias:
                raise UnsupportedError("nested column qualifier does not match source")
            output = _simple(
                item.alias if isinstance(item, exp.Alias) else actual.name, "projection alias"
            )
            column = _simple(actual.name, "nested column")
            if output in mapping or column not in inherited:
                raise UnsupportedError("ambiguous or unknown nested projection column")
            mapping[output] = inherited[column]
        return base, mapping

    if with_clause is not None:
        for cte in with_clause.expressions:
            if (
                not isinstance(cte, exp.CTE)
                or not cte.alias
                or cte.args.get("materialized")
                or cte.args.get("key_expressions")
            ):
                raise UnsupportedError("unsupported CTE declaration")
            cte_alias = cte.args.get("alias")
            if isinstance(cte_alias, exp.TableAlias) and cte_alias.args.get("columns"):
                raise UnsupportedError("CTE column-alias lists are unsupported")
            name = _simple(cte.alias, "CTE name")
            if name in definitions or name in {table.table for table in spec.tables}:
                raise UnsupportedError("CTE name must be unique and distinct from source tables")
            definitions[name] = direct_projection(cte.this)

    alias_maps: dict[str, dict[str, str]] = {}
    source = node.args.get("from_")
    joins = node.args.get("joins")
    if not isinstance(source, exp.From) or not isinstance(joins, list) or len(joins) != 1:
        return node

    def expand(item: exp.Expression) -> exp.Expression:
        if isinstance(item, exp.Subquery):
            if not item.alias or any(
                value for key, value in item.args.items() if key not in {"this", "alias"}
            ):
                raise UnsupportedError("derived table requires a simple alias")
            base, mapping = direct_projection(item.this)
            alias = _simple(item.alias, "derived alias")
        elif isinstance(item, exp.Table) and item.name in definitions:
            if item.db or item.catalog:
                raise UnsupportedError("external CTE reference is unsupported")
            if any(value for key, value in item.args.items() if key not in {"this", "alias"}):
                raise UnsupportedError("unsupported CTE reference option")
            base, mapping = definitions[item.name]
            alias = _simple(item.alias or item.name, "CTE reference alias")
        else:
            return item
        if alias in alias_maps:
            raise UnsupportedError("source aliases must differ")
        alias_maps[alias] = mapping
        return exp.Table(
            this=exp.to_identifier(base), alias=exp.TableAlias(this=exp.to_identifier(alias))
        )

    source.set("this", expand(source.this))
    joins[0].set("this", expand(joins[0].this))
    node.set("with_", None)
    if definitions and not alias_maps:
        raise UnsupportedError("unused CTE definitions are unsupported")
    for column in node.find_all(exp.Column):
        if column.table in alias_maps:
            mapping = alias_maps[column.table]
            if column.name not in mapping:
                raise UnsupportedError("outer query references an unprojected nested column")
            column.set("this", exp.to_identifier(mapping[column.name]))
    return node


def parse_join_query(sql: str, spec: JoinSpec, *, metric: bool) -> JoinQuery:
    if len(sql) > 4096:
        raise UnsupportedError("SQL exceeds 4096 characters")
    try:
        statements = sqlglot.parse(sql, read="duckdb", error_level=ErrorLevel.RAISE)
    except ParseError as exc:
        raise SpecError(f"invalid SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsupportedError("exactly one SELECT is required")
    node = statements[0]
    node = _transparent_sources(node, spec)
    if any(
        value
        for key, value in node.args.items()
        if key not in {"expressions", "from_", "joins", "group", "where"}
    ):
        raise UnsupportedError("unsupported SELECT clause")
    source = node.args.get("from_")
    joins = node.args.get("joins")
    if not isinstance(source, exp.From) or not isinstance(joins, list) or len(joins) != 1:
        raise UnsupportedError("exactly one explicit INNER or LEFT JOIN is required")
    if any(value for key, value in source.args.items() if key != "this"):
        raise UnsupportedError("unsupported FROM source")
    join = joins[0]
    if not isinstance(join, exp.Join):
        raise UnsupportedError("only explicit INNER or LEFT JOIN is supported")
    side, kind = join.args.get("side"), join.args.get("kind")
    if side in {"LEFT", "RIGHT", "FULL"} and kind in {None, "OUTER"}:
        join_kind = side.lower()
    elif kind == "INNER" and not side:
        join_kind = "inner"
    else:
        raise UnsupportedError("only explicit INNER, LEFT, RIGHT or FULL JOIN is supported")
    if any(value for key, value in join.args.items() if key not in {"this", "kind", "side", "on"}):
        raise UnsupportedError("unsupported JOIN option")
    aliases = (
        _table(source.this, spec.tables[0].table),
        _table(join.this, spec.tables[1].table),
    )
    if aliases[0] == aliases[1]:
        raise UnsupportedError("table aliases must differ")
    on = join.args.get("on")
    conditions: list[exp.Expression] = []

    def flatten_equalities(item: exp.Expression) -> None:
        if isinstance(item, exp.And):
            flatten_equalities(item.this)
            flatten_equalities(item.expression)
        else:
            conditions.append(item)

    if not isinstance(on, exp.Expression):
        raise UnsupportedError("JOIN ON requires direct equality keys")
    flatten_equalities(on)
    if not 1 <= len(conditions) <= 2:
        raise UnsupportedError("JOIN ON requires one or two equality keys")
    keys: list[tuple[Ref, Ref]] = []
    for on_condition in conditions:
        if not isinstance(on_condition, exp.EQ):
            raise UnsupportedError("JOIN ON requires only direct equality keys")
        if not isinstance(on_condition.this, exp.Column) or not isinstance(
            on_condition.expression, exp.Column
        ):
            raise UnsupportedError("JOIN ON requires direct column equalities")
        left = _ref(on_condition.this, spec, aliases)
        right = _ref(on_condition.expression, spec, aliases)
        if {left.table, right.table} != {0, 1}:
            raise UnsupportedError("JOIN key must equate one column from each table")
        if (
            spec.tables[left.table].column(left.column).type
            != spec.tables[right.table].column(right.column).type
        ):
            raise UnsupportedError("JOIN key types must match")
        keys.append((left, right) if left.table == 0 else (right, left))
    if len(set(keys)) != len(keys):
        raise UnsupportedError("JOIN key equalities must be distinct")
    group = node.args.get("group")
    group_refs: tuple[Ref, ...] = ()
    if group is not None:
        if not isinstance(group, exp.Group) or not 1 <= len(group.expressions) <= 2:
            raise UnsupportedError("one or two direct GROUP BY columns required")
        if any(value for key, value in group.args.items() if key != "expressions"):
            raise UnsupportedError("unsupported GROUP BY option")
        group_refs = tuple(_ref(item, spec, aliases) for item in group.expressions)
        if len(set(group_refs)) != len(group_refs):
            raise UnsupportedError("GROUP BY columns must be distinct")
    if metric and group_refs:
        raise UnsupportedError("metric must be scalar")
    if not metric and not group_refs:
        raise UnsupportedError("retained view must group by one or two columns")
    where = node.args.get("where")
    if where is not None and not isinstance(where, exp.Where):
        raise UnsupportedError("invalid WHERE clause")
    where_condition = _predicate(where.this, spec, aliases) if where is not None else None
    projections: list[JoinProjection] = []
    for expression in node.expressions:
        actual = expression.this if isinstance(expression, exp.Alias) else expression
        alias = expression.alias if isinstance(expression, exp.Alias) else None
        if isinstance(actual, exp.Column):
            ref = _ref(actual, spec, aliases)
            if ref not in group_refs:
                raise UnsupportedError("nonaggregate projection must be the grouping column")
            projections.append(
                JoinProjection(_simple(alias or ref.column, "projection"), ref, None)
            )
        else:
            if not alias:
                raise UnsupportedError("aggregate requires an alias")
            projections.append(
                JoinProjection(
                    _simple(alias, "aggregate alias"), None, _aggregate(actual, spec, aliases)
                )
            )
    if not projections or len({p.name for p in projections}) != len(projections):
        raise UnsupportedError("distinct named projections required")
    if metric and (len(projections) != 1 or projections[0].aggregate is None):
        raise UnsupportedError("metric must select one scalar aggregate")
    if not metric and (
        {p.ref for p in projections if p.ref is not None} != set(group_refs)
        or sum(p.ref is not None for p in projections) != len(group_refs)
        or not any(p.aggregate is not None for p in projections)
    ):
        raise UnsupportedError("view needs every grouping column once and an aggregate")
    return JoinQuery(join_kind, tuple(keys), group_refs, where_condition, tuple(projections))


def all_join_worlds(spec: JoinSpec) -> list[World]:
    """Complete unordered bags in the admitted analytical bound, keys included."""
    if analytical_world_bound(spec) > MAX_COMBINED_WORLDS:
        raise UnsupportedError("combined-world bound exceeds safety cap")
    sides: list[list[tuple[Row, ...]]] = []
    for table in spec.tables:
        possible = list(product(*(col.domain for col in table.columns)))
        worlds = [
            rows
            for size in range(table.max_rows + 1)
            for rows in combinations_with_replacement(possible, size)
            if legal_world(table, rows)
        ]
        sides.append(worlds)
    return [(left, right) for left, right in product(sides[0], sides[1])]


def legal_join_world(spec: JoinSpec, world: World) -> bool:
    return all(legal_world(table, rows) for table, rows in zip(spec.tables, world, strict=True))


def serialize_world(world: World) -> list[list[list[int | str | None]]]:
    return [[[serial_value(value) for value in row] for row in rows] for rows in world]
