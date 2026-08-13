#!/usr/bin/env python3
"""
FreshMart Load Test Data Generator

Generates realistic operational data for load testing the triple store.
Creates ~700,000 triples representing 6 months of FreshMart operations.

Usage:
    python generate_load_test_data.py [--scale FACTOR] [--clear] [--dry-run]

Options:
    --scale FACTOR  Scale factor (1.0 = ~700K triples, 0.1 = ~70K triples)
    --clear         Clear existing demo data before generating
    --dry-run       Print statistics without inserting data
    --batch-size    Number of triples per INSERT batch (default: 1000)

Environment variables:
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE
"""

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Tuple

try:
    import psycopg2
    from psycopg2.extras import execute_values
    from faker import Faker
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install psycopg2-binary faker")
    sys.exit(1)

from demo_label import (
    address_state,
    catalog,
    load_label,
    locations,
    order_prefix,
    store_name,
)

# Initialize Faker with seed for reproducibility
fake = Faker()
Faker.seed(43)
random.seed(43)

# White-label config: the product catalog, store naming, locations, and the
# order-number prefix are all label-driven (labels/<name>.yaml -> `make label`).
# Structure is NOT: predicates, subject prefixes, zone codes, and entity counts
# are identical for every label so the demo behaves the same way each time.
LABEL = load_label()
REALISTIC_PRODUCTS = catalog(LABEL)
ZONES = locations(LABEL)
ORDER_PREFIX = order_prefix(LABEL)
ADDRESS_STATE = address_state(LABEL)

ORDER_STATUSES = ["CREATED", "DELIVERED", "CANCELLED"]
COURIER_STATUSES = ["OFF_SHIFT", "AVAILABLE", "ON_DELIVERY"]
VEHICLE_TYPES = ["BIKE", "SCOOTER", "CAR", "WALKING"]
TASK_STATUSES = ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"]


class DataGenerator:
    """Generates FreshMart load test data."""

    def __init__(self, scale: float = 1.0):
        self.scale = scale
        self.triples: List[Tuple[str, str, str, str]] = []

        # Scaled counts
        self.num_stores = max(10, int(50 * scale))
        self.num_products = len(REALISTIC_PRODUCTS)  # label catalog, expanded to seed.catalog.expand_to
        self.num_customers = max(100, int(5000 * scale))
        self.num_couriers = max(self.num_stores * 15, int(200 * scale))  # At least 15 couriers per store
        self.num_orders = max(500, int(25000 * scale))
        self.lines_per_order = 3  # Average
        self.num_days = 180  # 6 months

        # Generated IDs for reference
        self.store_ids: List[str] = []
        self.product_ids: List[str] = []
        self.customer_ids: List[str] = []
        self.courier_ids: List[str] = []
        self.order_ids: List[str] = []

        # Store-courier mapping for realistic assignments
        self.store_couriers: dict = {}

    def add_triple(self, subject_id: str, predicate: str, object_value: str, object_type: str):
        """Add a triple to the batch."""
        self.triples.append((subject_id, predicate, str(object_value), object_type))

    def generate_stores(self):
        """Generate store entities."""
        print(f"Generating {self.num_stores} stores...")

        stores_per_zone = max(1, self.num_stores // len(ZONES))
        store_num = 1

        for zone_code, zone_name, streets in ZONES:
            for i in range(stores_per_zone):
                if store_num > self.num_stores:
                    break

                store_id = f"store:{zone_code}-{i+1:02d}"
                self.store_ids.append(store_id)

                street = random.choice(streets)
                address = f"{random.randint(100, 999)} {street}, {zone_name}, {ADDRESS_STATE} {fake.zipcode_in_state(ADDRESS_STATE)}"

                self.add_triple(store_id, "store_name", store_name(LABEL, zone_name, i + 1), "string")
                self.add_triple(store_id, "store_address", address, "string")
                self.add_triple(store_id, "store_zone", zone_code, "string")
                self.add_triple(store_id, "store_status", random.choice(["OPEN", "OPEN", "OPEN", "LIMITED"]), "string")
                self.add_triple(store_id, "store_capacity_orders_per_hour", str(random.randint(30, 80)), "int")

                store_num += 1

    def generate_products(self):
        """Generate product entities using realistic catalog."""
        print(f"Generating all {len(REALISTIC_PRODUCTS)} products (products never scale)...")

        # Always use ALL realistic products regardless of scale parameter
        # Rows are (name, category, price, weight_grams, perishable).
        products_to_use = REALISTIC_PRODUCTS

        for product_num, (name, category, price, weight_grams, perishable) in enumerate(products_to_use, start=1):
            # Create consistent product ID
            product_id = f"product:prod{product_num:04d}"
            self.product_ids.append(product_id)

            self.add_triple(product_id, "product_name", name, "string")
            self.add_triple(product_id, "category", category, "string")
            self.add_triple(product_id, "unit_price", f"{price:.2f}", "float")
            self.add_triple(product_id, "unit_weight_grams", str(weight_grams), "int")
            self.add_triple(product_id, "perishable", str(perishable).lower(), "bool")

    def generate_customers(self):
        """Generate customer entities."""
        print(f"Generating {self.num_customers} customers...")

        for i in range(self.num_customers):
            customer_id = f"customer:{i+1:05d}"
            self.customer_ids.append(customer_id)

            zone = random.choice(ZONES)
            street = random.choice(zone[2])

            self.add_triple(customer_id, "customer_name", fake.name(), "string")
            self.add_triple(customer_id, "customer_email", fake.email(), "string")
            self.add_triple(customer_id, "customer_address",
                          f"{fake.building_number()} {street}, {zone[1]}, {ADDRESS_STATE} {fake.zipcode_in_state(ADDRESS_STATE)}",
                          "string")

    def generate_couriers(self):
        """Generate courier entities."""
        print(f"Generating {self.num_couriers} couriers...")

        couriers_per_store = max(15, self.num_couriers // len(self.store_ids))
        courier_num = 1

        for store_id in self.store_ids:
            self.store_couriers[store_id] = []

            for i in range(couriers_per_store):
                if courier_num > self.num_couriers:
                    break

                courier_id = f"courier:C-{courier_num:04d}"
                self.courier_ids.append(courier_id)
                self.store_couriers[store_id].append(courier_id)

                self.add_triple(courier_id, "courier_name", fake.name(), "string")
                self.add_triple(courier_id, "courier_home_store", store_id, "entity_ref")
                self.add_triple(courier_id, "vehicle_type", random.choice(VEHICLE_TYPES), "string")
                self.add_triple(courier_id, "courier_status", "AVAILABLE", "string")

                courier_num += 1

    def generate_inventory(self):
        """Generate inventory items for each store."""
        print(f"Generating inventory for {len(self.store_ids)} stores...")

        inventory_num = 1
        # All products available in all stores (1000 products per store)
        products_per_store = len(self.product_ids)

        for store_id in self.store_ids:
            # Each store carries all products
            store_products = self.product_ids

            for product_id in store_products:
                inventory_id = f"inventory:INV-{inventory_num:06d}"

                stock = random.randint(0, 100)

                self.add_triple(inventory_id, "inventory_store", store_id, "entity_ref")
                self.add_triple(inventory_id, "inventory_product", product_id, "entity_ref")
                self.add_triple(inventory_id, "stock_level", str(stock), "int")

                # Add replenishment ETA for low stock items
                if stock < 10:
                    eta = datetime.now() + timedelta(hours=random.randint(4, 48))
                    self.add_triple(inventory_id, "replenishment_eta", eta.isoformat(), "timestamp")

                inventory_num += 1

    def generate_orders(self):
        """Generate orders with order lines and delivery tasks."""
        print(f"Generating {self.num_orders} orders with order lines and delivery tasks...")

        # Distribute orders across the time period
        start_date = datetime.now() - timedelta(days=self.num_days)

        for i in range(self.num_orders):
            if i % 5000 == 0 and i > 0:
                print(f"  Generated {i} orders...")

            order_id = f"order:{ORDER_PREFIX}{i+1:06d}"
            self.order_ids.append(order_id)

            # Random date within the period, weighted toward recent
            days_ago = int(random.triangular(0, self.num_days, self.num_days * 0.3))
            order_date = datetime.now() - timedelta(days=days_ago)

            # Peak hours: 11am-1pm, 5pm-8pm
            hour = random.choices(
                range(24),
                weights=[1,1,1,1,1,1,1,2,3,4,5,8,8,5,4,3,4,6,8,8,6,4,2,1]
            )[0]
            order_date = order_date.replace(hour=hour, minute=random.randint(0, 59))

            # Assign to store and customer
            store_id = random.choice(self.store_ids)
            customer_id = random.choice(self.customer_ids)

            # Delivery window (1-2 hours from order)
            window_start = order_date + timedelta(hours=random.uniform(0.5, 1.5))
            window_end = window_start + timedelta(hours=random.uniform(1, 2))

            # Status based on age
            if days_ago > 2:
                status = random.choices(
                    ORDER_STATUSES,
                    weights=[1, 90, 6]  # Mostly delivered
                )[0]
            elif days_ago > 0:
                status = random.choices(
                    ORDER_STATUSES,
                    weights=[5, 60, 5]
                )[0]
            else:  # Today
                status = random.choices(
                    ORDER_STATUSES,
                    weights=[30, 15, 5]  # Mostly created, waiting for courier
                )[0]

            # Generate order lines first to calculate total
            num_lines = random.randint(1, 6)
            line_products = random.sample(self.product_ids, min(num_lines, len(self.product_ids)))

            order_total = Decimal("0.00")
            for line_num, product_id in enumerate(line_products, 1):
                # Use UUID-based line IDs (consistent with order_line_service.py)
                line_uuid = str(uuid.uuid4())
                line_id = f"orderline:{line_uuid}"
                quantity = random.randint(1, 4)
                # Get a reasonable price
                unit_price = Decimal(str(random.uniform(2.0, 15.0))).quantize(Decimal("0.01"))
                line_total = unit_price * quantity
                order_total += line_total

                self.add_triple(line_id, "line_of_order", order_id, "entity_ref")
                self.add_triple(line_id, "line_product", product_id, "entity_ref")
                self.add_triple(line_id, "quantity", str(quantity), "int")
                self.add_triple(line_id, "order_line_unit_price", str(unit_price), "float")
                self.add_triple(line_id, "line_amount", str(line_total), "float")
                self.add_triple(line_id, "line_sequence", str(line_num), "int")

            # Order triples
            self.add_triple(order_id, "order_number", f"{ORDER_PREFIX}{i+1:06d}", "string")
            self.add_triple(order_id, "order_status", status, "string")
            self.add_triple(order_id, "order_store", store_id, "entity_ref")
            self.add_triple(order_id, "placed_by", customer_id, "entity_ref")
            self.add_triple(order_id, "delivery_window_start", window_start.isoformat(), "timestamp")
            self.add_triple(order_id, "delivery_window_end", window_end.isoformat(), "timestamp")
            self.add_triple(order_id, "order_total_amount", str(order_total), "float")
            self.add_triple(order_id, "order_created_at", order_date.isoformat(), "timestamp")

            # Generate delivery task for non-cancelled orders
            if status != "CANCELLED":
                task_id = f"task:T-{i+1:06d}"

                # Assign courier from the store
                store_couriers = self.store_couriers.get(store_id, self.courier_ids)
                courier_id = random.choice(store_couriers) if store_couriers else random.choice(self.courier_ids)

                # Task status mirrors order status
                if status == "DELIVERED":
                    task_status = "COMPLETED"
                elif status == "OUT_FOR_DELIVERY":
                    task_status = "IN_PROGRESS"
                else:
                    task_status = "PENDING"

                self.add_triple(task_id, "task_of_order", order_id, "entity_ref")
                self.add_triple(task_id, "assigned_to", courier_id, "entity_ref")
                self.add_triple(task_id, "task_status", task_status, "string")

                if status in ["OUT_FOR_DELIVERY", "DELIVERED"]:
                    eta = window_start + timedelta(minutes=random.randint(-15, 30))
                    self.add_triple(task_id, "eta", eta.isoformat(), "timestamp")
                    self.add_triple(task_id, "route_sequence", str(random.randint(1, 5)), "int")

    def generate_all(self):
        """Generate all entity types."""
        self.generate_stores()
        self.generate_products()
        self.generate_customers()
        self.generate_couriers()
        self.generate_inventory()
        self.generate_orders()

        return self.triples

    def get_statistics(self) -> dict:
        """Return statistics about generated data."""
        return {
            "scale_factor": self.scale,
            "stores": self.num_stores,
            "products": self.num_products,
            "customers": self.num_customers,
            "couriers": self.num_couriers,
            "orders": self.num_orders,
            "estimated_order_lines": self.num_orders * self.lines_per_order,
            "estimated_delivery_tasks": int(self.num_orders * 0.94),  # ~6% cancelled
            "estimated_inventory_items": self.num_stores * min(len(self.product_ids), int(200 * self.scale)),
            "total_triples": len(self.triples),
        }


def get_db_connection():
    """Create database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", 5432)),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", "postgres"),
        database=os.environ.get("PG_DATABASE", "freshmart"),
    )


def clear_demo_data(conn):
    """Clear existing demo data (keeps ontology)."""
    print("Clearing existing triple data...")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM triples")
        deleted = cur.rowcount
        conn.commit()
        print(f"  Deleted {deleted} existing triples")


def record_seeded_label(conn, label_name: str):
    """Record which label produced this data, so a UI built from a different
    label's artifact can be detected. Tolerates the table not existing yet
    (an older database that has not run migration 090)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO demo_label (id, label, seeded_at)
                VALUES (1, %s, NOW())
                ON CONFLICT (id) DO UPDATE
                    SET label = EXCLUDED.label, seeded_at = EXCLUDED.seeded_at
                """,
                (label_name,),
            )
            conn.commit()
        print(f"Recorded seeded label: {label_name}")
    except psycopg2.Error as exc:
        conn.rollback()
        print(f"  Could not record seeded label ({exc.__class__.__name__}); continuing.")


def insert_triples(conn, triples: List[Tuple], batch_size: int = 1000):
    """Insert triples in batches."""
    print(f"Inserting {len(triples)} triples in batches of {batch_size}...")

    with conn.cursor() as cur:
        for i in range(0, len(triples), batch_size):
            batch = triples[i:i + batch_size]
            execute_values(
                cur,
                """
                INSERT INTO triples (subject_id, predicate, object_value, object_type)
                VALUES %s
                """,
                batch,
                template="(%s, %s, %s, %s)"
            )

            if (i + batch_size) % 50000 == 0 or i + batch_size >= len(triples):
                conn.commit()
                print(f"  Inserted {min(i + batch_size, len(triples))} triples...")

    conn.commit()
    print("  Done!")


def run_analyze(conn):
    """Run ANALYZE to update table statistics."""
    print("Running ANALYZE on triples table...")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("ANALYZE triples")
    conn.autocommit = False
    print("  Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Generate FreshMart load test data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate full dataset (~700K triples)
  python generate_load_test_data.py

  # Generate smaller dataset for testing (~70K triples)
  python generate_load_test_data.py --scale 0.1

  # Clear and regenerate
  python generate_load_test_data.py --clear

  # Preview without inserting
  python generate_load_test_data.py --dry-run
        """
    )
    parser.add_argument("--scale", type=float, default=1.0,
                       help="Scale factor (1.0 = ~700K triples)")
    parser.add_argument("--clear", action="store_true",
                       help="Clear existing data before generating")
    parser.add_argument("--dry-run", action="store_true",
                       help="Print statistics without inserting")
    parser.add_argument("--batch-size", type=int, default=1000,
                       help="Batch size for inserts")

    args = parser.parse_args()

    print("=" * 60)
    print("FreshMart Load Test Data Generator")
    print("=" * 60)
    print()

    # Generate data
    generator = DataGenerator(scale=args.scale)
    triples = generator.generate_all()

    # Print statistics
    stats = generator.get_statistics()
    print()
    print("Generated Data Statistics:")
    print("-" * 40)
    print(f"  Scale factor:        {stats['scale_factor']}")
    print(f"  Stores:              {stats['stores']:,}")
    print(f"  Products:            {stats['products']:,}")
    print(f"  Customers:           {stats['customers']:,}")
    print(f"  Couriers:            {stats['couriers']:,}")
    print(f"  Orders:              {stats['orders']:,}")
    print(f"  Order Lines:         ~{stats['estimated_order_lines']:,}")
    print(f"  Delivery Tasks:      ~{stats['estimated_delivery_tasks']:,}")
    print(f"  Inventory Items:     ~{stats['estimated_inventory_items']:,}")
    print("-" * 40)
    print(f"  TOTAL TRIPLES:       {stats['total_triples']:,}")
    print()

    if args.dry_run:
        print("Dry run - no data inserted")
        return

    # Connect and insert
    try:
        conn = get_db_connection()
        print(f"Connected to PostgreSQL at {os.environ.get('PG_HOST', 'localhost')}:{os.environ.get('PG_PORT', 5432)}")
        print()

        if args.clear:
            clear_demo_data(conn)
            print()

        insert_triples(conn, triples, batch_size=args.batch_size)
        print()

        record_seeded_label(conn, LABEL.get("label", "freshmart"))
        print()

        run_analyze(conn)
        print()

        # Verify count
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM triples")
            total = cur.fetchone()[0]
            print(f"Total triples in database: {total:,}")

        conn.close()

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("Data generation complete!")
    print()
    print("Materialize views update automatically via CDC.")
    print()
    print("Next steps:")
    print("  1. Verify data in Materialize (may take a few seconds to sync):")
    print("     PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \\")
    print('       "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_flat_mv;"')
    print()
    print("  2. Test query performance:")
    print("     curl http://localhost:8080/freshmart/orders | head")
    print()
    print("  3. Compare PostgreSQL vs Materialize:")
    print("     curl http://localhost:8080/stats")
    print("=" * 60)


if __name__ == "__main__":
    main()
