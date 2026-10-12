"""SQL template SHAPES -- the unit the effective-n ceiling is computed in.

`ledger/generate.py`'s header states the convention this module exists to honour:
replicates of a shape are correlated, so the effective n of a taskset is bounded by its
SHAPE count divided by the within-shape correlation, and **only a grammar raises shapes;
a bigger file raises replicates.** The `ledger` taskset died of exactly that confusion --
9 cheap shapes against 61 effective paired tasks needed, with a vertical asymptote at
rho = 0.1475, and going 40 -> 400 records would have multiplied replicates and added zero
shapes.

BIRD dev ships 1534 questions. **1534 is a question count, not a shape count**, and
reporting it as the instrument's n would repeat the dead taskset's error one dataset
larger. Many BIRD questions are the same clause skeleton over a different column of a
different database: `SELECT COUNT(*) FROM t WHERE c = 'x'` asked about schools, then about
cards, then about superheroes is one shape with three replicates. Whether a 0.6B policy
solves one is strongly informative about the other two, which is what correlation means.

So this module reduces a query to its CLAUSE SKELETON and nothing else. Identifiers,
literals and numbers are erased; what survives is the structure a solution strategy has to
produce: how many table references, which joins, which aggregates, grouping, filtering
depth, nesting, set operations, ordering, arithmetic.

**Granularity is a judgement call, and a single number would hide that.** A shape
definition that is too coarse undercounts shapes and overstates correlation; too fine, and
every question is its own shape and the ceiling becomes the question count again -- the
very trap being avoided. This module therefore emits TWO granularities and
`bench/suite.py:report()` prints both, so a reader can see how sensitive the ceiling is to
the choice rather than taking one on trust:

- `coarse` -- the structural family: table-reference bucket, aggregation, grouping,
  nesting, set operations. Roughly "what kind of query is this".
- `fine` -- the full skeleton, including *which* aggregates, join types, ordering,
  predicate-count bucket, CASE and arithmetic. Roughly "what does a solution have to
  emit".

The honest claim is that the true effective-n ceiling lies between the two.

No SQL parser dependency. The repo has none and adding one to compute a descriptive
statistic would be a dependency bought for a report. A tokenizer that erases literals and
quoted identifiers is sufficient for a clause skeleton, and its failure mode is visible:
an unparsed construct lands in `UNKNOWN` tokens, which `report()` counts rather than
swallows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- tokenizer --------------------------------------------------------------------
#
# One pass, longest-alternative-first. Comments and whitespace are dropped; string
# literals, quoted identifiers and numbers collapse to placeholders, because a skeleton
# that retained them would make `WHERE c = 'CA'` and `WHERE c = 'NY'` two shapes -- the
# replicate trap, reintroduced at the token level.
_SCAN = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<line_comment>--[^\n]*)
    | (?P<block_comment>/\*.*?\*/)
    | (?P<string>'(?:[^']|'')*')
    | (?P<dq>"(?:[^"]|"")*")
    | (?P<bt>`(?:[^`]|``)*`)
    | (?P<br>\[[^\]]*\])
    | (?P<number>\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+|\d+(?:[eE][+-]?\d+)?)
    | (?P<word>[A-Za-z_][A-Za-z_0-9$]*)
    | (?P<op><=|>=|<>|!=|\|\||[-+*/%<>=(),.;:?])
    | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)

# Only words that carry STRUCTURE are kept as keywords. Everything else becomes `ID`,
# which is what erases table and column names from the skeleton.
_KEYWORDS = frozenset("""
    SELECT FROM WHERE GROUP BY HAVING ORDER LIMIT OFFSET DISTINCT ALL
    JOIN INNER LEFT RIGHT FULL OUTER CROSS NATURAL ON USING
    UNION INTERSECT EXCEPT
    AND OR NOT IN EXISTS BETWEEN LIKE GLOB IS NULL CASE WHEN THEN ELSE END
    AS ASC DESC CAST WITH RECURSIVE OVER PARTITION
    COUNT SUM AVG MIN MAX TOTAL GROUP_CONCAT ROUND ABS IIF COALESCE NULLIF
    STRFTIME SUBSTR REPLACE LENGTH LOWER UPPER TRIM DATE JULIANDAY
    INT INTEGER REAL TEXT NUMERIC
""".split())

AGGREGATES = frozenset({"COUNT", "SUM", "AVG", "MIN", "MAX", "TOTAL", "GROUP_CONCAT"})
SETOPS = ("UNION", "INTERSECT", "EXCEPT")
_JOIN_MODIFIERS = frozenset({"INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS",
                             "NATURAL"})
# A FROM list ends at the first of these, at the same paren depth.
_FROM_TERMINATORS = frozenset({"WHERE", "GROUP", "ORDER", "LIMIT", "HAVING", "ON",
                               "USING", "UNION", "INTERSECT", "EXCEPT", "JOIN"}
                              | _JOIN_MODIFIERS)
_VALUE_ENDERS = frozenset({"ID", "NUM", "LIT", ")"})


def tokenize(sql: str) -> list[str]:
    """SQL -> structural tokens. `ID`/`NUM`/`LIT` are placeholders, `UNKNOWN` is a
    character the scanner could not classify, kept rather than dropped so that an
    unparsed construct shows up in the report instead of silently shrinking a shape."""
    out: list[str] = []
    for m in _SCAN.finditer(sql):
        kind = m.lastgroup
        if kind in ("ws", "line_comment", "block_comment"):
            continue
        if kind == "string":
            out.append("LIT")
        elif kind in ("dq", "bt", "br"):
            out.append("ID")
        elif kind == "number":
            out.append("NUM")
        elif kind == "word":
            up = m.group().upper()
            out.append(up if up in _KEYWORDS else "ID")
        elif kind == "op":
            out.append(m.group())
        else:
            out.append("UNKNOWN")
    return out


@dataclass(frozen=True)
class Skeleton:
    """The clause skeleton of one query. Every field is derived from the token stream;
    nothing here is read off the dataset's own metadata, because BIRD's difficulty label
    is a human annotation and the shape count has to be independent of it."""

    n_table_refs: int
    joins: tuple[str, ...]
    aggregates: tuple[str, ...]
    setops: tuple[str, ...]
    nest_depth: int
    n_selects: int
    distinct: bool
    group: bool
    having: bool
    order: bool
    limit: bool
    case: bool
    arith: bool
    n_predicates: int
    unknown: int

    @property
    def table_bucket(self) -> str:
        """1 / 2 / 3+ table references. Bucketed because 4 tables against 5 is not a
        different solution strategy, and treating it as one inflates the shape count --
        which inflates the ceiling, which is the flattering direction."""
        return "1" if self.n_table_refs <= 1 else ("2" if self.n_table_refs == 2
                                                   else "3+")

    @property
    def predicate_bucket(self) -> str:
        return ("0" if self.n_predicates == 0
                else "1" if self.n_predicates == 1
                else "2" if self.n_predicates == 2
                else "3+")

    def coarse(self) -> str:
        """Structural family. Deliberately blind to which aggregate, which join type and
        how many predicates.

        No `join` marker: the table bucket already carries arity, and a separate marker
        would have split `FROM a, b WHERE a.id = b.id` from `FROM a JOIN b ON a.id =
        b.id` into two shapes on a pure syntax choice that leaves the semantics
        identical. Splitting on gold-query style inflates the shape count, which
        inflates the ceiling -- the flattering direction, so it is refused.
        """
        parts = [f"t{self.table_bucket}"]
        if self.aggregates:
            parts.append("agg")
        if self.group:
            parts.append("grp")
        if self.nest_depth:
            parts.append(f"nest{self.nest_depth}")
        if self.setops:
            parts.append("setop")
        return " ".join(parts)

    def fine(self) -> str:
        """Full skeleton: what a correct solution actually has to emit."""
        parts = [f"t{self.table_bucket}"]
        if self.joins:
            parts.append("join:" + ",".join(self.joins))
        if self.distinct:
            parts.append("dist")
        if self.aggregates:
            parts.append("agg:" + ",".join(self.aggregates))
        if self.group:
            parts.append("grp")
        if self.having:
            parts.append("hav")
        parts.append(f"pred:{self.predicate_bucket}")
        if self.nest_depth:
            parts.append(f"nest{self.nest_depth}")
        if self.setops:
            parts.append("setop:" + ",".join(self.setops))
        if self.order:
            parts.append("ord")
        if self.limit:
            parts.append("lim")
        if self.case:
            parts.append("case")
        if self.arith:
            parts.append("arith")
        return " ".join(parts)


def skeleton(sql: str) -> Skeleton:
    """Reduce one query to its clause skeleton.

    Single left-to-right pass with a paren-depth counter. `nest_depth` is the deepest
    paren level at which a `SELECT` appears, so a correlated subquery inside a WHERE and
    a derived table in a FROM both register as nesting, while a plain `COUNT(*)` does
    not -- depth alone would count every function call as nesting.
    """
    toks = tokenize(sql)
    depth = 0
    nest_depth = 0
    n_selects = 0
    joins: list[str] = []
    aggregates: set[str] = set()
    setops: list[str] = []
    distinct = group = having = order = limit = case = arith = False
    n_predicates = 0
    n_table_refs = 0
    # Paren depth at which the FROM list currently being scanned lives; None when not
    # inside one. Commas at that exact depth separate table references, while commas
    # anywhere else (argument lists, select lists) must not count.
    from_depth: int | None = None
    pending_join_mod: list[str] = []

    for i, t in enumerate(toks):
        prev = toks[i - 1] if i else ""
        if t == "(":
            depth += 1
            continue
        if t == ")":
            if from_depth is not None and depth <= from_depth:
                from_depth = None
            depth -= 1
            continue

        if t == "SELECT":
            n_selects += 1
            nest_depth = max(nest_depth, depth)
            from_depth = None
        elif t == "FROM":
            from_depth = depth
            n_table_refs += 1          # the first table reference of this FROM list
        elif t == "," and from_depth is not None and depth == from_depth:
            # An implicit comma join is an INNER join with different spelling. Recording
            # it as one keeps `fine()` blind to that spelling: the gold author's choice
            # between `FROM a, b` and `FROM a JOIN b` is not a different solution shape,
            # and counting it as one would overstate the shape inventory.
            n_table_refs += 1
            joins.append("INNER")
        elif t == "JOIN":
            mods = tuple(sorted(set(pending_join_mod))) or ("INNER",)
            joins.append("+".join(mods))
            n_table_refs += 1
            pending_join_mod = []
        elif t in _JOIN_MODIFIERS:
            pending_join_mod.append(t)
            continue
        elif t in AGGREGATES and i + 1 < len(toks) and toks[i + 1] == "(":
            aggregates.add(t)
        elif t in SETOPS:
            setops.append(t)
            from_depth = None
        elif t == "DISTINCT":
            distinct = True
        elif t == "GROUP":
            group = True
            from_depth = None
        elif t == "HAVING":
            having = True
            from_depth = None
        elif t == "ORDER":
            order = True
            from_depth = None
        elif t == "LIMIT":
            limit = True
            from_depth = None
        elif t == "CASE":
            case = True
        elif t in ("AND", "OR"):
            n_predicates += 1
        elif t in ("ON", "USING"):
            # A join condition is a predicate wherever it is written. `a JOIN b ON
            # a.id = b.id WHERE b.x > 5` and `a, b WHERE a.id = b.id AND b.x > 5` are
            # the same two conditions, and counting only WHERE/AND/OR scored them 1 and
            # 2 -- splitting one shape in two on the gold author's spelling.
            n_predicates += 1
        elif t == "WHERE":
            n_predicates += 1
            from_depth = None
        elif t in ("/", "%", "+"):
            arith = True
        elif t == "-" and prev in _VALUE_ENDERS:
            arith = True               # binary minus; a leading `-` is a sign, not maths
        elif t == "*" and prev in _VALUE_ENDERS:
            arith = True               # `SELECT *` and `COUNT(*)` have prev SELECT / (

        if t in _FROM_TERMINATORS and t != "JOIN" and t not in _JOIN_MODIFIERS:
            pending_join_mod = []

    return Skeleton(
        n_table_refs=n_table_refs,
        joins=tuple(sorted(joins)),
        aggregates=tuple(sorted(aggregates)),
        setops=tuple(sorted(set(setops))),
        nest_depth=nest_depth,
        n_selects=n_selects,
        distinct=distinct,
        group=group,
        having=having,
        order=order,
        limit=limit,
        case=case,
        arith=arith,
        n_predicates=n_predicates,
        unknown=sum(1 for t in toks if t == "UNKNOWN"),
    )


def shape(sql: str, granularity: str = "fine") -> str:
    """The shape string a selector and a power report group on."""
    if granularity not in ("fine", "coarse"):
        raise ValueError(f"granularity must be 'fine' or 'coarse', got {granularity!r}")
    sk = skeleton(sql)
    return sk.fine() if granularity == "fine" else sk.coarse()
