#!/usr/bin/env python3
import asyncio
import psycopg

async def test_subscribe():
    print("Connecting to Materialize...")
    conn = await psycopg.AsyncConnection.connect(
        "host=localhost port=6875 user=materialize password=materialize database=materialize",
        autocommit=True
    )

    print("Setting cluster to serving...")
    await conn.execute("SET CLUSTER = serving")

    print("Starting SUBSCRIBE to orders_search_source_mv...")
    cursor = conn.cursor()
    await cursor.execute("SUBSCRIBE (SELECT * FROM orders_search_source_mv) WITH (PROGRESS)")

    print("Waiting for first 5 rows...\n")
    count = 0
    try:
        async for row in cursor:
            count += 1
            print(f"Row {count}: ts={row[0]}, diff={row[1]}, progressed={row[2] if len(row) > 2 else 'N/A'}")
            if count >= 5:
                break
    except Exception as e:
        print(f"Error during iteration: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nReceived {count} rows")
    await cursor.close()
    await conn.close()

if __name__ == "__main__":
    asyncio.run(test_subscribe())
