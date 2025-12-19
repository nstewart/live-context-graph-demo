"""Get store health metrics for operational decision-making."""

import asyncpg
from typing import Optional
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def get_store_health(
    view: str = "summary",
    store_id: Optional[str] = None,
    category: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """Get real-time store operational health metrics and recommendations.

    This tool provides situational awareness of store operations by querying
    real-time metrics from Materialize. Use it to understand operational state
    before making decisions or providing recommendations to staff.

    Args:
        view: Type of health check to perform (default: "summary")
            - "summary": High-level overview of all metrics (capacity, inventory risk, pricing yield)
            - "capacity": Per-store utilization and headroom analysis
            - "inventory_risk": Products at risk of stockout with pending orders
            - "quick_check": Fast single-store health check (requires store_id)

        store_id: Filter to specific store (e.g., "store:BK-01")
            - Required for "quick_check" view
            - Optional for other views to filter results

        category: Filter inventory risk by product category (e.g., "Produce", "Dairy")
            - Only applies to "inventory_risk" view

        risk_level: Filter inventory by risk level (CRITICAL, HIGH, MEDIUM, LOW)
            - Only applies to "inventory_risk" view
            - Default: shows CRITICAL and HIGH only for summary

        limit: Maximum number of items to return (default: 10)
            - Applies to "capacity" and "inventory_risk" views

    Returns:
        dict: Health metrics with recommendations

    Examples:
        # Get overall health before dinner rush
        get_store_health(view="summary")

        # Check specific store capacity before creating order
        get_store_health(view="quick_check", store_id="store:BK-01")

        # Find all critical inventory issues
        get_store_health(view="inventory_risk", risk_level="CRITICAL")

        # Check Brooklyn store's high-risk produce items
        get_store_health(view="inventory_risk", store_id="store:BK-01", category="Produce", risk_level="HIGH")
    """
    settings = get_settings()

    try:
        # Connect to Materialize
        conn = await asyncpg.connect(
            host=settings.mz_host,
            port=settings.mz_port,
            user=settings.mz_user,
            password=settings.mz_password,
            database=settings.mz_database,
        )

        try:
            # CRITICAL: Set cluster to serving for indexed queries
            await conn.execute("SET CLUSTER = serving")

            # Route to appropriate view handler
            if view == "summary":
                return await _get_summary(conn)
            elif view == "capacity":
                return await _get_capacity(conn, store_id, limit)
            elif view == "inventory_risk":
                return await _get_inventory_risk(conn, store_id, category, risk_level, limit)
            elif view == "quick_check":
                if not store_id:
                    return {
                        "view": "quick_check",
                        "error": "store_id is required for quick_check view",
                        "recommendations": ["Please specify a store_id parameter"],
                    }
                return await _get_quick_check(conn, store_id)
            else:
                return {
                    "view": view,
                    "error": f"Unknown view type: {view}",
                    "valid_views": ["summary", "capacity", "inventory_risk", "quick_check"],
                    "recommendations": ["Use 'summary' for overall health overview"],
                }

        finally:
            await conn.close()

    except Exception as e:
        return {
            "view": view,
            "error": f"Health check failed: {str(e)}",
            "recommendations": [
                "Unable to access health metrics - please retry",
                "If problem persists, check system status",
            ],
        }


async def _get_summary(conn: asyncpg.Connection) -> dict:
    """Get high-level overview of all three metrics."""

    # Query 1: Capacity health summary
    capacity_summary = await conn.fetch("""
        SELECT
            health_status,
            COUNT(*) as store_count,
            ROUND(AVG(current_utilization_pct), 1) as avg_utilization_pct
        FROM store_capacity_health_mv
        GROUP BY health_status
        ORDER BY
            CASE health_status
                WHEN 'CRITICAL' THEN 1
                WHEN 'STRAINED' THEN 2
                WHEN 'HEALTHY' THEN 3
                WHEN 'UNDERUTILIZED' THEN 4
            END
    """)

    # Query 2: Inventory risk summary
    risk_summary = await conn.fetch("""
        SELECT
            risk_level,
            COUNT(*) as item_count,
            ROUND(SUM(revenue_at_risk)::numeric, 2) as total_revenue_at_risk
        FROM inventory_risk_mv
        WHERE risk_level IN ('CRITICAL', 'HIGH')
        GROUP BY risk_level
        ORDER BY
            CASE risk_level
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
            END
    """)

    # Query 3: Pricing yield summary
    pricing_summary = await conn.fetchrow("""
        SELECT
            ROUND(SUM(price_premium)::numeric, 2) as total_premium,
            ROUND(SUM(order_price * quantity)::numeric, 2) as total_revenue,
            COUNT(DISTINCT order_id) as delivered_orders
        FROM pricing_yield_mv
    """)

    # Build response
    capacity_data = {row['health_status']: dict(row) for row in capacity_summary}
    risk_data = {row['risk_level']: dict(row) for row in risk_summary}

    # Calculate totals
    total_stores = sum(c['store_count'] for c in capacity_data.values())
    critical_stores = capacity_data.get('CRITICAL', {}).get('store_count', 0)
    strained_stores = capacity_data.get('STRAINED', {}).get('store_count', 0)

    critical_items = risk_data.get('CRITICAL', {}).get('item_count', 0)
    high_risk_items = risk_data.get('HIGH', {}).get('item_count', 0)
    total_revenue_at_risk = sum(float(r.get('total_revenue_at_risk', 0)) for r in risk_data.values())

    total_premium = float(pricing_summary['total_premium'] or 0)
    total_revenue = float(pricing_summary['total_revenue'] or 0)
    pricing_yield_pct = (total_premium / total_revenue * 100) if total_revenue > 0 else 0

    # Generate recommendations
    recommendations = []
    if critical_stores > 0:
        recommendations.append(f"URGENT: {critical_stores} store(s) at CRITICAL capacity - consider closing intake or load balancing")
    if strained_stores > 0:
        recommendations.append(f"WARNING: {strained_stores} store(s) STRAINED - monitor closely and consider surge pricing")
    if critical_items > 0:
        recommendations.append(f"URGENT: {critical_items} product(s) at CRITICAL inventory risk - potential stockouts imminent")
    if high_risk_items > 5:
        recommendations.append(f"WARNING: {high_risk_items} products at HIGH risk - prioritize replenishment")
    if total_revenue_at_risk > 500:
        recommendations.append(f"ALERT: ${total_revenue_at_risk:.2f} revenue at risk from inventory shortages")
    if pricing_yield_pct < 2:
        recommendations.append("OPPORTUNITY: Pricing yield below target - review dynamic pricing strategy")
    if not recommendations:
        recommendations.append("All systems operating within normal parameters")

    return {
        "view": "summary",
        "timestamp": "now",  # Could add actual timestamp from effective_updated_at
        "capacity": {
            "total_stores": total_stores,
            "critical_stores": critical_stores,
            "strained_stores": strained_stores,
            "by_status": capacity_data,
        },
        "inventory_risk": {
            "critical_items": critical_items,
            "high_risk_items": high_risk_items,
            "total_revenue_at_risk": round(total_revenue_at_risk, 2),
            "by_risk_level": risk_data,
        },
        "pricing_yield": {
            "total_premium": total_premium,
            "total_revenue": total_revenue,
            "yield_percentage": round(pricing_yield_pct, 2),
            "delivered_orders": pricing_summary['delivered_orders'],
        },
        "recommendations": recommendations,
    }


async def _get_capacity(conn: asyncpg.Connection, store_id: Optional[str], limit: int) -> dict:
    """Get per-store capacity utilization."""

    query = """
        SELECT
            store_id,
            store_name,
            store_zone,
            store_capacity_orders_per_hour,
            current_active_orders,
            current_utilization_pct,
            headroom,
            health_status,
            recommended_action
        FROM store_capacity_health_mv
        WHERE ($1::text IS NULL OR store_id = $1)
        ORDER BY current_utilization_pct DESC
        LIMIT $2
    """

    rows = await conn.fetch(query, store_id, limit)

    stores = [dict(row) for row in rows]

    # Generate recommendations
    recommendations = []
    critical = [s for s in stores if s['health_status'] == 'CRITICAL']
    strained = [s for s in stores if s['health_status'] == 'STRAINED']

    if critical:
        store_names = ', '.join(s['store_name'] for s in critical[:3])
        recommendations.append(f"URGENT: Close intake or redirect orders at {store_names}")
    if strained:
        store_names = ', '.join(s['store_name'] for s in strained[:3])
        recommendations.append(f"WARNING: Consider surge pricing at {store_names}")
    if not stores:
        recommendations.append("No stores found matching criteria")
    elif not critical and not strained:
        recommendations.append("All stores operating with healthy capacity levels")

    return {
        "view": "capacity",
        "store_count": len(stores),
        "stores": stores,
        "recommendations": recommendations,
    }


async def _get_inventory_risk(
    conn: asyncpg.Connection,
    store_id: Optional[str],
    category: Optional[str],
    risk_level: Optional[str],
    limit: int,
) -> dict:
    """Get products at risk of stockout."""

    # Default to CRITICAL and HIGH if no risk_level specified
    if not risk_level:
        risk_filter = "risk_level IN ('CRITICAL', 'HIGH')"
        params = [store_id, category, limit]
    else:
        risk_filter = "risk_level = $3"
        params = [store_id, category, risk_level, limit]

    query = f"""
        SELECT
            inventory_id,
            store_id,
            store_name,
            store_zone,
            product_id,
            product_name,
            category,
            stock_level,
            pending_reservations,
            revenue_at_risk,
            perishable,
            risk_level
        FROM inventory_risk_mv
        WHERE ($1::text IS NULL OR store_id = $1)
          AND ($2::text IS NULL OR category = $2)
          AND {risk_filter}
        ORDER BY
            CASE risk_level
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                WHEN 'LOW' THEN 4
            END,
            revenue_at_risk DESC
        LIMIT ${len(params)}
    """

    rows = await conn.fetch(query, *params)

    items = [dict(row) for row in rows]

    # Calculate totals
    total_revenue_at_risk = sum(float(item['revenue_at_risk']) for item in items)
    critical_items = [i for i in items if i['risk_level'] == 'CRITICAL']

    # Generate recommendations
    recommendations = []
    if critical_items:
        top_critical = critical_items[:3]
        products = ', '.join(f"{i['product_name']} at {i['store_name']}" for i in top_critical)
        recommendations.append(f"URGENT: Immediate replenishment needed for {products}")
    if total_revenue_at_risk > 1000:
        recommendations.append(f"ALERT: ${total_revenue_at_risk:.2f} in pending orders at risk - prioritize fulfillment")
    if len(items) > 10:
        recommendations.append(f"WARNING: {len(items)} products showing inventory strain - review replenishment schedule")
    if not items:
        recommendations.append("No high-risk inventory issues found - inventory levels healthy")

    return {
        "view": "inventory_risk",
        "item_count": len(items),
        "total_revenue_at_risk": round(total_revenue_at_risk, 2),
        "items": items,
        "recommendations": recommendations,
    }


async def _get_quick_check(conn: asyncpg.Connection, store_id: str) -> dict:
    """Fast health check for a single store."""

    # Query 1: Store capacity
    capacity = await conn.fetchrow("""
        SELECT
            store_name,
            store_zone,
            current_active_orders,
            store_capacity_orders_per_hour,
            current_utilization_pct,
            headroom,
            health_status,
            recommended_action
        FROM store_capacity_health_mv
        WHERE store_id = $1
    """, store_id)

    if not capacity:
        return {
            "view": "quick_check",
            "store_id": store_id,
            "error": f"Store not found: {store_id}",
            "recommendations": ["Verify store_id is correct (e.g., 'store:BK-01')"],
        }

    # Query 2: High-risk inventory at this store
    risk_items = await conn.fetch("""
        SELECT
            product_name,
            category,
            stock_level,
            pending_reservations,
            revenue_at_risk,
            risk_level
        FROM inventory_risk_mv
        WHERE store_id = $1
          AND risk_level IN ('CRITICAL', 'HIGH')
        ORDER BY
            CASE risk_level
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
            END,
            revenue_at_risk DESC
        LIMIT 5
    """, store_id)

    risk_list = [dict(row) for row in risk_items]
    total_revenue_at_risk = sum(float(item['revenue_at_risk']) for item in risk_list)

    # Generate recommendations
    recommendations = []
    if capacity['health_status'] == 'CRITICAL':
        recommendations.append(f"URGENT: {capacity['store_name']} at {capacity['current_utilization_pct']}% capacity - {capacity['recommended_action']}")
    elif capacity['health_status'] == 'STRAINED':
        recommendations.append(f"WARNING: {capacity['store_name']} at {capacity['current_utilization_pct']}% capacity - monitor closely")

    if risk_list:
        critical_count = sum(1 for i in risk_list if i['risk_level'] == 'CRITICAL')
        if critical_count > 0:
            recommendations.append(f"URGENT: {critical_count} product(s) at CRITICAL inventory risk")
        recommendations.append(f"Inventory risk: ${total_revenue_at_risk:.2f} in pending orders may be unfulfillable")

    if not recommendations:
        recommendations.append(f"{capacity['store_name']} operating normally - {capacity['headroom']} orders headroom available")

    return {
        "view": "quick_check",
        "store_id": store_id,
        "store_name": capacity['store_name'],
        "store_zone": capacity['store_zone'],
        "capacity": {
            "current_active_orders": capacity['current_active_orders'],
            "max_capacity": capacity['store_capacity_orders_per_hour'],
            "utilization_pct": float(capacity['current_utilization_pct']),
            "headroom": capacity['headroom'],
            "health_status": capacity['health_status'],
            "recommended_action": capacity['recommended_action'],
        },
        "inventory_risk": {
            "high_risk_items": len(risk_list),
            "total_revenue_at_risk": round(total_revenue_at_risk, 2),
            "top_risks": risk_list,
        },
        "recommendations": recommendations,
    }
