"""Typed aggregate-only relational IR."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Aggregate:
    kind: str
    column: str | None


@dataclass(frozen=True)
class Projection:
    name: str
    aggregate: Aggregate | None


@dataclass(frozen=True)
class Predicate:
    kind: str
    column: str
    value: int | None = None


@dataclass(frozen=True)
class Query:
    group_by: str | None
    projections: tuple[Projection, ...]
    predicate: Predicate | None = None
