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
    ref: Ref | None


@dataclass(frozen=True)
class JoinProjection:
    name: str
    ref: Ref | None
    aggregate: JoinAggregate | None


@dataclass(frozen=True)
class JoinPredicate:
    op: str
    operands: tuple[Ref | int | JoinPredicate, ...]


@dataclass(frozen=True)
class JoinQuery:
    join_kind: str
    on: tuple[Ref, Ref]
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
            }
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
            return JoinAggregate("count_distinct", _ref(arg.expressions[0], spec, aliases))
        return JoinAggregate("count", _ref(arg, spec, aliases))
    if isinstance(node, (exp.Sum, exp.Min, exp.Max)) and node.this is not None:
        if any(value for key, value in node.args.items() if key != "this"):
            raise UnsupportedError("numeric aggregate has unsupported arguments")
        ref = _ref(node.this, spec, aliases)
        if spec.tables[ref.table].column(ref.column).type != "INTEGER":
            raise UnsupportedError("numeric aggregate requires INTEGER")
        return JoinAggregate(type(node).__name__.lower(), ref)
    raise UnsupportedError(f"unsupported expression: {type(node).__name__}")


def _operand(node: exp.Expression, spec: JoinSpec, aliases: tuple[str, str]) -> Ref | int:
    if isinstance(node, exp.Column):
        return _ref(node, spec, aliases)
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
    raise UnsupportedError("WHERE operands must be direct columns or signed 32-bit integers")


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
            if isinstance(left, int) and isinstance(right, int):
                raise UnsupportedError("WHERE comparison needs a source column")
            types = {
                spec.tables[item.table].column(item.column).type
                for item in (left, right)
                if isinstance(item, Ref)
            }
            if len(types) != 1 or (
                "DATE" in types and (isinstance(left, int) or isinstance(right, int))
            ):
                raise UnsupportedError("WHERE comparison operands have incompatible types")
            return JoinPredicate(op, (left, right))
    raise UnsupportedError(f"unsupported WHERE predicate: {type(node).__name__}")


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
    if join.args.get("side") == "LEFT" and join.args.get("kind") in {None, "OUTER"}:
        join_kind = "left"
    elif join.args.get("kind") == "INNER" and not join.args.get("side"):
        join_kind = "inner"
    else:
        raise UnsupportedError("only explicit INNER or LEFT JOIN is supported")
    if any(value for key, value in join.args.items() if key not in {"this", "kind", "side", "on"}):
        raise UnsupportedError("unsupported JOIN option")
    aliases = (
        _table(source.this, spec.tables[0].table),
        _table(join.this, spec.tables[1].table),
    )
    if aliases[0] == aliases[1]:
        raise UnsupportedError("table aliases must differ")
    on = join.args.get("on")
    if not isinstance(on, exp.EQ):
        raise UnsupportedError("JOIN ON must be one direct equality")
    left = _ref(on.this, spec, aliases)
    right = _ref(on.expression, spec, aliases)
    if {left.table, right.table} != {0, 1}:
        raise UnsupportedError("JOIN must equate one column from each table")
    if (
        spec.tables[left.table].column(left.column).type
        != spec.tables[right.table].column(right.column).type
    ):
        raise UnsupportedError("JOIN key types must match")
    if left.table == 1:
        left, right = right, left
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
    condition = _predicate(where.this, spec, aliases) if where is not None else None
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
    return JoinQuery(join_kind, (left, right), group_refs, condition, tuple(projections))


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
