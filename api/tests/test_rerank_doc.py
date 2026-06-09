"""Unit tests for the reranker document builder.

The cross-encoder reads this string per candidate; it must carry the fresh
business signals (category, live price, stock, status) from Materialize.
"""

from src.routes.search import _build_rerank_doc, _build_rerank_doc_parts


def _item(name=None, cat=None, price=None, stock=None):
    return {"product_name": name, "category": cat, "live_price": price, "current_stock": stock}


def test_doc_includes_status_category_price_and_stock():
    doc = _build_rerank_doc(
        {"order_number": "FM-1", "order_status": "PICKING"},
        [_item("Carrots Organic", "Produce", 1.8, 5)],
    )
    assert doc.startswith("Order FM-1, status PICKING. Items:")
    assert "Carrots Organic (Produce, $1.80, in stock)" in doc


def test_out_of_stock_and_missing_price():
    doc = _build_rerank_doc({"order_number": "FM-2"}, [_item("Kale", "Produce", None, 0)])
    assert "Kale (Produce, out of stock)" in doc
    assert "$" not in doc  # no price rendered when missing


def test_falls_back_to_unit_price_when_no_live_price():
    doc = _build_rerank_doc({"order_number": "FM-4"}, [{"product_name": "Eggs", "category": "Dairy", "unit_price": 4.99, "current_stock": 2}])
    assert "Eggs (Dairy, $4.99, in stock)" in doc


def test_skips_items_without_a_name():
    doc = _build_rerank_doc(
        {"order_number": "FM-3"},
        [{"category": "Mystery"}, _item("Milk", "Dairy", 2.0, 3)],
    )
    assert "Milk (Dairy, $2.00, in stock)" in doc
    assert "Mystery" not in doc


def test_parts_split_mz_head_from_indexed_items():
    """The order head is the Materialize segment; items are the index segment.
    `doc` must be exactly the two concatenated (what the model scores)."""
    parts = _build_rerank_doc_parts(
        {"order_number": "FM-1", "order_status": "PICKING"},
        [_item("Carrots Organic", "Produce", 1.8, 5)],
    )
    assert parts["mz"] == "Order FM-1, status PICKING"
    assert parts["index"] == "Items: Carrots Organic (Produce, $1.80, in stock)"
    assert parts["doc"] == f"{parts['mz']}. {parts['index']}"
    # The string the model reads is unchanged by the split.
    assert parts["doc"] == _build_rerank_doc(
        {"order_number": "FM-1", "order_status": "PICKING"},
        [_item("Carrots Organic", "Produce", 1.8, 5)],
    )


def test_parts_index_empty_when_no_items():
    """With no line items there's no index segment, and doc is just the head."""
    parts = _build_rerank_doc_parts({"order_number": "FM-9", "order_status": "CREATED"}, [])
    assert parts["index"] == ""
    assert parts["doc"] == parts["mz"] == "Order FM-9, status CREATED"
