# Zero Server - Real-time Data Sync

This service provides real-time data synchronization from Materialize to web clients via WebSocket.

## Architecture

```
Web Clients (React)
    ↓ WebSocket
Zero Server (Node.js/TypeScript)
    ↓ PostgreSQL Protocol + TAIL/SUBSCRIBE
Materialize (Streaming Database)
    ↓ CDC
PostgreSQL (Source of Truth)
```

## How It Works

1. **Zero Server** connects to Materialize and subscribes to materialized views using the `SUBSCRIBE` command
2. **Materialize** streams changes from views in real-time
3. **Zero Server** broadcasts changes to all connected WebSocket clients
4. **React clients** receive updates and automatically refresh their UI

## Features

- ✅ Real-time push-based data synchronization
- ✅ WebSocket server with automatic reconnection
- ✅ Subscribe to multiple collections simultaneously
- ✅ Initial state sync on subscription
- ✅ Incremental updates via change events
- ✅ Type-safe schema definitions
- ✅ Docker support for easy deployment

## Configuration

Environment variables:

```bash
PORT=8090                    # WebSocket server port
MZ_HOST=mz                   # Materialize host
MZ_PORT=6875                 # Materialize port
MZ_USER=materialize          # Materialize user
MZ_PASSWORD=materialize      # Materialize password
MZ_DATABASE=materialize      # Materialize database
ZERO_COLLECTIONS=orders,stores,couriers,inventory,triples  # Collections to sync
```

## Collections

The server syncs these collections from Materialize views:

| Collection | Materialize View | Description |
|------------|------------------|-------------|
| `orders` | `orders_flat_mv` | Flattened order data with customer/store/courier info |
| `stores` | `store_inventory_mv` | Store information with inventory |
| `couriers` | `courier_schedule_mv` | Courier schedules and tasks |
| `inventory` | `store_inventory_mv` | Inventory levels by store |
| `triples` | `triples` | Subject-predicate-object triples |

## WebSocket Protocol

### Client → Server

**Subscribe to a collection:**
```json
{
  "type": "subscribe",
  "collection": "orders"
}
```

**Unsubscribe from a collection:**
```json
{
  "type": "unsubscribe",
  "collection": "orders"
}
```

### Server → Client

**Connection acknowledged:**
```json
{
  "type": "connected",
  "collections": ["orders", "stores", "couriers"]
}
```

**Initial state (full snapshot):**
```json
{
  "type": "initial-state",
  "collection": "orders",
  "data": [
    { "id": "order:001", "order_status": "CREATED", ... }
  ]
}
```

**Incremental changes:**
```json
{
  "type": "changes",
  "changes": [
    {
      "collection": "orders",
      "operation": "update",
      "data": { "id": "order:001", "order_status": "PICKING", ... },
      "timestamp": 1234567890
    }
  ]
}
```

## Development

```bash
# Install dependencies
npm install

# Run in development mode with hot reload
npm run dev

# Build for production
npm run build

# Run production build
npm start
```

## Docker

```bash
# Build image
docker build -t zero-server .

# Run container
docker run -p 8090:8090 \
  -e MZ_HOST=mz \
  -e MZ_PORT=6875 \
  zero-server
```

## Health Check

```bash
curl http://localhost:8090/health
```

Response:
```json
{
  "status": "ok",
  "clients": 3,
  "collections": ["orders", "stores", "couriers"]
}
```

## Integration with React

See `/web/src/contexts/ZeroContext.tsx` and `/web/src/hooks/useZeroQuery.ts` for React integration.

Example usage:

```typescript
import { useOrdersZero } from '../hooks/useZeroQuery'

function OrdersList() {
  const { data: orders, isLoading, connected } = useOrdersZero()

  if (isLoading) return <div>Loading...</div>
  if (!connected) return <div>Connecting to real-time updates...</div>

  return (
    <div>
      {orders?.map(order => (
        <div key={order.id}>{order.order_number}</div>
      ))}
    </div>
  )
}
```

## Benefits Over Polling

- **Instant Updates**: Changes appear immediately, no polling delay
- **Lower Latency**: Typically <100ms vs 5-30s polling intervals
- **Reduced Load**: Single WebSocket connection vs repeated HTTP requests
- **Better UX**: Real-time collaborative features
- **Efficient**: Only sends what changed, not full datasets

## Limitations

- WebSocket connections require persistent connections
- Clients must handle reconnection logic
- More complex than simple HTTP polling
- Requires backend service to stay running

## Troubleshooting

**WebSocket connection fails:**
- Check that Zero server is running on port 8090
- Verify VITE_ZERO_URL in web app `.env`
- Check network/firewall settings

**No data updates:**
- Verify Materialize is connected and healthy
- Check that views exist and have data
- Look at Zero server logs for SUBSCRIBE errors

**High memory usage:**
- Reduce number of collections
- Limit data volume in Materialize views
- Consider pagination for large datasets
