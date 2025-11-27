"""Tests for agent tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx


class TestSearchOrders:
    """Tests for search_orders tool."""

    @pytest.mark.asyncio
    async def test_returns_matching_orders(self, mock_settings, sample_search_response):
        """Returns orders matching search query."""
        with patch("src.tools.tool_search_orders.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = sample_search_response
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_orders import search_orders

                # Call the underlying function directly
                results = await search_orders.ainvoke({"query": "Alex"})

                assert len(results) == 2
                assert results[0]["order_id"] == "order:FM-1001"
                assert results[0]["customer_name"] == "Alex Thompson"

    @pytest.mark.asyncio
    async def test_includes_status_filter(self, mock_settings):
        """Includes status filter in OpenSearch query."""
        with patch("src.tools.tool_search_orders.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = {"hits": {"hits": []}}
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_orders import search_orders

                await search_orders.ainvoke({
                    "query": "Alex",
                    "status": "OUT_FOR_DELIVERY"
                })

                # Check the posted query body
                call_args = mock_client.post.call_args
                query_body = call_args.kwargs["json"]
                must_clauses = query_body["query"]["bool"]["must"]
                assert any(
                    clause.get("term", {}).get("order_status") == "OUT_FOR_DELIVERY"
                    for clause in must_clauses
                )

    @pytest.mark.asyncio
    async def test_handles_http_error(self, mock_settings):
        """Returns error message on HTTP error."""
        with patch("src.tools.tool_search_orders.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_orders import search_orders

                results = await search_orders.ainvoke({"query": "Alex"})

                assert len(results) == 1
                assert "error" in results[0]

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self, mock_settings):
        """Respects limit parameter in query."""
        with patch("src.tools.tool_search_orders.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = {"hits": {"hits": []}}
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_orders import search_orders

                await search_orders.ainvoke({"query": "Alex", "limit": 5})

                call_args = mock_client.post.call_args
                query_body = call_args.kwargs["json"]
                assert query_body["size"] == 5


class TestFetchOrderContext:
    """Tests for fetch_order_context tool."""

    @pytest.mark.asyncio
    async def test_fetches_single_order(self, mock_settings, sample_order_detail):
        """Fetches details for single order."""
        with patch("src.tools.tool_fetch_order_context.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = sample_order_detail

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_fetch_order_context import fetch_order_context

                results = await fetch_order_context.ainvoke({
                    "order_ids": ["order:FM-1001"]
                })

                assert len(results) == 1
                assert results[0]["order_id"] == "order:FM-1001"

    @pytest.mark.asyncio
    async def test_fetches_multiple_orders(self, mock_settings, sample_order_detail):
        """Fetches details for multiple orders."""
        with patch("src.tools.tool_fetch_order_context.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = sample_order_detail

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_fetch_order_context import fetch_order_context

                results = await fetch_order_context.ainvoke({
                    "order_ids": ["order:FM-1001", "order:FM-1002"]
                })

                assert len(results) == 2

    @pytest.mark.asyncio
    async def test_handles_not_found(self, mock_settings):
        """Handles 404 not found response."""
        with patch("src.tools.tool_fetch_order_context.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 404

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_fetch_order_context import fetch_order_context

                results = await fetch_order_context.ainvoke({
                    "order_ids": ["order:NONEXISTENT"]
                })

                assert len(results) == 1
                assert "error" in results[0]
                assert "not found" in results[0]["error"].lower()

    @pytest.mark.asyncio
    async def test_handles_http_error(self, mock_settings):
        """Handles HTTP connection errors."""
        with patch("src.tools.tool_fetch_order_context.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_fetch_order_context import fetch_order_context

                results = await fetch_order_context.ainvoke({
                    "order_ids": ["order:FM-1001"]
                })

                assert len(results) == 1
                assert "error" in results[0]


class TestGetOntology:
    """Tests for get_ontology tool."""

    @pytest.mark.asyncio
    async def test_returns_simplified_schema(self, mock_settings, sample_ontology_schema):
        """Returns simplified ontology schema."""
        with patch("src.tools.tool_get_ontology.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = sample_ontology_schema
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_get_ontology import get_ontology

                result = await get_ontology.ainvoke({})

                assert "classes" in result
                assert "properties" in result
                assert len(result["classes"]) == 3
                assert result["classes"][0]["class_name"] == "Customer"

    @pytest.mark.asyncio
    async def test_simplifies_property_format(self, mock_settings, sample_ontology_schema):
        """Simplifies property format for agent."""
        with patch("src.tools.tool_get_ontology.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = sample_ontology_schema
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_get_ontology import get_ontology

                result = await get_ontology.ainvoke({})

                # Check property format is simplified
                customer_name_prop = next(
                    p for p in result["properties"] if p["prop_name"] == "customer_name"
                )
                assert "domain" in customer_name_prop
                assert "range" in customer_name_prop
                assert "required" in customer_name_prop

    @pytest.mark.asyncio
    async def test_handles_http_error(self, mock_settings):
        """Returns error on HTTP failure."""
        with patch("src.tools.tool_get_ontology.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_get_ontology import get_ontology

                result = await get_ontology.ainvoke({})

                assert "error" in result


class TestWriteTriples:
    """Tests for write_triples tool."""

    @pytest.mark.asyncio
    async def test_writes_single_triple(self, mock_settings, sample_created_triple):
        """Writes single triple successfully."""
        with patch("src.tools.tool_write_triples.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = sample_created_triple

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_write_triples import write_triples

                results = await write_triples.ainvoke({
                    "triples": [{
                        "subject_id": "order:FM-1001",
                        "predicate": "order_status",
                        "object_value": "DELIVERED",
                        "object_type": "string",
                    }]
                })

                assert len(results) == 1
                assert results[0]["success"] is True

    @pytest.mark.asyncio
    async def test_validates_required_fields(self, mock_settings):
        """Validates required fields in triple."""
        with patch("src.tools.tool_write_triples.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_write_triples import write_triples

                # Missing required fields
                results = await write_triples.ainvoke({
                    "triples": [{
                        "subject_id": "order:FM-1001",
                        # Missing predicate, object_value, object_type
                    }]
                })

                assert len(results) == 1
                assert "error" in results[0]
                assert "Missing required fields" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_handles_validation_failure(self, mock_settings):
        """Handles API validation failure."""
        with patch("src.tools.tool_write_triples.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.json.return_value = {
                    "detail": {
                        "errors": [{"error_type": "domain_violation", "message": "Wrong domain"}]
                    }
                }

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_write_triples import write_triples

                results = await write_triples.ainvoke({
                    "triples": [{
                        "subject_id": "order:FM-1001",
                        "predicate": "customer_name",  # Wrong domain
                        "object_value": "John",
                        "object_type": "string",
                    }]
                })

                assert len(results) == 1
                assert results[0]["success"] is False
                assert results[0]["error"] == "Validation failed"

    @pytest.mark.asyncio
    async def test_writes_multiple_triples(self, mock_settings, sample_created_triple):
        """Writes multiple triples."""
        with patch("src.tools.tool_write_triples.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = sample_created_triple

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_write_triples import write_triples

                results = await write_triples.ainvoke({
                    "triples": [
                        {
                            "subject_id": "order:FM-1001",
                            "predicate": "order_status",
                            "object_value": "DELIVERED",
                            "object_type": "string",
                        },
                        {
                            "subject_id": "order:FM-1002",
                            "predicate": "order_status",
                            "object_value": "DELIVERED",
                            "object_type": "string",
                        },
                    ]
                })

                assert len(results) == 2
                assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_handles_http_error(self, mock_settings):
        """Handles HTTP connection errors."""
        with patch("src.tools.tool_write_triples.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_write_triples import write_triples

                results = await write_triples.ainvoke({
                    "triples": [{
                        "subject_id": "order:FM-1001",
                        "predicate": "order_status",
                        "object_value": "DELIVERED",
                        "object_type": "string",
                    }]
                })

                assert len(results) == 1
                assert results[0]["success"] is False
                assert "error" in results[0]

    @pytest.mark.asyncio
    async def test_passes_validate_param(self, mock_settings, sample_created_triple):
        """Passes validate parameter to API."""
        with patch("src.tools.tool_write_triples.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = sample_created_triple

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_write_triples import write_triples

                await write_triples.ainvoke({
                    "triples": [{
                        "subject_id": "test:123",
                        "predicate": "any_prop",
                        "object_value": "Value",
                        "object_type": "string",
                    }],
                    "validate": False,
                })

                call_args = mock_client.post.call_args
                assert call_args.kwargs["params"]["validate"] is False


class TestCreateOrder:
    """Tests for create_order tool."""

    @pytest.mark.asyncio
    async def test_creates_order_with_correct_predicates(self, mock_settings):
        """Creates order with correct ontology predicates."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock inventory response
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "inventory_id": "inv:001",
                                    "store_id": "store:BK-01",
                                    "product_id": "product:milk-1L",
                                    "stock_level": 50,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Mock order creation response
                mock_order_response = MagicMock()
                mock_order_response.status_code = 201
                mock_order_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                # First call is inventory search, second is order creation
                mock_client.post = AsyncMock(side_effect=[mock_inventory_response, mock_order_response])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                result = await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "store_id": "store:BK-01",
                    "items": [
                        {
                            "product_id": "product:milk-1L",
                            "quantity": 2,
                            "unit_price": 4.99,
                            "is_perishable": True,
                        }
                    ],
                })

                assert result["success"] is True
                assert result["order_status"] == "CREATED"
                assert result["customer_id"] == "customer:test123"

                # Verify the order creation API call (second call)
                assert mock_client.post.call_count == 2
                call_args = mock_client.post.call_args_list[1]
                triples = call_args.kwargs["json"]

                # Check order predicates
                predicates = {t["predicate"] for t in triples}
                assert "order_status" in predicates
                assert "placed_by" in predicates
                assert "order_store" in predicates
                assert "order_number" in predicates

                # Check line item predicates match ontology
                assert "line_of_order" in predicates
                assert "line_product" in predicates
                assert "quantity" in predicates
                assert "order_line_unit_price" in predicates
                assert "line_amount" in predicates
                assert "perishable_flag" in predicates

    @pytest.mark.asyncio
    async def test_order_always_starts_in_created_state(self, mock_settings):
        """Ensures order_status is always CREATED initially."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock inventory response
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "inventory_id": "inv:001",
                                    "store_id": "store:BK-01",
                                    "product_id": "product:milk",
                                    "stock_level": 50,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Mock order creation response
                mock_order_response = MagicMock()
                mock_order_response.status_code = 201
                mock_order_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=[mock_inventory_response, mock_order_response])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                result = await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "items": [
                        {"product_id": "product:milk", "quantity": 1, "unit_price": 5.0}
                    ],
                })

                # Check return value
                assert result["order_status"] == "CREATED"

                # Check the triple sent to API (second call)
                call_args = mock_client.post.call_args_list[1]
                triples = call_args.kwargs["json"]
                status_triple = next(t for t in triples if t["predicate"] == "order_status")
                assert status_triple["object_value"] == "CREATED"

    @pytest.mark.asyncio
    async def test_calculates_line_amounts(self, mock_settings):
        """Calculates line_amount for each item."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock inventory response
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "inventory_id": "inv:001",
                                    "store_id": "store:BK-01",
                                    "product_id": "product:milk",
                                    "stock_level": 50,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Mock order creation response
                mock_order_response = MagicMock()
                mock_order_response.status_code = 201
                mock_order_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=[mock_inventory_response, mock_order_response])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "items": [
                        {"product_id": "product:milk", "quantity": 2, "unit_price": 4.99}
                    ],
                })

                call_args = mock_client.post.call_args_list[1]
                triples = call_args.kwargs["json"]

                # Find line_amount triple
                line_amount_triple = next(t for t in triples if t["predicate"] == "line_amount")
                assert line_amount_triple["object_value"] == "9.98"  # 2 * 4.99

    @pytest.mark.asyncio
    async def test_handles_api_error(self, mock_settings):
        """Handles API errors gracefully."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                result = await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "items": [
                        {"product_id": "product:milk", "quantity": 1, "unit_price": 5.0}
                    ],
                })

                assert result["success"] is False
                assert "error" in result

    @pytest.mark.asyncio
    async def test_filters_unavailable_items(self, mock_settings):
        """Filters out items not in store inventory."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock inventory response - only milk is available
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "inventory_id": "inv:001",
                                    "store_id": "store:BK-01",
                                    "product_id": "product:milk",
                                    "stock_level": 50,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Mock order creation response
                mock_order_response = MagicMock()
                mock_order_response.status_code = 201
                mock_order_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=[mock_inventory_response, mock_order_response])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                result = await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "store_id": "store:BK-01",
                    "items": [
                        {"product_id": "product:milk", "quantity": 1, "unit_price": 5.0},
                        {"product_id": "product:bananas", "quantity": 2, "unit_price": 2.0},
                    ],
                })

                # Order should succeed with only milk
                assert result["success"] is True
                assert result["item_count"] == 1
                assert "skipped_items" in result
                assert len(result["skipped_items"]) == 1
                assert result["skipped_items"][0]["product_id"] == "product:bananas"

    @pytest.mark.asyncio
    async def test_adjusts_quantity_for_insufficient_stock(self, mock_settings):
        """Adjusts quantity when stock is insufficient."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock inventory response - only 5 units available
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "inventory_id": "inv:001",
                                    "store_id": "store:BK-01",
                                    "product_id": "product:milk",
                                    "stock_level": 5,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Mock order creation response
                mock_order_response = MagicMock()
                mock_order_response.status_code = 201
                mock_order_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=[mock_inventory_response, mock_order_response])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                result = await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "store_id": "store:BK-01",
                    "items": [
                        {"product_id": "product:milk", "quantity": 10, "unit_price": 5.0},
                    ],
                })

                # Order should succeed with adjusted quantity
                assert result["success"] is True
                assert "adjusted_quantities" in result
                assert len(result["adjusted_quantities"]) == 1
                assert result["adjusted_quantities"][0]["requested"] == 10
                assert result["adjusted_quantities"][0]["available"] == 5

                # Check that order was created with 5 units, not 10
                call_args = mock_client.post.call_args_list[1]
                triples = call_args.kwargs["json"]
                quantity_triple = next(t for t in triples if t["predicate"] == "quantity")
                assert quantity_triple["object_value"] == "5"

    @pytest.mark.asyncio
    async def test_returns_error_when_no_items_available(self, mock_settings):
        """Returns error when no requested items are in stock."""
        with patch("src.tools.tool_create_order.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock empty inventory response
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {"hits": []}
                }
                mock_inventory_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_order import create_order

                result = await create_order.ainvoke({
                    "customer_id": "customer:test123",
                    "store_id": "store:BK-01",
                    "items": [
                        {"product_id": "product:bananas", "quantity": 2, "unit_price": 2.0},
                    ],
                })

                # Should return error
                assert result["success"] is False
                assert "No requested items are available" in result["error"]
                assert "available_products" in result


class TestSearchInventory:
    """Tests for search_inventory tool."""

    @pytest.mark.asyncio
    async def test_searches_inventory_by_product_name(self, mock_settings):
        """Returns products matching search query by name."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock inventory search response
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "product_id": "product:milk-1L",
                                    "stock_level": 45,
                                    "replenishment_eta": None,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Mock product detail response
                mock_product_response = MagicMock()
                mock_product_response.status_code = 200
                mock_product_response.json.return_value = {
                    "triples": [
                        {"predicate": "product_name", "object_value": "Organic Whole Milk 1 Gallon"},
                        {"predicate": "category", "object_value": "Dairy"},
                        {"predicate": "unit_price", "object_value": "5.99"},
                        {"predicate": "perishable", "object_value": "true"},
                    ]
                }

                mock_client = AsyncMock()
                # First call is inventory search, second is product detail
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.get = AsyncMock(return_value=mock_product_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "milk",
                    "store_id": "store:BK-01",
                })

                assert len(results) == 1
                assert results[0]["product_id"] == "product:milk-1L"
                assert results[0]["product_name"] == "Organic Whole Milk 1 Gallon"
                assert results[0]["category"] == "Dairy"
                assert results[0]["unit_price"] == 5.99
                assert results[0]["quantity_available"] == 45
                assert results[0]["is_perishable"] is True

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, mock_settings):
        """Queries inventory for specified store only."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {"hits": {"hits": []}}
                mock_inventory_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                await search_inventory.ainvoke({
                    "query": "milk",
                    "store_id": "store:MAN-01",
                })

                # Verify store_id filter in inventory query
                call_args = mock_client.post.call_args
                query_body = call_args.kwargs["json"]
                must_clauses = query_body["query"]["bool"]["must"]
                assert any(
                    clause.get("term", {}).get("store_id") == "store:MAN-01"
                    for clause in must_clauses
                )

    @pytest.mark.asyncio
    async def test_searches_by_category(self, mock_settings):
        """Matches products by category."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "product_id": "product:chicken-breast",
                                    "stock_level": 20,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                mock_product_response = MagicMock()
                mock_product_response.status_code = 200
                mock_product_response.json.return_value = {
                    "triples": [
                        {"predicate": "product_name", "object_value": "Organic Chicken Breast"},
                        {"predicate": "category", "object_value": "Meat"},
                        {"predicate": "unit_price", "object_value": "8.99"},
                    ]
                }

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.get = AsyncMock(return_value=mock_product_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "meat",
                    "store_id": "store:BK-01",
                })

                assert len(results) == 1
                assert results[0]["category"] == "Meat"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_inventory(self, mock_settings):
        """Returns empty list when store has no inventory."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {"hits": {"hits": []}}
                mock_inventory_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "milk",
                    "store_id": "store:BK-01",
                })

                assert len(results) == 0

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self, mock_settings):
        """Respects limit parameter for results."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock 5 products in inventory
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {"_source": {"product_id": f"product:item{i}", "stock_level": 10}}
                            for i in range(5)
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                mock_product_response = MagicMock()
                mock_product_response.status_code = 200
                mock_product_response.json.return_value = {
                    "triples": [
                        {"predicate": "product_name", "object_value": "Test Product"},
                        {"predicate": "category", "object_value": "Test"},
                        {"predicate": "unit_price", "object_value": "1.99"},
                    ]
                }

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.get = AsyncMock(return_value=mock_product_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "test",
                    "limit": 3,
                })

                # Should only return 3 results even though 5 match
                assert len(results) == 3

    @pytest.mark.asyncio
    async def test_handles_missing_product_details(self, mock_settings):
        """Handles missing product details gracefully."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "product_id": "product:unknown",
                                    "stock_level": 10,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Product detail request returns 404
                mock_product_response = MagicMock()
                mock_product_response.status_code = 404

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Not found"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "unknown",
                })

                # Should still return result with product_id as name
                assert len(results) == 1
                assert results[0]["product_id"] == "product:unknown"
                assert results[0]["product_name"] == "product:unknown"
                assert results[0]["category"] == "Unknown"

    @pytest.mark.asyncio
    async def test_adds_warning_for_missing_price(self, mock_settings):
        """Adds warning when product price is missing."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "product_id": "product:no-price",
                                    "stock_level": 10,
                                }
                            }
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                # Product detail without price
                mock_product_response = MagicMock()
                mock_product_response.status_code = 200
                mock_product_response.json.return_value = {
                    "triples": [
                        {"predicate": "product_name", "object_value": "Mystery Product"},
                        {"predicate": "category", "object_value": "Unknown"},
                    ]
                }

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.get = AsyncMock(return_value=mock_product_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "mystery",
                })

                assert len(results) == 1
                assert results[0]["unit_price"] is None
                assert "warning" in results[0]
                assert "Price information unavailable" in results[0]["warning"]

    @pytest.mark.asyncio
    async def test_handles_http_error(self, mock_settings):
        """Returns error on HTTP failure."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                results = await search_inventory.ainvoke({
                    "query": "milk",
                })

                assert len(results) == 1
                assert "error" in results[0]

    @pytest.mark.asyncio
    async def test_fetches_products_in_parallel(self, mock_settings):
        """Fetches all product details in parallel, not sequentially."""
        with patch("src.tools.tool_search_inventory.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                # Mock 3 products in inventory
                mock_inventory_response = MagicMock()
                mock_inventory_response.json.return_value = {
                    "hits": {
                        "hits": [
                            {"_source": {"product_id": f"product:item{i}", "stock_level": 10}}
                            for i in range(3)
                        ]
                    }
                }
                mock_inventory_response.raise_for_status = MagicMock()

                mock_product_response = MagicMock()
                mock_product_response.status_code = 200
                mock_product_response.json.return_value = {
                    "triples": [
                        {"predicate": "product_name", "object_value": "Test Product"},
                        {"predicate": "category", "object_value": "Test"},
                        {"predicate": "unit_price", "object_value": "1.99"},
                    ]
                }

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_inventory_response)
                mock_client.get = AsyncMock(return_value=mock_product_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_search_inventory import search_inventory

                await search_inventory.ainvoke({
                    "query": "test",
                })

                # Should have made exactly 3 GET calls (one per product)
                # The fact that all succeed means asyncio.gather worked
                assert mock_client.get.call_count == 3

                # Verify all 3 product IDs were fetched
                call_urls = [call.args[0] for call in mock_client.get.call_args_list]
                assert any("product:item0" in url for url in call_urls)
                assert any("product:item1" in url for url in call_urls)
                assert any("product:item2" in url for url in call_urls)


class TestCreateCustomer:
    """Tests for create_customer tool."""

    @pytest.mark.asyncio
    async def test_creates_customer_with_all_fields(self, mock_settings):
        """Creates customer with name, email, address, and home_store."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                result = await create_customer.ainvoke({
                    "name": "John Doe",
                    "email": "john@example.com",
                    "address": "123 Main St, Brooklyn, NY",
                    "home_store_id": "store:BK-01",
                })

                assert result["success"] is True
                assert result["name"] == "John Doe"
                assert result["email"] == "john@example.com"
                assert result["address"] == "123 Main St, Brooklyn, NY"
                assert result["home_store_id"] == "store:BK-01"
                assert "customer_id" in result
                assert result["customer_id"].startswith("customer:")

                # Verify the triples posted
                call_args = mock_client.post.call_args
                triples = call_args.kwargs["json"]

                # Should have 4 triples: name, email, address, home_store
                assert len(triples) == 4

                predicates = {t["predicate"] for t in triples}
                assert "customer_name" in predicates
                assert "customer_email" in predicates
                assert "customer_address" in predicates
                assert "home_store" in predicates

    @pytest.mark.asyncio
    async def test_creates_customer_with_only_required_fields(self, mock_settings):
        """Creates customer with only name (required)."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                result = await create_customer.ainvoke({
                    "name": "Jane Smith",
                })

                assert result["success"] is True
                assert result["name"] == "Jane Smith"
                assert result["email"] is None
                assert result["address"] is None
                assert result["home_store_id"] == "store:BK-01"  # default

                # Verify the triples posted
                call_args = mock_client.post.call_args
                triples = call_args.kwargs["json"]

                # Should have 2 triples: name and home_store (defaults)
                assert len(triples) == 2

                predicates = {t["predicate"] for t in triples}
                assert "customer_name" in predicates
                assert "home_store" in predicates
                assert "customer_email" not in predicates
                assert "customer_address" not in predicates

    @pytest.mark.asyncio
    async def test_generates_unique_customer_id(self, mock_settings):
        """Generates unique customer ID for each call."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                result1 = await create_customer.ainvoke({"name": "Customer 1"})
                result2 = await create_customer.ainvoke({"name": "Customer 2"})

                assert result1["customer_id"] != result2["customer_id"]
                assert result1["customer_id"].startswith("customer:")
                assert result2["customer_id"].startswith("customer:")

    @pytest.mark.asyncio
    async def test_uses_correct_ontology_predicates(self, mock_settings):
        """Uses correct ontology predicates for customer."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                await create_customer.ainvoke({
                    "name": "Test Customer",
                    "email": "test@example.com",
                    "address": "123 Test St",
                })

                call_args = mock_client.post.call_args
                triples = call_args.kwargs["json"]

                # Verify correct object_type for each predicate
                for triple in triples:
                    if triple["predicate"] == "home_store":
                        assert triple["object_type"] == "entity_ref"
                    else:
                        assert triple["object_type"] == "string"

    @pytest.mark.asyncio
    async def test_enables_validation(self, mock_settings):
        """Enables ontology validation when creating customer."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                await create_customer.ainvoke({"name": "Test"})

                # Verify validate=True in params
                call_args = mock_client.post.call_args
                assert call_args.kwargs["params"]["validate"] is True

    @pytest.mark.asyncio
    async def test_handles_http_error(self, mock_settings):
        """Handles HTTP errors gracefully."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(
                    side_effect=httpx.HTTPError("Connection failed")
                )
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                result = await create_customer.ainvoke({"name": "Test"})

                assert result["success"] is False
                assert "error" in result
                assert "Failed to create customer" in result["error"]

    @pytest.mark.asyncio
    async def test_handles_validation_error(self, mock_settings):
        """Handles API validation errors."""
        with patch("src.tools.tool_create_customer.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Validation failed",
                        request=MagicMock(),
                        response=mock_response,
                    )
                )

                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                from src.tools.tool_create_customer import create_customer

                result = await create_customer.ainvoke({"name": "Test"})

                assert result["success"] is False
                assert "error" in result
