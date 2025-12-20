# Contributing Guide

Guide for developers contributing to the FreshMart Digital Twin project.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Integration Tests](#integration-tests)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Adding Features](#adding-features)

## Development Setup

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for web development)
- Python 3.11+ (for API/agent development)
- Make (optional, but recommended)

### Initial Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/your-username/freshmart-digital-twin-agent-starter.git
cd freshmart-digital-twin-agent-starter

# 2. Copy environment template
cp .env.example .env

# 3. Add your LLM API keys (for agent development)
# Edit .env and add:
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...

# 4. Start all services
make up

# 5. Verify services are running
docker-compose ps
```

### Development Workflow

**API Development (Python/FastAPI)**:

```bash
# Install dependencies
cd api
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Run with hot reload (inside container)
docker-compose up -d api
docker-compose logs -f api
```

**Web Development (React/TypeScript)**:

```bash
# Install dependencies
cd web
npm install

# Run dev server (hot reload enabled)
npm run dev

# Run tests
npm test

# Type check
npm run type-check

# Build for production
npm run build
```

**Agent Development (Python/LangGraph)**:

```bash
# Install dependencies
cd agents
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Test interactively
docker-compose exec -it agents python -m src.main chat
```

**Search Sync Worker (Python)**:

```bash
# Install dependencies
cd search-sync
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Watch logs
docker-compose logs -f search-sync
```

### Claude Code with Materialize MCP Server

If you use [Claude Code](https://github.com/anthropics/claude-code), you can install the [Materialize MCP Server](https://github.com/MaterializeInc/materialize-mcp-server) to query Materialize directly from your Claude Code session.

**Install the MCP Server:**

```bash
# Clone the repository
git clone https://github.com/MaterializeInc/materialize-mcp-server

# Add the MCP server to Claude Code (use absolute path to your clone)
claude mcp add materialize-local --command "uv" --args "run" "--project" "/path/to/materialize-mcp-server" "materialize-mcp-server"
```

The default connection string (`postgresql://materialize@localhost:6875/materialize`) works with the local Materialize instance started by `make up`.

For more details, see the [Materialize MCP Server developer docs](https://github.com/MaterializeInc/materialize-mcp-server/tree/main/developers).

## Project Structure

```
freshmart-digital-twin-agent-starter/
├── docker-compose.yml          # Service orchestration
├── Makefile                    # Common commands
├── .env.example                # Environment template
│
├── db/
│   ├── migrations/             # SQL migrations (run on startup)
│   ├── seed/                   # Demo data (small dataset)
│   ├── materialize/            # Materialize initialization
│   └── scripts/
│       ├── generate_data.sh    # Load test data generator wrapper
│       └── generate_load_test_data.py  # Python data generator
│
├── api/                        # FastAPI backend
│   ├── src/
│   │   ├── ontology/          # Ontology CRUD
│   │   ├── triples/           # Triple store + validation
│   │   ├── freshmart/         # FreshMart operational endpoints
│   │   └── routes/            # HTTP routes
│   └── tests/
│       ├── test_freshmart_service_integration.py  # PG/MZ integration tests
│       └── ...                # Unit and API tests
│
├── search-sync/               # OpenSearch sync workers
│   ├── src/
│   │   ├── base_subscribe_worker.py  # Abstract base class
│   │   ├── orders_sync.py     # Orders sync worker
│   │   ├── inventory_sync.py  # Inventory sync worker
│   │   └── mz_client_subscribe.py  # Materialize SUBSCRIBE client
│   └── tests/
│
├── zero-server/               # WebSocket server
│   └── src/
│       ├── server.ts          # WebSocket server
│       └── materialize-backend.ts  # SUBSCRIBE to Materialize
│
├── web/                       # React admin UI
│   ├── src/
│   │   ├── api/               # API client
│   │   ├── context/           # Zero WebSocket context
│   │   ├── hooks/             # useZeroQuery for real-time data
│   │   └── pages/             # UI pages
│   └── tests/
│
├── agents/                    # LangGraph agents
│   ├── src/
│   │   ├── tools/             # Agent tools
│   │   └── graphs/            # LangGraph definitions
│   └── tests/
│
└── docs/                      # Documentation
    ├── ARCHITECTURE.md
    ├── ONTOLOGY_GUIDE.md
    ├── API_REFERENCE.md
    ├── AGENTS.md
    ├── OPERATIONS.md
    ├── UI_GUIDE.md
    ├── CONTRIBUTING.md
    └── DYNAMIC_PRICING.md
```

## Running Tests

### API Unit Tests

```bash
cd api
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_ontology_service.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Search-Sync Tests

```bash
cd search-sync
python -m pytest tests/ -v

# Test SUBSCRIBE consolidation
python -m pytest tests/test_subscribe_consolidation.py -v
```

### Web Tests

```bash
cd web
npm test -- --run

# Watch mode
npm test

# Coverage
npm test -- --coverage
```

### Agent Tests

```bash
cd agents
python -m pytest tests/ -v

# Test specific tool
python -m pytest tests/test_tools.py::test_search_orders -v
```

## Integration Tests

The API includes integration tests that verify both PostgreSQL and Materialize read paths work correctly.

### Prerequisites

Requires running database connections:

```bash
# Start services
make up

# Verify databases are ready
docker-compose exec api python -c "from src.config import settings; print(settings.pg_external_url)"
```

### Run Integration Tests

```bash
cd api

# Run all integration tests
PG_HOST=localhost PG_PORT=5432 PG_USER=postgres PG_PASSWORD=postgres PG_DATABASE=freshmart \
MZ_HOST=localhost MZ_PORT=6875 MZ_USER=materialize MZ_PASSWORD=materialize MZ_DATABASE=materialize \
python -m pytest tests/test_freshmart_service_integration.py -v
```

### Test Classes

| Test Class | Tests | Description |
|------------|-------|-------------|
| `TestPostgreSQLReadPath` | 9 | Verifies FreshMart queries using PostgreSQL views |
| `TestMaterializeReadPath` | 9 | Verifies FreshMart queries using Materialize MVs |
| `TestCrossBackendConsistency` | 6 | Confirms both backends return identical data |
| `TestViewMapping` | 2 | Unit tests for view name mapping |

### Run Specific Test Classes

```bash
# PostgreSQL only
PG_HOST=localhost ... python -m pytest tests/test_freshmart_service_integration.py::TestPostgreSQLReadPath -v

# Materialize only
MZ_HOST=localhost ... python -m pytest tests/test_freshmart_service_integration.py::TestMaterializeReadPath -v

# Cross-backend consistency
python -m pytest tests/test_freshmart_service_integration.py::TestCrossBackendConsistency -v
```

## Code Style

### Python

Follow PEP 8 with these tools:

```bash
# Format with black
black api/src api/tests

# Sort imports
isort api/src api/tests

# Lint with flake8
flake8 api/src api/tests

# Type check with mypy
mypy api/src
```

### TypeScript/JavaScript

Follow project ESLint configuration:

```bash
cd web

# Lint
npm run lint

# Format with prettier
npm run format

# Type check
npm run type-check
```

### SQL

- Use lowercase for keywords
- Indent with 2 spaces
- Align column definitions
- Add comments for complex queries

## Pull Request Process

### 1. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Write code following style guidelines
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass

### 3. Commit Changes

```bash
git add .
git commit -m "Add feature: brief description

Detailed explanation of changes and why they were made."
```

**Commit Message Format**:
- First line: Brief summary (50 chars or less)
- Blank line
- Detailed explanation (wrap at 72 chars)

**Types**:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions/changes
- `refactor:` - Code restructuring
- `perf:` - Performance improvements

### 4. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub with:

**Title**: Clear, concise summary

**Description**:
- What changed and why
- Link to related issues
- Screenshots (for UI changes)
- Testing instructions

**Checklist**:
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] All tests passing
- [ ] Code follows style guide
- [ ] No breaking changes (or documented)

### 5. Code Review

- Address reviewer feedback
- Push additional commits to same branch
- Request re-review when ready

### 6. Merge

- Squash commits for clean history
- Delete branch after merge

## Adding Features

### Adding a New Ontology Class

See [Ontology Guide](ONTOLOGY_GUIDE.md) for complete walkthrough.

**Summary**:
1. Define class in `ontology_classes` table
2. Define properties in `ontology_properties` table
3. Create Materialize views (regular → materialized → indexes)
4. Update sync workers if needed
5. Update UI components
6. Add tests

### Adding a New API Endpoint

```python
# api/src/routes/example.py
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/example")
async def get_example():
    """Example endpoint."""
    return {"message": "Hello"}
```

**Add to main app**:
```python
# api/src/main.py
from src.routes import example

app.include_router(example.router, prefix="/api", tags=["example"])
```

**Add tests**:
```python
# api/tests/test_example.py
def test_get_example(client):
    response = client.get("/api/example")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello"}
```

### Adding a New Agent Tool

```python
# agents/src/tools/tool_example.py
from langchain_core.tools import tool

@tool
async def example_tool(param: str) -> dict:
    """
    Example tool description.

    Args:
        param: Parameter description

    Returns:
        Result dictionary
    """
    # Implementation
    return {"result": param}
```

**Register tool**:
```python
# agents/src/graphs/ops_assistant_graph.py
from src.tools.tool_example import example_tool

TOOLS = [
    # ... existing tools
    example_tool,
]
```

**Add tests**:
```python
# agents/tests/test_tools.py
import pytest
from src.tools.tool_example import example_tool

@pytest.mark.asyncio
async def test_example_tool():
    result = await example_tool.ainvoke({"param": "test"})
    assert result["result"] == "test"
```

### Adding a New UI Page

```typescript
// web/src/pages/ExamplePage.tsx
export function ExamplePage() {
  const [data] = useQuery(z.query.example_view);

  return (
    <div>
      <h1>Example Page</h1>
      {data.map(item => (
        <div key={item.id}>{item.name}</div>
      ))}
    </div>
  );
}
```

**Add route**:
```typescript
// web/src/App.tsx
import { ExamplePage } from './pages/ExamplePage';

<Route path="/example" element={<ExamplePage />} />
```

## Guidelines

### Testing

- Write tests for all new features
- Aim for >80% code coverage
- Test both success and error cases
- Use fixtures for common test data
- Mock external dependencies

### Documentation

- Update relevant docs for any changes
- Add inline comments for complex logic
- Update API docs for new endpoints
- Add examples for new features
- Keep README up to date

### Performance

- Profile before optimizing
- Use appropriate indexes
- Leverage Materialize for complex queries
- Batch operations when possible
- Monitor query execution times

### Security

- Validate all inputs
- Use parameterized queries
- Don't expose sensitive data in logs
- Follow principle of least privilege
- Keep dependencies updated

## Questions?

- Open an issue for bugs or feature requests
- Join discussions for design questions
- Check existing documentation first
- Ask in pull request comments

## See Also

- [Architecture Guide](ARCHITECTURE.md) - System architecture
- [Ontology Guide](ONTOLOGY_GUIDE.md) - Adding entity types
- [Operations Guide](OPERATIONS.md) - Running and debugging
