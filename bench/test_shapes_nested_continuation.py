"""Regression tests for FROM-context tracking across nested parens.

A `(` inside a FROM list (derived table) used to let the inner SELECT overwrite
`from_depth`, and the closing `)` cleared it outright: the outer FROM list's
comma joins were then silently dropped, splitting `x, b` from `x INNER JOIN b`
into two shapes on spelling alone -- the exact split the coarse/fine contract
refuses. These tests pin the restored behaviour plus the existing
spelling-equivalence and join-semantics contracts it must not disturb.

Offline: real `bench.shapes` only, no fixtures, mocks or external calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from bench.shapes import shape, skeleton  # noqa: E402


def test_derived_table_comma_join_matches_explicit_join():
    """`FROM (SELECT ...) x, b` and `FROM (SELECT ...) x INNER JOIN b` are the same
    semantics and must be one shape, with the comma still counted as a table
    reference + implicit INNER join even though a derived table sits inside the
    same FROM list."""
    comma = "SELECT * FROM (SELECT * FROM a) x, b WHERE x.id=b.id"
    explicit = "SELECT * FROM (SELECT * FROM a) x INNER JOIN b ON x.id=b.id"
    assert shape(comma) == shape(explicit)
    assert shape(comma, "coarse") == shape(explicit, "coarse")
    for sql in (comma, explicit):
        sk = skeleton(sql)
        assert sk.n_table_refs == 3
        assert sk.joins == ("INNER",)
        assert sk.n_predicates == 1
        assert sk.nest_depth == 1
        assert sk.n_selects == 2


def test_nested_function_commas_are_not_table_references():
    """Commas inside function argument lists -- including inside a derived table's
    SELECT list and inside a table function's own arguments -- are not FROM-list
    separators and must add zero table references."""
    fn = ("SELECT * FROM (SELECT COALESCE(a.id, 0) FROM a) x, b "
          "WHERE COALESCE(x.id, 0)=b.id")
    bare = "SELECT * FROM (SELECT a.id FROM a) x, b WHERE x.id=b.id"
    assert shape(fn) == shape(bare)
    assert shape(fn, "coarse") == shape(bare, "coarse")
    for sql in (fn, bare):
        sk = skeleton(sql)
        assert sk.n_table_refs == 3
        assert sk.joins == ("INNER",)
        assert sk.n_predicates == 1

    table_fn = skeleton("SELECT * FROM json_each(COALESCE(a, b), c) x")
    assert table_fn.n_table_refs == 1
    assert table_fn.joins == ()
    assert table_fn.n_predicates == 0
    assert table_fn.nest_depth == 0


def test_deeper_derived_table_restores_each_from_context():
    """Two levels of derived tables must each restore the enclosing FROM context,
    so every comma join in the chain is counted."""
    comma = ("SELECT * FROM (SELECT * FROM (SELECT * FROM a) x, b "
             "WHERE x.id=b.id) y, c WHERE y.id=c.id")
    explicit = ("SELECT * FROM (SELECT * FROM (SELECT * FROM a) x "
                "INNER JOIN b ON x.id=b.id) y INNER JOIN c ON y.id=c.id")
    assert shape(comma) == shape(explicit)
    assert shape(comma, "coarse") == shape(explicit, "coarse")
    for sql in (comma, explicit):
        sk = skeleton(sql)
        assert sk.n_table_refs == 5
        assert sk.joins == ("INNER", "INNER")
        assert sk.n_predicates == 2
        assert sk.nest_depth == 2
        assert sk.n_selects == 3


def test_flat_join_spelling_remains_equivalent():
    """The pre-existing flat case from test_bench.py: the fix must not disturb the
    comma-vs-INNER equivalence where no nesting is involved."""
    explicit = "SELECT a.n FROM a INNER JOIN b ON a.id = b.id WHERE b.x > 5"
    comma = "SELECT a.n FROM a, b WHERE a.id = b.id AND b.x > 5"
    assert shape(explicit) == shape(comma)
    assert shape(explicit, "coarse") == shape(comma, "coarse")
    for sql in (explicit, comma):
        sk = skeleton(sql)
        assert sk.n_table_refs == 2
        assert sk.joins == ("INNER",)
        assert sk.n_predicates == 2


def test_left_join_remains_distinct():
    """Join SEMANTICS still split a shape even where spelling does not: INNER and
    LEFT are different solution strategies (fine), one structural family
    (coarse)."""
    inner = "SELECT a.n FROM a INNER JOIN b ON a.id = b.id WHERE b.x > 5"
    left = "SELECT a.n FROM a LEFT JOIN b ON a.id = b.id WHERE b.x > 5"
    assert shape(inner) != shape(left)
    assert shape(inner, "coarse") == shape(left, "coarse")
    assert skeleton(inner).joins == ("INNER",)
    assert skeleton(left).joins == ("LEFT",)


def test_where_subquery_does_not_reopen_outer_from():
    """An EXISTS subquery in WHERE must not resurrect a FROM context: commas are
    gone anyway, but the outer table ref count and predicate count must survive
    the subquery's own SELECT/FROM intact."""
    sk = skeleton("SELECT * FROM a WHERE EXISTS (SELECT * FROM b) "
                  "AND COALESCE(a.id, 0)=1")
    assert sk.n_table_refs == 2
    assert sk.joins == ()
    assert sk.n_predicates == 2
    assert sk.nest_depth == 1
    assert sk.n_selects == 2
