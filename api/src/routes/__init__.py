# Routes module
from src.routes.audit import router as audit_router
from src.routes.freshmart import router as freshmart_router
from src.routes.loadgen import router as loadgen_router
from src.routes.ontology import router as ontology_router
from src.routes.query_stats import router as query_stats_router
from src.routes.triples import router as triples_router

__all__ = [
    "audit_router",
    "freshmart_router",
    "loadgen_router",
    "ontology_router",
    "query_stats_router",
    "triples_router",
]
