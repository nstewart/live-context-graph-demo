"""Triples API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.client import get_pg_session_factory
from src.triples.models import (
    ObjectType,
    SubjectInfo,
    Triple,
    TripleCreate,
    TripleFilter,
    TripleUpdate,
    ValidationResult,
)
from src.triples.service import TripleService, TripleValidationError

router = APIRouter(prefix="/triples", tags=["Triples"])
logger = logging.getLogger(__name__)


async def get_session() -> AsyncSession:
    """Dependency to get database session."""
    factory = get_pg_session_factory()
    async with factory() as session:
        logger.info("🔵 [TRANSACTION START] PostgreSQL write transaction started")
        try:
            yield session
            await session.commit()
            logger.info("✅ [TRANSACTION END] PostgreSQL transaction committed successfully")
        except Exception as e:
            logger.error(f"❌ [TRANSACTION] PostgreSQL transaction failed, rolling back: {e}")
            await session.rollback()
            raise


async def get_triple_service(session: AsyncSession = Depends(get_session)) -> TripleService:
    """Dependency to get triple service."""
    return TripleService(session)


# =============================================================================
# Triples CRUD
# =============================================================================


@router.get("", response_model=list[Triple])
async def list_triples(
    subject_id: Optional[str] = None,
    predicate: Optional[str] = None,
    object_value: Optional[str] = None,
    object_type: Optional[ObjectType] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TripleService = Depends(get_triple_service),
):
    """List triples with optional filtering."""
    filter_ = TripleFilter(
        subject_id=subject_id,
        predicate=predicate,
        object_value=object_value,
        object_type=object_type,
    )
    return await service.list_triples(filter_=filter_, limit=limit, offset=offset)


@router.get("/{triple_id}", response_model=Triple)
async def get_triple(triple_id: int, service: TripleService = Depends(get_triple_service)):
    """Get a triple by ID."""
    triple = await service.get_triple(triple_id)
    if not triple:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Triple not found")
    return triple


@router.post("", response_model=Triple, status_code=status.HTTP_201_CREATED)
async def create_triple(
    data: TripleCreate,
    validate: bool = Query(default=True, description="Validate against ontology"),
    service: TripleService = Depends(get_triple_service),
):
    """
    Create a new triple.

    If validate=true (default), the triple will be validated against the ontology schema:
    - Subject prefix must correspond to a valid class
    - Predicate must exist and apply to the subject's class
    - Object type must match the predicate's range
    """
    service.validate = validate
    try:
        return await service.create_triple(data)
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


@router.post("/batch", response_model=list[Triple], status_code=status.HTTP_201_CREATED)
async def create_triples_batch(
    triples: list[TripleCreate],
    validate: bool = Query(default=True, description="Validate against ontology"),
    service: TripleService = Depends(get_triple_service),
):
    """Create multiple triples in a batch."""
    service.validate = validate
    try:
        return await service.create_triples_batch(triples)
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


@router.put("/batch", response_model=list[Triple])
async def upsert_triples_batch(
    triples: list[TripleCreate],
    validate: bool = Query(default=True, description="Validate against ontology"),
    service: TripleService = Depends(get_triple_service),
):
    """
    Upsert multiple triples in a batch (atomic transaction).

    For each (subject_id, predicate) pair, this will:
    1. Delete any existing triples with that subject_id and predicate
    2. Insert the new triple with the new object_value

    All operations happen in a single SQL transaction - no duplicates, no race conditions.
    """
    service.validate = validate
    try:
        return await service.upsert_triples_batch(triples)
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


@router.patch("/{triple_id}", response_model=Triple)
async def update_triple(
    triple_id: int,
    data: TripleUpdate,
    service: TripleService = Depends(get_triple_service),
):
    """Update a triple's object value."""
    try:
        updated = await service.update_triple(triple_id, data)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Triple not found")
        return updated
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


@router.delete("/{triple_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_triple(triple_id: int, service: TripleService = Depends(get_triple_service)):
    """Delete a triple."""
    deleted = await service.delete_triple(triple_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Triple not found")


# =============================================================================
# Subjects
# =============================================================================


@router.get("/subjects/counts")
async def get_subject_counts(service: TripleService = Depends(get_triple_service)):
    """
    Get counts of subjects by entity type.

    Returns total count and breakdown by entity type (prefix).
    Useful for building entity type filters in the UI.
    """
    return await service.get_subject_counts()


@router.get("/subjects/list", response_model=list[str])
async def list_subjects(
    class_name: Optional[str] = Query(default=None, description="Filter by class name"),
    prefix: Optional[str] = Query(default=None, description="Filter by subject prefix (e.g., 'order')"),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TripleService = Depends(get_triple_service),
):
    """List distinct subject IDs, optionally filtered by class or prefix."""
    return await service.list_subjects(class_name=class_name, prefix=prefix, limit=limit, offset=offset)


@router.get("/subjects/{subject_id:path}", response_model=SubjectInfo)
async def get_subject(subject_id: str, service: TripleService = Depends(get_triple_service)):
    """Get all triples for a subject."""
    return await service.get_subject(subject_id)


@router.delete("/subjects/{subject_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(subject_id: str, service: TripleService = Depends(get_triple_service)):
    """Delete all triples for a subject."""
    count = await service.delete_subject(subject_id)
    if count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")


# =============================================================================
# Validation
# =============================================================================


@router.post("/validate", response_model=ValidationResult)
async def validate_triple(
    data: TripleCreate,
    service: TripleService = Depends(get_triple_service),
):
    """
    Validate a triple against the ontology without creating it.

    Returns validation result with any errors found.
    """
    return await service.validator.validate(data)
