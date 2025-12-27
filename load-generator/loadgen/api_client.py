"""FreshMart API client wrapper for load generation."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class FreshMartAPIClient:
    """Client for interacting with FreshMart API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Initialize API client.

        Args:
            base_url: Base URL for FreshMart API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for transient failures
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            follow_redirects=True,
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    async def _retry_request(self, method: str, *args, **kwargs) -> httpx.Response:
        """Execute HTTP request with retry logic for transient failures.

        Args:
            method: HTTP method (get, post, put, delete)
            *args: Positional arguments for the request
            **kwargs: Keyword arguments for the request

        Returns:
            HTTP response

        Raises:
            httpx.HTTPError: If all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                # Get the appropriate method from the client
                request_func = getattr(self.client, method)
                response = await request_func(*args, **kwargs)
                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                # Retry on network/timeout errors
                last_exception = e
                if attempt < self.max_retries - 1:
                    backoff = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.debug(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {backoff}s: {e}"
                    )
                    await asyncio.sleep(backoff)
                    continue
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                    raise

            except httpx.HTTPStatusError as e:
                # Retry on 5xx server errors, but not on 4xx client errors
                if e.response.status_code >= 500:
                    last_exception = e
                    if attempt < self.max_retries - 1:
                        backoff = 2 ** attempt
                        logger.debug(
                            f"Server error {e.response.status_code} "
                            f"(attempt {attempt + 1}/{self.max_retries}), "
                            f"retrying in {backoff}s"
                        )
                        await asyncio.sleep(backoff)
                        continue
                # Don't retry on client errors (4xx)
                raise

        # This should not be reached, but just in case
        if last_exception:
            raise last_exception

    async def health_check(self) -> dict[str, Any]:
        """Check API health.

        Returns:
            Health status response

        Raises:
            httpx.HTTPError: If health check fails
        """
        response = await self._retry_request("get", "/health")
        return response.json()

    async def get_stores(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get list of stores.

        Args:
            limit: Maximum number of stores to return

        Returns:
            List of store objects
        """
        response = await self._retry_request("get", "/freshmart/stores", params={"limit": limit})
        return response.json()

    async def get_customers(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get list of customers.

        Args:
            limit: Maximum number of customers to return

        Returns:
            List of customer objects
        """
        response = await self._retry_request("get", "/freshmart/customers", params={"limit": limit})
        return response.json()

    async def get_products(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Get list of products.

        Args:
            limit: Maximum number of products to return

        Returns:
            List of product objects
        """
        response = await self._retry_request("get", "/freshmart/products", params={"limit": limit})
        return response.json()

    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get list of orders.

        Args:
            status: Filter by order status
            limit: Maximum number of orders to return
            offset: Offset for pagination

        Returns:
            List of order objects
        """
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await self._retry_request("get", "/freshmart/orders", params=params)
        return response.json()

    async def create_triples_batch(
        self, triples: list[dict[str, Any]], validate: bool = True
    ) -> dict[str, Any]:
        """Create multiple triples in a batch.

        Args:
            triples: List of triple objects to create
            validate: Whether to validate against ontology

        Returns:
            Batch creation response

        Raises:
            httpx.HTTPError: If creation fails
        """
        response = await self._retry_request(
            "post",
            "/triples/batch",
            json=triples,
            params={"validate": validate},
        )
        return response.json()

    async def update_triples_batch(
        self, updates: list[dict[str, Any]], validate: bool = True
    ) -> dict[str, Any]:
        """Update multiple triples in a batch.

        Args:
            updates: List of triple updates
            validate: Whether to validate against ontology

        Returns:
            Batch update response

        Raises:
            httpx.HTTPError: If update fails
        """
        response = await self._retry_request(
            "put",
            "/triples/batch",
            json=updates,
            params={"validate": validate},
        )
        return response.json()

    async def create_customer(
        self,
        customer_id: str,
        name: str,
        email: str,
        address: str,
        home_store_id: str,
    ) -> dict[str, Any]:
        """Create a new customer.

        Args:
            customer_id: Customer ID (e.g., "customer:12345")
            name: Customer name
            email: Customer email
            address: Customer address
            home_store_id: Home store ID

        Returns:
            Creation response
        """
        triples = [
            {
                "subject_id": customer_id,
                "predicate": "customer_name",
                "object_value": name,
                "object_type": "string",
            },
            {
                "subject_id": customer_id,
                "predicate": "customer_email",
                "object_value": email,
                "object_type": "string",
            },
            {
                "subject_id": customer_id,
                "predicate": "customer_address",
                "object_value": address,
                "object_type": "string",
            },
            {
                "subject_id": customer_id,
                "predicate": "home_store",
                "object_value": home_store_id,
                "object_type": "entity_ref",
            },
        ]
        return await self.create_triples_batch(triples)

    async def create_order(
        self,
        order_id: str,
        customer_id: str,
        store_id: str,
        line_items: list[dict[str, Any]],
        delivery_window_start: datetime,
        delivery_window_end: datetime,
    ) -> dict[str, Any]:
        """Create a new order with line items.

        Args:
            order_id: Order ID (e.g., "order:FM-12345")
            customer_id: Customer ID
            store_id: Store ID
            line_items: List of line items with product_id, quantity, price
            delivery_window_start: Delivery window start time
            delivery_window_end: Delivery window end time

        Returns:
            Creation response
        """
        # Calculate total
        total = sum(item["quantity"] * item["price"] for item in line_items)
        now = datetime.now(timezone.utc).isoformat()

        # Create order triples
        order_triples = [
            {
                "subject_id": order_id,
                "predicate": "order_number",
                "object_value": order_id.split(":")[-1],
                "object_type": "string",
            },
            {
                "subject_id": order_id,
                "predicate": "order_status",
                "object_value": "CREATED",
                "object_type": "string",
            },
            {
                "subject_id": order_id,
                "predicate": "order_created_at",
                "object_value": now,
                "object_type": "timestamp",
            },
            {
                "subject_id": order_id,
                "predicate": "placed_by",
                "object_value": customer_id,
                "object_type": "entity_ref",
            },
            {
                "subject_id": order_id,
                "predicate": "order_store",
                "object_value": store_id,
                "object_type": "entity_ref",
            },
            {
                "subject_id": order_id,
                "predicate": "delivery_window_start",
                "object_value": delivery_window_start.isoformat(),
                "object_type": "timestamp",
            },
            {
                "subject_id": order_id,
                "predicate": "delivery_window_end",
                "object_value": delivery_window_end.isoformat(),
                "object_type": "timestamp",
            },
            {
                "subject_id": order_id,
                "predicate": "order_total_amount",
                "object_value": str(total),
                "object_type": "float",
            },
        ]

        # Create line item triples
        for idx, item in enumerate(line_items):
            line_id = f"orderline:{order_id.split(':')[-1]}-{idx+1}"
            line_amount = item["quantity"] * item["price"]

            order_triples.extend(
                [
                    {
                        "subject_id": line_id,
                        "predicate": "line_of_order",
                        "object_value": order_id,
                        "object_type": "entity_ref",
                    },
                    {
                        "subject_id": line_id,
                        "predicate": "line_product",
                        "object_value": item["product_id"],
                        "object_type": "entity_ref",
                    },
                    {
                        "subject_id": line_id,
                        "predicate": "quantity",
                        "object_value": str(item["quantity"]),
                        "object_type": "int",
                    },
                    {
                        "subject_id": line_id,
                        "predicate": "order_line_unit_price",
                        "object_value": str(item["price"]),
                        "object_type": "float",
                    },
                    {
                        "subject_id": line_id,
                        "predicate": "line_amount",
                        "object_value": str(line_amount),
                        "object_type": "float",
                    },
                    {
                        "subject_id": line_id,
                        "predicate": "line_sequence",
                        "object_value": str(idx + 1),
                        "object_type": "int",
                    },
                ]
            )

        return await self.create_triples_batch(order_triples)

    async def update_order_status(
        self, order_id: str, new_status: str
    ) -> dict[str, Any]:
        """Update order status.

        Args:
            order_id: Order ID
            new_status: New status value

        Returns:
            Update response
        """
        updates = [
            {
                "subject_id": order_id,
                "predicate": "order_status",
                "object_value": new_status,
                "object_type": "string",
            }
        ]
        return await self.update_triples_batch(updates)

    async def update_inventory(
        self, store_id: str, product_id: str, new_quantity: int
    ) -> dict[str, Any]:
        """Update inventory quantity for a product at a store.

        Args:
            store_id: Store ID
            product_id: Product ID
            new_quantity: New quantity value

        Returns:
            Update response
        """
        # Inventory is tracked as triples with store+product as subject
        inventory_id = f"inventory:{store_id.split(':')[-1]}-{product_id.split(':')[-1]}"

        updates = [
            {
                "subject_id": inventory_id,
                "predicate": "stock_level",
                "object_value": str(new_quantity),
                "object_type": "int",
            }
        ]
        return await self.update_triples_batch(updates)

    # =========================================================================
    # Courier Dispatch (CQRS Queries)
    # =========================================================================

    async def get_available_couriers(
        self, store_id: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get available couriers that can be assigned to orders.

        Args:
            store_id: Optional filter by home store
            limit: Maximum number of results

        Returns:
            List of available courier objects
        """
        params = {"limit": limit}
        if store_id:
            params["store_id"] = store_id

        response = await self._retry_request(
            "get", "/freshmart/dispatch/couriers/available", params=params
        )
        return response.json()

    async def get_orders_awaiting_courier(
        self, store_id: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get orders awaiting courier assignment.

        Args:
            store_id: Optional filter by store
            limit: Maximum number of results

        Returns:
            List of orders waiting for courier (FIFO)
        """
        params = {"limit": limit}
        if store_id:
            params["store_id"] = store_id

        response = await self._retry_request(
            "get", "/freshmart/dispatch/orders/awaiting-courier", params=params
        )
        return response.json()

    async def get_tasks_ready_to_advance(
        self, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get delivery tasks where the timer has elapsed.

        Args:
            limit: Maximum number of results

        Returns:
            List of tasks ready to advance to next status
        """
        response = await self._retry_request(
            "get", "/freshmart/dispatch/tasks/ready-to-advance", params={"limit": limit}
        )
        return response.json()

    async def get_store_courier_metrics(
        self, store_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Get courier metrics per store.

        Args:
            store_id: Optional filter by store

        Returns:
            List of store courier metrics
        """
        params = {}
        if store_id:
            params["store_id"] = store_id

        response = await self._retry_request(
            "get", "/freshmart/dispatch/metrics", params=params
        )
        return response.json()
