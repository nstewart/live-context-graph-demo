"""Triple service for CRUD operations."""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ontology.service import OntologyService
from src.triples.models import (
    SubjectInfo,
    Triple,
    TripleCreate,
    TripleFilter,
    TripleUpdate,
    ValidationResult,
)
from src.triples.validator import TripleValidator

logger = logging.getLogger(__name__)


class TripleValidationError(Exception):
    """Exception raised when triple validation fails."""

    def __init__(self, validation_result: ValidationResult):
        self.validation_result = validation_result
        super().__init__(f"Triple validation failed: {validation_result.errors}")


class TripleService:
    """Service for triple management with ontology validation."""

    def __init__(self, session: AsyncSession, validate: bool = True):
        self.session = session
        self.validate = validate
        self._ontology_service: Optional[OntologyService] = None
        self._validator: Optional[TripleValidator] = None

    @property
    def ontology_service(self) -> OntologyService:
        """Lazy-load ontology service."""
        if self._ontology_service is None:
            self._ontology_service = OntologyService(self.session)
        return self._ontology_service

    @property
    def validator(self) -> TripleValidator:
        """Lazy-load validator."""
        if self._validator is None:
            self._validator = TripleValidator(self.ontology_service)
        return self._validator

    async def list_triples(self, filter_: Optional[TripleFilter] = None, limit: int = 100, offset: int = 0) -> list[Triple]:
        """List triples with optional filtering."""
        conditions = []
        params: dict = {"limit": limit, "offset": offset}

        if filter_:
            if filter_.subject_id:
                conditions.append("subject_id = :subject_id")
                params["subject_id"] = filter_.subject_id
            if filter_.predicate:
                conditions.append("predicate = :predicate")
                params["predicate"] = filter_.predicate
            if filter_.object_value:
                conditions.append("object_value = :object_value")
                params["object_value"] = filter_.object_value
            if filter_.object_type:
                conditions.append("object_type = :object_type")
                params["object_type"] = filter_.object_type.value

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT id, subject_id, predicate, object_value, object_type,
                   created_at, updated_at
            FROM triples
            {where_clause}
            ORDER BY subject_id, predicate
            LIMIT :limit OFFSET :offset
        """

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()
        return [
            Triple(
                id=row.id,
                subject_id=row.subject_id,
                predicate=row.predicate,
                object_value=row.object_value,
                object_type=row.object_type,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def get_triple(self, triple_id: int) -> Optional[Triple]:
        """Get a triple by ID."""
        result = await self.session.execute(
            text("""
                SELECT id, subject_id, predicate, object_value, object_type,
                       created_at, updated_at
                FROM triples
                WHERE id = :triple_id
            """),
            {"triple_id": triple_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return Triple(
            id=row.id,
            subject_id=row.subject_id,
            predicate=row.predicate,
            object_value=row.object_value,
            object_type=row.object_type,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def get_subject(self, subject_id: str) -> SubjectInfo:
        """Get all triples for a subject."""
        # Get triples
        triples = await self.list_triples(TripleFilter(subject_id=subject_id), limit=1000)

        # Get class info
        prefix = subject_id.split(":")[0]
        ont_class = await self.ontology_service.get_class_by_prefix(prefix)

        return SubjectInfo(
            subject_id=subject_id,
            class_name=ont_class.class_name if ont_class else None,
            class_id=ont_class.id if ont_class else None,
            triples=triples,
        )

    async def create_triple(self, data: TripleCreate) -> Triple:
        """Create a new triple with optional validation."""
        # Validate against ontology
        if self.validate:
            validation_result = await self.validator.validate(data)
            if not validation_result.is_valid:
                raise TripleValidationError(validation_result)

        # Insert triple
        result = await self.session.execute(
            text("""
                INSERT INTO triples (subject_id, predicate, object_value, object_type)
                VALUES (:subject_id, :predicate, :object_value, :object_type)
                ON CONFLICT (subject_id, predicate, object_value) DO UPDATE
                SET updated_at = NOW()
                RETURNING id, subject_id, predicate, object_value, object_type,
                          created_at, updated_at
            """),
            {
                "subject_id": data.subject_id,
                "predicate": data.predicate,
                "object_value": data.object_value,
                "object_type": data.object_type.value,
            },
        )
        row = result.fetchone()
        return Triple(
            id=row.id,
            subject_id=row.subject_id,
            predicate=row.predicate,
            object_value=row.object_value,
            object_type=row.object_type,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def create_triples_batch(self, triples: list[TripleCreate]) -> list[Triple]:
        """Create multiple triples in a batch."""
        # Log transaction start with summary of what's being written
        subjects = {}  # subject_id -> list of predicates
        for triple in triples:
            if triple.subject_id not in subjects:
                subjects[triple.subject_id] = []
            subjects[triple.subject_id].append(triple.predicate)

        # Determine which entity types and OpenSearch indices will be affected
        entity_types_affected = {}
        for subject_id in subjects.keys():
            prefix = subject_id.split(":")[0]
            if prefix not in entity_types_affected:
                entity_types_affected[prefix] = set()
            entity_types_affected[prefix].add(subject_id)

        # Create summary showing entity types (e.g., "2 orderlines, 1 order")
        entity_summary = ", ".join([f"{len(docs)} {entity_type}{'s' if len(docs) != 1 else ''}"
                                    for entity_type, docs in sorted(entity_types_affected.items())])

        # Also track OpenSearch indices for context
        index_map = {
            "order": "orders",
            "orderline": "orders",
            "inventory": "inventory",
            "product": "products",
            "customer": "customers",
            "store": "stores",
            "courier": "couriers",
        }
        indices_affected = {}
        for entity_type, docs in entity_types_affected.items():
            index = index_map.get(entity_type, entity_type)
            if index not in indices_affected:
                indices_affected[index] = set()
            indices_affected[index].update(docs)

        indices_summary = ", ".join([f"{idx} index" for idx in sorted(indices_affected.keys())])

        MAX_PREDICATES_TO_LOG = 3
        logger.info(
            f"  📝 [BATCH INSERT] Writing {len(triples)} triples → {entity_summary} → {indices_summary}"
        )
        for subject_id, predicates in subjects.items():
            logger.info(f"     • {subject_id}: {len(predicates)} properties ({', '.join(predicates[:MAX_PREDICATES_TO_LOG])}{'...' if len(predicates) > MAX_PREDICATES_TO_LOG else ''})")

        # Validate all triples if needed
        if self.validate:
            for triple in triples:
                validation_result = await self.validator.validate(triple)
                if not validation_result.is_valid:
                    raise TripleValidationError(validation_result)

        # Bulk insert using VALUES clause to avoid N+1 query pattern
        if not triples:
            return []

        # Build bulk insert query
        values_clauses = []
        params = {}
        for i, triple in enumerate(triples):
            values_clauses.append(
                f"(:subject_id_{i}, :predicate_{i}, :object_value_{i}, :object_type_{i})"
            )
            params[f"subject_id_{i}"] = triple.subject_id
            params[f"predicate_{i}"] = triple.predicate
            params[f"object_value_{i}"] = triple.object_value
            params[f"object_type_{i}"] = triple.object_type.value

        query = f"""
            INSERT INTO triples (subject_id, predicate, object_value, object_type)
            VALUES {', '.join(values_clauses)}
            ON CONFLICT (subject_id, predicate, object_value) DO UPDATE
            SET updated_at = NOW()
            RETURNING id, subject_id, predicate, object_value, object_type,
                      created_at, updated_at
        """

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()
        created = [
            Triple(
                id=row.id,
                subject_id=row.subject_id,
                predicate=row.predicate,
                object_value=row.object_value,
                object_type=row.object_type,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

        logger.info(
            f"  ✅ [BATCH INSERT] Successfully wrote {len(created)} triples"
        )

        return created

    async def upsert_triples_batch(self, triples: list[TripleCreate]) -> list[Triple]:
        """Upsert multiple triples in a batch - deletes old values and inserts new ones atomically.

        For each (subject_id, predicate) pair, this will:
        1. Delete any existing triples with that subject_id and predicate
        2. Insert the new triple with the new object_value

        All operations happen in a single SQL transaction.
        """
        # Validate subject_id format
        for triple in triples:
            if ":" not in triple.subject_id:
                raise ValueError(f"Invalid subject_id format: '{triple.subject_id}'. Expected format: 'prefix:id'")
            prefix = triple.subject_id.split(":", 1)[0]
            if not prefix:
                raise ValueError(f"Invalid subject_id format: '{triple.subject_id}'. Prefix cannot be empty")

        # Log transaction start
        subjects = {}
        for triple in triples:
            if triple.subject_id not in subjects:
                subjects[triple.subject_id] = []
            subjects[triple.subject_id].append(triple.predicate)

        # Determine which entity types and OpenSearch indices will be affected
        entity_types_affected = {}
        for subject_id in subjects.keys():
            prefix = subject_id.split(":", 1)[0]
            if prefix not in entity_types_affected:
                entity_types_affected[prefix] = set()
            entity_types_affected[prefix].add(subject_id)

        # Create summary showing entity types (e.g., "2 orderlines, 1 order")
        entity_summary = ", ".join([f"{len(docs)} {entity_type}{'s' if len(docs) != 1 else ''}"
                                    for entity_type, docs in sorted(entity_types_affected.items())])

        # Also track OpenSearch indices for context
        index_map = {
            "order": "orders",
            "orderline": "orders",
            "inventory": "inventory",
            "product": "products",
            "customer": "customers",
            "store": "stores",
            "courier": "couriers",
        }
        indices_affected = {}
        for entity_type, docs in entity_types_affected.items():
            index = index_map.get(entity_type, entity_type)
            if index not in indices_affected:
                indices_affected[index] = set()
            indices_affected[index].update(docs)

        indices_summary = ", ".join([f"{idx} index" for idx in sorted(indices_affected.keys())])

        MAX_PREDICATES_TO_LOG = 3
        logger.info(
            f"  📝 [BATCH UPSERT] Upserting {len(triples)} triples → {entity_summary} → {indices_summary}"
        )
        for subject_id, predicates in subjects.items():
            logger.info(f"     • {subject_id}: {len(predicates)} properties ({', '.join(predicates[:MAX_PREDICATES_TO_LOG])}{'...' if len(predicates) > MAX_PREDICATES_TO_LOG else ''})")

        # Validate if needed
        if self.validate:
            for triple in triples:
                validation_result = await self.validator.validate(triple)
                if not validation_result.is_valid:
                    raise TripleValidationError(validation_result)

        if not triples:
            return []

        # Batch delete - collect unique (subject_id, predicate) pairs
        delete_pairs = {}
        for triple in triples:
            key = (triple.subject_id, triple.predicate)
            delete_pairs[key] = True

        # Build bulk delete query
        delete_conditions = []
        delete_params = {}
        for i, (subject_id, predicate) in enumerate(delete_pairs.keys()):
            delete_conditions.append(
                f"(subject_id = :del_subject_{i} AND predicate = :del_predicate_{i})"
            )
            delete_params[f"del_subject_{i}"] = subject_id
            delete_params[f"del_predicate_{i}"] = predicate

        if delete_conditions:
            delete_query = f"""
                DELETE FROM triples
                WHERE {' OR '.join(delete_conditions)}
            """
            await self.session.execute(text(delete_query), delete_params)

        # Bulk insert
        values_clauses = []
        insert_params = {}
        for i, triple in enumerate(triples):
            values_clauses.append(
                f"(:subject_id_{i}, :predicate_{i}, :object_value_{i}, :object_type_{i})"
            )
            insert_params[f"subject_id_{i}"] = triple.subject_id
            insert_params[f"predicate_{i}"] = triple.predicate
            insert_params[f"object_value_{i}"] = triple.object_value
            insert_params[f"object_type_{i}"] = triple.object_type.value

        insert_query = f"""
            INSERT INTO triples (subject_id, predicate, object_value, object_type)
            VALUES {', '.join(values_clauses)}
            RETURNING id, subject_id, predicate, object_value, object_type,
                      created_at, updated_at
        """

        result = await self.session.execute(text(insert_query), insert_params)
        rows = result.fetchall()
        upserted = [
            Triple(
                id=row.id,
                subject_id=row.subject_id,
                predicate=row.predicate,
                object_value=row.object_value,
                object_type=row.object_type,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

        logger.info(
            f"  ✅ [BATCH UPSERT] Successfully upserted {len(upserted)} triples"
        )

        return upserted

    async def update_triple(self, triple_id: int, data: TripleUpdate) -> Optional[Triple]:
        """Update a triple's object value."""
        # Get existing triple
        existing = await self.get_triple(triple_id)
        if not existing:
            return None

        # Log transaction start for single update
        logger.info(
            f"🔵 PG_TXN_START: Writing 1 triple (update)"
        )
        logger.info(
            f"  📝 {existing.subject_id}: updating {existing.predicate} "
            f"from '{existing.object_value}' to '{data.object_value}'"
        )

        # Validate if needed
        if self.validate:
            # Create a TripleCreate to validate
            triple_create = TripleCreate(
                subject_id=existing.subject_id,
                predicate=existing.predicate,
                object_value=data.object_value,
                object_type=existing.object_type,
            )
            validation_result = await self.validator.validate(triple_create)
            if not validation_result.is_valid:
                raise TripleValidationError(validation_result)

        # Update
        result = await self.session.execute(
            text("""
                UPDATE triples
                SET object_value = :object_value, updated_at = NOW()
                WHERE id = :triple_id
                RETURNING id, subject_id, predicate, object_value, object_type,
                          created_at, updated_at
            """),
            {"triple_id": triple_id, "object_value": data.object_value},
        )
        row = result.fetchone()
        if not row:
            return None

        triple = Triple(
            id=row.id,
            subject_id=row.subject_id,
            predicate=row.predicate,
            object_value=row.object_value,
            object_type=row.object_type,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

        # Determine likely index from subject prefix (order -> orders, inventory -> inventory, etc.)
        prefix = triple.subject_id.split(":")[0]
        # Map common prefixes to their likely OpenSearch index
        index_map = {
            "order": "orders",
            "orderline": "orders",
            "inventory": "inventory",
            "product": "products",
            "customer": "customers",
            "store": "stores",
            "courier": "couriers",
        }
        likely_index = index_map.get(prefix, prefix)

        logger.info(
            f"✅ PG_TXN_END: Successfully updated 1 triple → will update {likely_index} index for {triple.subject_id}"
        )

        return triple

    async def delete_triple(self, triple_id: int) -> bool:
        """Delete a triple."""
        result = await self.session.execute(
            text("DELETE FROM triples WHERE id = :triple_id"),
            {"triple_id": triple_id},
        )
        return result.rowcount > 0

    async def delete_subject(self, subject_id: str) -> int:
        """Delete all triples for a subject."""
        result = await self.session.execute(
            text("DELETE FROM triples WHERE subject_id = :subject_id"),
            {"subject_id": subject_id},
        )
        return result.rowcount

    async def list_subjects(
        self, class_name: Optional[str] = None, prefix: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[str]:
        """List distinct subject IDs, optionally filtered by class or prefix."""
        # Determine prefix from class_name if provided
        filter_prefix = prefix
        if class_name and not filter_prefix:
            ont_class = await self.ontology_service.get_class_by_name(class_name)
            if not ont_class:
                return []
            filter_prefix = ont_class.prefix

        if filter_prefix:
            result = await self.session.execute(
                text("""
                    SELECT DISTINCT subject_id
                    FROM triples
                    WHERE subject_id LIKE :prefix_pattern
                    ORDER BY subject_id
                    LIMIT :limit OFFSET :offset
                """),
                {"prefix_pattern": f"{filter_prefix}:%", "limit": limit, "offset": offset},
            )
        else:
            result = await self.session.execute(
                text("""
                    SELECT DISTINCT subject_id
                    FROM triples
                    ORDER BY subject_id
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": offset},
            )

        rows = result.fetchall()
        return [row.subject_id for row in rows]

    async def get_subject_counts(self) -> dict:
        """Get counts of subjects by entity type (prefix) and total count."""
        result = await self.session.execute(
            text("""
                SELECT
                    SPLIT_PART(subject_id, ':', 1) AS entity_type,
                    COUNT(DISTINCT subject_id) AS count
                FROM triples
                GROUP BY SPLIT_PART(subject_id, ':', 1)
                ORDER BY count DESC, entity_type
            """)
        )
        rows = result.fetchall()

        by_type = {row.entity_type: row.count for row in rows}
        total = sum(by_type.values())

        return {
            "total": total,
            "by_type": by_type,
        }
