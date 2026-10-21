"""Fail-closed SQLGlot AST to typed IR conversion."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError

from dataproof_verifier.ir import Aggregate, Predicate, Projection, Query
from dataproof_verifier.models import InvalidSqlError, Spec, UnsupportedError


def _column(node: exp.Expression, spec: Spec) -> str:
    if not isinstance(node, exp.Column) or node.table or node.db or node.catalog:
        raise UnsupportedError("only unqualified direct columns are supported")
    name = node.name
    spec.column(name)
    return name


def _aggregate(node: exp.Expression, spec: Spec) -> Aggregate:
    if isinstance(node, exp.Count):
        if node.expressions:
            raise UnsupportedError("COUNT has unsupported arguments")
        arg = node.this
        if isinstance(arg, exp.Star) and not any(arg.args.values()):
            return Aggregate("count_star", None)
        if isinstance(arg, exp.Distinct) and len(arg.expressions) == 1:
            return Aggregate("count_distinct", _column(arg.expressions[0], spec))
        return Aggregate("count", _column(arg, spec))
    if isinstance(node, (exp.Sum, exp.Min, exp.Max)) and node.this is not None:
        if any(value for key, value in node.args.items() if key != "this"):
            raise UnsupportedError("numeric aggregate has unsupported arguments")
        name = _column(node.this, spec)
        if spec.column(name).type != "INTEGER":
            raise UnsupportedError("numeric aggregate requires an INTEGER column")
        return Aggregate(type(node).__name__.lower(), name)
    raise UnsupportedError(f"unsupported expression: {type(node).__name__}")


def _predicate(node: exp.Expression, spec: Spec) -> Predicate:
    if isinstance(node, exp.EQ):
        name = _column(node.this, spec)
        if spec.column(name).type != "INTEGER":
            raise UnsupportedError("equality filter requires an INTEGER column")
        rhs = node.expression
        sign = 1
        if isinstance(rhs, exp.Neg):
            rhs = rhs.this
            sign = -1
        if not isinstance(rhs, exp.Literal) or not rhs.is_int:
            raise UnsupportedError("equality filter requires an integer literal")
        value = sign * int(rhs.this)
        if not -(2**31) <= value < 2**31:
            raise UnsupportedError("integer filter literal exceeds INTEGER range")
        return Predicate("eq", name, value)
    kind = "is_null"
    if isinstance(node, exp.Not):
        kind = "is_not_null"
        node = node.this
    if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
        return Predicate(kind, _column(node.this, spec))
    raise UnsupportedError("unsupported WHERE predicate")


def parse_query(sql: str, spec: Spec, *, metric: bool) -> Query:
    if len(sql) > 4096:
        raise UnsupportedError("SQL exceeds 4096 characters")
    try:
        statements = sqlglot.parse(sql, read="duckdb", error_level=ErrorLevel.RAISE)
    except ParseError as exc:
        raise InvalidSqlError(f"invalid SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsupportedError("exactly one SELECT statement is required")
    node = statements[0]
    allowed_clauses = {"expressions", "from_", "group", "where"}
    unsupported_clauses = sorted(
        key for key, value in node.args.items() if key not in allowed_clauses and value
    )
    if unsupported_clauses:
        names = {"joins": "JOIN", "order": "ORDER BY", "grouping_sets": "GROUPING SETS"}
        labels = ", ".join(names.get(key, key.upper()) for key in unsupported_clauses)
        raise UnsupportedError(f"unsupported SELECT clause: {labels}")
    from_clause = node.args.get("from_")
    if not isinstance(from_clause, exp.From) or not isinstance(from_clause.this, exp.Table):
        raise UnsupportedError("one direct source table is required")
    table = from_clause.this
    if table.name != spec.table or table.db or table.catalog or table.alias:
        raise UnsupportedError("query must read the declared local table")
    where = node.args.get("where")
    predicate = None
    if where is not None:
        if not isinstance(where, exp.Where) or where.this is None:
            raise UnsupportedError("unsupported WHERE clause")
        predicate = _predicate(where.this, spec)
    group = node.args.get("group")
    group_name: str | None = None
    if group is not None:
        if not isinstance(group, exp.Group) or len(group.expressions) != 1:
            raise UnsupportedError("one direct GROUP BY column is required")
        group_name = _column(group.expressions[0], spec)
    if metric and group_name is not None:
        raise UnsupportedError("metric must be scalar")
    if not metric and group_name is None:
        raise UnsupportedError("retained view must group by one column")
    projections: list[Projection] = []
    for expression in node.expressions:
        actual = expression.this if isinstance(expression, exp.Alias) else expression
        alias = expression.alias if isinstance(expression, exp.Alias) else None
        if isinstance(actual, exp.Column):
            name = _column(actual, spec)
            if name != group_name:
                raise UnsupportedError("nonaggregated projection must be the grouping column")
            projections.append(Projection(alias or name, None))
        else:
            if not alias:
                raise UnsupportedError("aggregates require explicit aliases")
            projections.append(Projection(alias, _aggregate(actual, spec)))
    if not projections or len({p.name for p in projections}) != len(projections):
        raise UnsupportedError("query must have distinct named projections")
    if metric and (len(projections) != 1 or projections[0].aggregate is None):
        raise UnsupportedError("metric must select exactly one scalar aggregate")
    if not metric and (
        sum(p.aggregate is None for p in projections) != 1
        or not any(p.aggregate is not None for p in projections)
    ):
        raise UnsupportedError("view needs its grouping column and an aggregate")
    return Query(group_name, tuple(projections), predicate)
