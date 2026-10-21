"""Guarded admission for one materialized aggregate CTE or derived table.

This compiler reuses the existing typed joined-query parser for the inner
SELECT and emits the same relational plan evaluated by joined NoUndo search.
Only a single, nonrecursive, once-referenced aggregate stage is admitted.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError

from dataproof_verifier.join_model import (
    JoinAggregate,
    JoinProjection,
    JoinScalar,
    JoinSpec,
    Ref,
    _simple,
    parse_join_query,
)
from dataproof_verifier.models import SpecError, UnsupportedError
from dataproof_verifier.relational_core import (
    PLAN_VERSION,
    Aggregate,
    Materialize,
    RelationalPlan,
    compile_join_query,
)


def _inner_type(projection: JoinProjection, spec: JoinSpec) -> str:
    if isinstance(projection.ref, Ref):
        return spec.tables[projection.ref.table].column(projection.ref.column).type
    if isinstance(projection.ref, JoinScalar):
        return projection.ref.typ
    if projection.aggregate is not None:
        return "INTEGER"
    raise UnsupportedError("unknown materialized output type")


def _single_column(node: exp.Expression, alias: str, types: dict[str, str]) -> str:
    if (
        not isinstance(node, exp.Column)
        or node.table != alias
        or node.db
        or node.catalog
        or any(value for key, value in node.args.items() if key not in {"this", "table"})
    ):
        raise UnsupportedError("outer columns must be directly qualified by the materialized alias")
    name = _simple(node.name, "materialized column")
    if name not in types:
        raise UnsupportedError("unknown materialized output column")
    return name


def _outer_aggregate(node: exp.Expression, alias: str, types: dict[str, str]) -> JoinAggregate:
    if isinstance(node, exp.Count):
        if node.expressions or any(
            value for key, value in node.args.items() if key not in {"this", "big_int"}
        ):
            raise UnsupportedError("unsupported outer COUNT form")
        arg = node.this
        if isinstance(arg, exp.Star) and not any(arg.args.values()):
            return JoinAggregate("count_star", None)
        if isinstance(arg, exp.Distinct) and len(arg.expressions) == 1:
            name = _single_column(arg.expressions[0], alias, types)
            return JoinAggregate("count_distinct", JoinScalar("ref", types[name], (Ref(0, name),)))
        name = _single_column(arg, alias, types)
        return JoinAggregate("count", JoinScalar("ref", types[name], (Ref(0, name),)))
    if isinstance(node, (exp.Sum, exp.Min, exp.Max)):
        if any(value for key, value in node.args.items() if key != "this"):
            raise UnsupportedError("unsupported outer numeric aggregate option")
        name = _single_column(node.this, alias, types)
        if types[name] != "INTEGER":
            raise UnsupportedError("outer numeric aggregate requires INTEGER")
        return JoinAggregate(
            type(node).__name__.lower(), JoinScalar("ref", "INTEGER", (Ref(0, name),))
        )
    raise UnsupportedError("outer query requires admitted direct aggregates")


def _source(node: exp.Select, spec: JoinSpec) -> tuple[exp.Select, str]:
    source = node.args.get("from_")
    if not isinstance(source, exp.From) or any(
        value for key, value in source.args.items() if key != "this"
    ):
        raise UnsupportedError("outer query requires one materialized source")
    with_clause = node.args.get("with_")
    if with_clause is not None:
        if (
            not isinstance(with_clause, exp.With)
            or with_clause.args.get("recursive")
            or len(with_clause.expressions) != 1
            or any(
                value
                for key, value in with_clause.args.items()
                if key not in {"expressions", "recursive"}
            )
        ):
            raise UnsupportedError("one nonrecursive aggregate CTE is required")
        cte = with_clause.expressions[0]
        if not isinstance(cte, exp.CTE) or not isinstance(cte.this, exp.Select):
            raise UnsupportedError("aggregate CTE must contain a SELECT")
        if any(value for key, value in cte.args.items() if key not in {"this", "alias"}):
            raise UnsupportedError("unsupported aggregate CTE option")
        declaration = cte.args.get("alias")
        if not isinstance(declaration, exp.TableAlias) or declaration.args.get("columns"):
            raise UnsupportedError("aggregate CTE needs a simple name without column aliases")
        cte_name = _simple(cte.alias, "CTE name")
        if cte_name in {table.table for table in spec.tables}:
            raise UnsupportedError("CTE name collides with a source table")
        table = source.this
        if (
            not isinstance(table, exp.Table)
            or table.name != cte_name
            or table.db
            or table.catalog
            or any(value for key, value in table.args.items() if key not in {"this", "alias"})
        ):
            raise UnsupportedError("aggregate CTE must be referenced exactly once")
        alias = _simple(table.alias or cte_name, "materialized alias")
        return cte.this, alias
    derived = source.this
    if (
        not isinstance(derived, exp.Subquery)
        or not isinstance(derived.this, exp.Select)
        or not derived.alias
        or any(value for key, value in derived.args.items() if key not in {"this", "alias"})
    ):
        raise UnsupportedError("outer source must be one aggregate CTE or derived SELECT")
    declaration = derived.args.get("alias")
    if not isinstance(declaration, exp.TableAlias) or declaration.args.get("columns"):
        raise UnsupportedError("derived source column alias lists are unsupported")
    return derived.this, _simple(derived.alias, "derived alias")


def admit_query(sql: str, spec: JoinSpec, *, metric: bool) -> RelationalPlan:
    """Compile exactly one admitted original SQL SELECT, without executing it."""
    if len(sql) > 4096:
        raise UnsupportedError("SQL exceeds 4096 characters")
    try:
        statements = sqlglot.parse(sql, read="duckdb", error_level=ErrorLevel.RAISE)
    except ParseError as exc:
        raise SpecError(f"invalid SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsupportedError("exactly one SELECT is required")
    node = statements[0]
    if not isinstance(node.args.get("from_"), exp.From):
        raise UnsupportedError("SELECT requires a local source")
    # Historical direct joins and transparent projection CTEs continue through
    # their original parser, preserving its exact admission and diagnostics.
    if node.args.get("joins"):
        return compile_join_query(parse_join_query(sql, spec, metric=metric), spec)
    if any(
        value
        for key, value in node.args.items()
        if key not in {"expressions", "from_", "group", "with_"}
    ):
        raise UnsupportedError("unsupported outer aggregate-pipeline clause")
    inner, alias = _source(node, spec)
    inner_query = parse_join_query(inner.sql(dialect="duckdb"), spec, metric=False)
    inner_plan = compile_join_query(inner_query, spec)
    types = {
        projection.name: _inner_type(projection, spec) for projection in inner_query.projections
    }
    names = inner_plan.output_names
    group = node.args.get("group")
    group_refs: tuple[Ref, ...] = ()
    if group is not None:
        if (
            not isinstance(group, exp.Group)
            or not 1 <= len(group.expressions) <= 2
            or any(value for key, value in group.args.items() if key != "expressions")
        ):
            raise UnsupportedError("outer GROUP BY requires one or two direct columns")
        group_refs = tuple(Ref(0, _single_column(item, alias, types)) for item in group.expressions)
        if len(set(group_refs)) != len(group_refs):
            raise UnsupportedError("outer GROUP BY columns must be distinct")
    if bool(group_refs) == metric:
        raise UnsupportedError("outer view must group; outer metric must be scalar")
    projections: list[JoinProjection] = []
    for item in node.expressions:
        actual = item.this if isinstance(item, exp.Alias) else item
        name = item.alias if isinstance(item, exp.Alias) else None
        if isinstance(actual, exp.Column):
            column = _single_column(actual, alias, types)
            ref = Ref(0, column)
            if ref not in group_refs:
                raise UnsupportedError("outer direct projection must be a grouping column")
            projections.append(JoinProjection(_simple(name or column, "output alias"), ref, None))
        else:
            if not name:
                raise UnsupportedError("outer aggregate requires a named projection")
            projections.append(
                JoinProjection(
                    _simple(name, "output alias"), None, _outer_aggregate(actual, alias, types)
                )
            )
    if not projections or len({item.name for item in projections}) != len(projections):
        raise UnsupportedError("distinct outer output names required")
    if metric and (len(projections) != 1 or projections[0].aggregate is None):
        raise UnsupportedError("outer metric must contain exactly one scalar aggregate")
    if not metric and (
        {item.ref for item in projections if item.ref is not None} != set(group_refs)
        or sum(item.ref is not None for item in projections) != len(group_refs)
        or not any(item.aggregate is not None for item in projections)
    ):
        raise UnsupportedError("outer view needs each grouping column and an aggregate")
    materialized = Materialize(inner_plan.root, frozenset({0}))
    root = Aggregate(materialized, group_refs, tuple(projections), frozenset({0}), (names,))
    return RelationalPlan(
        PLAN_VERSION, root, tuple(item.name for item in projections), inner_plan.source_names
    )
