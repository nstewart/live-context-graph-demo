# FreshMart Load Generator

A standalone load generation tool that enables realistic, high-volume e-commerce activity for the FreshMart digital twin demo. Demonstrates Materialize's capabilities in handling real-time operational data at scale with sub-second data propagation.

## Features

- **Realistic Activity Patterns**: Simulates authentic e-commerce behavior including orders, status transitions, inventory updates, and customer creation
- **Multiple Load Profiles**: Pre-configured profiles from gentle demo activity to stress testing
- **Configurable Intensity**: Easy to adjust throughput, concurrency, and duration
- **Observable Activity**: Rich console output with real-time metrics and statistics
- **Graceful Operation**: Handles API errors, retries transient failures, and provides clean shutdown
- **Peak Hours Simulation**: Adjusts activity rates based on time of day (morning rush, lunch peak, dinner rush)

## Quick Start

### Installation

```bash
cd load-generator

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Basic Usage

```bash
# Start with demo profile (5 orders/min, 30 min duration)
python -m loadgen start

# Start with specific profile
python -m loadgen start --profile standard

# Start with custom duration
python -m loadgen start --profile peak --duration 60

# Check API health
python -m loadgen health

# List available profiles
python -m loadgen profiles
```

### Using Make (from repository root)

```bash
# Add to Makefile for convenience
make load-gen         # Start with demo profile
make load-gen-standard # Start with standard profile
make load-gen-peak    # Start with peak profile
```

## Load Profiles

### Demo Profile (default)
- **Target**: 5 orders/min
- **Concurrent workflows**: 10
- **Duration**: 30 minutes
- **Use case**: Gentle activity for showcasing features and demos

### Standard Profile
- **Target**: 20 orders/min
- **Concurrent workflows**: 50
- **Duration**: 2 hours
- **Use case**: Realistic weekday traffic simulation

### Peak Profile
- **Target**: 60 orders/min
- **Concurrent workflows**: 150
- **Duration**: 1 hour
- **Use case**: Peak hour simulation, demonstrates Materialize vs PostgreSQL performance

### Stress Profile
- **Target**: 200 orders/min
- **Concurrent workflows**: 500
- **Duration**: 30 minutes
- **Use case**: Stress testing to identify bottlenecks and system limits

## Activity Types

The load generator simulates six types of realistic e-commerce activities:

| Activity | Weight | Description |
|----------|--------|-------------|
| **New Orders** | 40% | Create orders with 1-6 line items from random customers |
| **Status Transitions** | 30% | Progress orders through lifecycle (CREATED → PICKING → OUT_FOR_DELIVERY → DELIVERED) |
| **Order Modifications** | 10% | Add/remove items from CREATED orders |
| **Customer Creation** | 5% | New customer registrations with realistic names and addresses |
| **Inventory Updates** | 10% | Stock level adjustments (replenishment, adjustments) |
| **Order Cancellations** | 5% | Cancel orders in CREATED or PICKING status |

## Order Lifecycle

Orders naturally progress through realistic status transitions:

```
CREATED (5-30 min) → PICKING (10-20 min) → OUT_FOR_DELIVERY (20-45 min) → DELIVERED
                                        \
                                         → CANCELLED (5% chance)
```

Timing is probabilistic to simulate real-world variability.

## Command-Line Interface

### `start` - Start Load Generation

```bash
python -m loadgen start [OPTIONS]
```

**Options:**
- `--profile TEXT`: Load profile to use (demo, standard, peak, stress) [default: demo]
- `--api-url TEXT`: FreshMart API base URL [default: http://localhost:8080]
- `--duration INTEGER`: Duration in minutes (overrides profile default)
- `--seed INTEGER`: Random seed for reproducibility
- `--verbose`: Enable verbose logging
- `--dry-run`: Show configuration without running
- `--help`: Show help message

**Examples:**

```bash
# Basic usage with demo profile
python -m loadgen start

# Use standard profile for 30 minutes
python -m loadgen start --profile standard --duration 30

# Connect to remote API
python -m loadgen start --api-url http://freshmart.example.com:8080

# Reproducible run with seed
python -m loadgen start --profile demo --seed 42

# Dry run to see configuration
python -m loadgen start --profile stress --dry-run

# Verbose output for debugging
python -m loadgen start --profile demo --verbose
```

### `profiles` - List Available Profiles

```bash
python -m loadgen profiles
```

Shows detailed information about all available load profiles.

### `health` - Check API Health

```bash
python -m loadgen health [API_URL]
```

Check if the FreshMart API is available and healthy.

**Example:**
```bash
python -m loadgen health http://localhost:8080
```

## Console Output

### Example Output

```
FreshMart Load Generator
============================================================
Profile: standard - Realistic weekday traffic
Target: 20 orders/min
Concurrent Workflows: 50
Duration: 120 minutes
API: http://localhost:8080
============================================================

[12:34:56] Initializing load orchestrator...
[12:34:57] API health check passed
[12:34:58] Loaded 150 customers, 5 stores, 965 products
[12:34:59] Load orchestrator initialized successfully
[12:34:59] Running for 120 minutes...

[12:35:59] Last minute: 18 activities, 18.0/min, 234ms avg latency, 100.0% success
[12:36:59] Last minute: 20 activities, 20.0/min, 241ms avg latency, 100.0% success

^C
[12:38:23] Interrupt received, stopping gracefully...
[12:38:24] Stopping workers...

============================================================
Final Summary
============================================================
Duration: 3.4 minutes
Total activities: 68
Success rate: 100.0%
Throughput: 20.0 activities/min
Avg latency: 237ms
P95 latency: 412ms
P99 latency: 524ms

Activity Breakdown:
  Orders created: 27
  Status transitions: 21
  Customers created: 3
  Inventory updates: 7
  Cancellations: 2
============================================================
```

## Integration with FreshMart

### Prerequisites

The FreshMart system must be running before starting the load generator:

```bash
# Start FreshMart (from repository root)
make up

# Or with agents
make up-agent

# Wait for services to be ready (usually 30-60 seconds)
```

Verify services are running:
- API: http://localhost:8080/docs
- UI: http://localhost:5173
- Materialize Console: http://localhost:6874

### API Endpoints Used

The load generator interacts with FreshMart through these endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Verify API availability |
| `POST /triples/batch` | Create orders, customers, order lines |
| `PUT /triples/batch` | Update order status, inventory levels |
| `GET /freshmart/orders` | Query existing orders |
| `GET /freshmart/customers` | Get customer list |
| `GET /freshmart/stores` | Get store list |
| `GET /freshmart/products` | Get product catalog |

### Observing Activity

Once the load generator is running, observe activity in:

1. **FreshMart UI** (http://localhost:5173)
   - Orders appear in real-time (< 2 second latency)
   - Watch status transitions
   - Monitor inventory levels

2. **API Stats** (http://localhost:8080/stats)
   - Compare PostgreSQL vs Materialize query performance
   - Observe query counts increasing

3. **Materialize Console** (http://localhost:6874)
   - View materialized view refresh activity
   - Monitor cluster resource usage
   - Observe CDC replication lag

4. **Search Activity**
   - Use OpenSearch to search for recent orders
   - Verify sub-2-second indexing latency

## Development

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=loadgen --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run with verbose output
pytest -v
```

### Project Structure

```
load-generator/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── pyproject.toml         # Package configuration
├── loadgen/
│   ├── __init__.py
│   ├── cli.py             # Command-line interface
│   ├── config.py          # Profiles and configuration
│   ├── orchestrator.py    # Main orchestration loop
│   ├── api_client.py      # FreshMart API client
│   ├── data_generators.py # Realistic data generation
│   ├── metrics.py         # Metrics tracking
│   └── scenarios/
│       ├── __init__.py
│       ├── orders.py      # Order creation scenarios
│       ├── lifecycle.py   # Order status transitions
│       ├── inventory.py   # Inventory updates
│       └── customers.py   # Customer creation
└── tests/
    ├── __init__.py
    ├── conftest.py        # Pytest fixtures
    ├── test_config.py
    ├── test_data_generators.py
    ├── test_api_client.py
    └── test_metrics.py
```

### Adding New Scenarios

To add a new scenario:

1. Create a new file in `loadgen/scenarios/`
2. Implement a class with `initialize()` and `execute()` methods
3. Add scenario to orchestrator in `loadgen/orchestrator.py`
4. Update activity weights in profile configuration

Example:

```python
# loadgen/scenarios/my_scenario.py
class MyScenario:
    def __init__(self, api_client, data_generator):
        self.api_client = api_client
        self.data_generator = data_generator

    async def initialize(self):
        """Initialize scenario (load reference data)."""
        pass

    async def execute(self) -> dict:
        """Execute scenario and return result."""
        return {"success": True, "details": "..."}
```

### Creating Custom Profiles

Create custom profiles by modifying `loadgen/config.py`:

```python
PROFILES["custom"] = LoadProfile(
    name="custom",
    description="My custom profile",
    orders_per_minute=100,
    concurrent_workflows=200,
    duration_minutes=60,
    new_order_weight=0.50,
    status_transition_weight=0.30,
    # ... other weights
)
```

## Troubleshooting

### API Connection Refused

**Problem**: `Connection refused` or `API health check failed`

**Solution**:
```bash
# Verify FreshMart is running
docker-compose ps

# Check API logs
docker-compose logs api

# Restart services
make down && make up
```

### Low Throughput

**Problem**: Actual throughput is lower than target

**Possible causes**:
- System resource constraints (CPU, memory)
- Database or Materialize overload
- Network latency

**Solutions**:
- Use a lower profile (demo instead of stress)
- Check Docker resource limits
- Monitor Materialize cluster health

### High Error Rate

**Problem**: Many activities failing (< 90% success rate)

**Possible causes**:
- Invalid reference data (missing products, stores)
- Ontology validation failures
- API errors

**Solutions**:
```bash
# Enable verbose logging
python -m loadgen start --verbose

# Check API logs
docker-compose logs -f api

# Verify seed data exists
docker-compose exec api python -m pytest tests/test_freshmart_api.py
```

### Orders Not Appearing in UI

**Problem**: Load generator reports success but orders don't appear in UI

**Possible causes**:
- Materialize replication lag
- WebSocket connection issues
- Zero server not running

**Solutions**:
```bash
# Check Materialize replication status
docker-compose exec mz psql -U materialize -c "SHOW SOURCES"

# Check zero-server logs
docker-compose logs zero-server

# Restart zero-server
docker-compose restart zero-server
```

## Performance Expectations

### Throughput Targets

| Profile | Orders/min | Triples/min | Expected Latency |
|---------|------------|-------------|------------------|
| Demo | 5 | ~50 | < 500ms |
| Standard | 20 | ~200 | < 800ms |
| Peak | 60 | ~600 | < 1.5s |
| Stress | 200 | ~2000 | < 3s |

*Note: Each order generates ~10 triples (order attributes + line items)*

### System Requirements

Recommended resources for development machine:

- **Demo/Standard**: 4 CPU cores, 8GB RAM
- **Peak**: 8 CPU cores, 16GB RAM
- **Stress**: 16 CPU cores, 32GB RAM

Docker Desktop resource allocation should match or exceed these values.

## Advanced Usage

### Running Against Remote API

```bash
# Point to cloud-hosted FreshMart
python -m loadgen start \
  --api-url https://freshmart.example.com:8080 \
  --profile standard \
  --duration 60
```

### Reproducible Load Testing

```bash
# Use seed for reproducible data generation
python -m loadgen start --seed 42 --profile demo

# Same seed produces same sequence of orders
python -m loadgen start --seed 42 --profile demo
```

### Continuous Integration

```bash
# Short smoke test for CI
python -m loadgen start --profile demo --duration 5

# Exit code 0 on success, 1 on failure
```

### Monitoring Load Generation

Monitor load generator performance:

```bash
# Terminal 1: Run load generator
python -m loadgen start --profile standard

# Terminal 2: Monitor API performance
watch -n 1 'curl -s http://localhost:8080/stats | jq .'

# Terminal 3: Monitor Docker stats
docker stats
```

## Comparison with generate_load_test_data.py

The existing `db/scripts/generate_load_test_data.py` serves a different purpose:

| Feature | generate_load_test_data.py | load-generator |
|---------|---------------------------|----------------|
| **Purpose** | Bulk seed data generation | Continuous live activity |
| **Data volume** | ~700K triples (6 months) | Configurable rate |
| **Execution** | One-time batch | Continuous streaming |
| **Use case** | Initial database population | Real-time demo |
| **CDC demo** | No | Yes |
| **Timing** | All at once | Realistic intervals |

**Use both**:
1. Run `generate_load_test_data.py` once for historical data
2. Run `load-generator` continuously for live activity

## FAQ

**Q: Can I run multiple load generators simultaneously?**

A: Yes, you can run multiple instances with different profiles or against different API endpoints. Be mindful of system resource limits.

**Q: How do I stop the load generator gracefully?**

A: Press `Ctrl+C` once. The generator will finish in-flight activities and print a summary. Avoid force-killing (Ctrl+C twice) as it may leave partial data.

**Q: Does the load generator clean up test data?**

A: No. The load generator creates real orders that persist in PostgreSQL and Materialize. Use `make db-reset` to clear all data.

**Q: Can I customize activity weights without editing code?**

A: Currently, activity weights are defined in `loadgen/config.py`. Future versions may support configuration files.

**Q: Why are my throughput numbers lower than the target?**

A: The target is a goal, not a guarantee. Actual throughput depends on system performance, network latency, and resource availability. The orchestrator doesn't artificially throttle; it lets workers execute as fast as the system allows.

**Q: How does peak hours simulation work?**

A: The data generator applies time-of-day multipliers: 1.5x for morning (7-9 AM), 2x for lunch (11 AM-1 PM), 2.5x for dinner (5-8 PM), 0.3x for late night (10 PM-6 AM).

## Contributing

Contributions are welcome! Please:

1. Add tests for new functionality
2. Update documentation
3. Follow existing code style
4. Ensure tests pass: `pytest`

## License

MIT License (same as parent repository)

## Support

- **Issues**: Report bugs and feature requests at the repository issue tracker
- **Documentation**: See parent repository `/docs` for FreshMart architecture details
- **API Reference**: http://localhost:8080/docs when FreshMart is running
