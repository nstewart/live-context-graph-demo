"""Unit tests for TripleService."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.triples.models import ObjectType, Triple, TripleCreate, TripleFilter, ValidationResult
from src.triples.service import TripleService, TripleValidationError


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    """Create TripleService with mock session."""
    return TripleService(mock_session, validate=False)


@pytest.fixture
def validating_service(mock_session):
    """Create TripleService with validation enabled."""
    return TripleService(mock_session, validate=True)


class TestListTriples:
    """Tests for TripleService.list_triples."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_triples(self, service, mock_session):
        """Returns empty list when no triples exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_triples()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_triples_with_limit_and_offset(self, service, mock_session):
        """Returns triples respecting limit and offset."""
        now = datetime.now()
        mock_rows = [
            MagicMock(
                id=1,
                subject_id="customer:123",
                predicate="customer_name",
                object_value="John Doe",
                object_type="string",
                created_at=now,
                updated_at=now,
            )
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        result = await service.list_triples(limit=10, offset=5)

        assert len(result) == 1
        assert result[0].subject_id == "customer:123"

    @pytest.mark.asyncio
    async def test_filters_by_subject_id(self, service, mock_session):
        """Filters triples by subject_id."""
        now = datetime.now()
        mock_rows = [
            MagicMock(
                id=1,
                subject_id="customer:123",
                predicate="customer_name",
                object_value="John",
                object_type="string",
                created_at=now,
                updated_at=now,
            )
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        filter_ = TripleFilter(subject_id="customer:123")
        result = await service.list_triples(filter_=filter_)

        assert len(result) == 1
        # Verify subject_id was passed to query
        call_args = mock_session.execute.call_args
        assert "subject_id" in call_args[0][1] or call_args[1].get("subject_id")

    @pytest.mark.asyncio
    async def test_filters_by_predicate(self, service, mock_session):
        """Filters triples by predicate."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        filter_ = TripleFilter(predicate="customer_name")
        await service.list_triples(filter_=filter_)

        mock_session.execute.assert_called_once()


class TestGetTriple:
    """Tests for TripleService.get_triple."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service, mock_session):
        """Returns None when triple doesn't exist."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.get_triple(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_triple_when_found(self, service, mock_session):
        """Returns triple when it exists."""
        now = datetime.now()
        mock_row = MagicMock(
            id=1,
            subject_id="customer:123",
            predicate="customer_name",
            object_value="John Doe",
            object_type="string",
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session.execute.return_value = mock_result

        result = await service.get_triple(1)

        assert result is not None
        assert result.id == 1
        assert result.subject_id == "customer:123"


class TestCreateTriple:
    """Tests for TripleService.create_triple."""

    @pytest.mark.asyncio
    async def test_creates_triple_without_validation(self, service, mock_session):
        """Creates triple when validation is disabled."""
        now = datetime.now()
        mock_row = MagicMock(
            id=1,
            subject_id="test:123",
            predicate="any_prop",
            object_value="Value",
            object_type="string",
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session.execute.return_value = mock_result

        data = TripleCreate(
            subject_id="test:123",
            predicate="any_prop",
            object_value="Value",
            object_type=ObjectType.STRING,
        )
        result = await service.create_triple(data)

        assert result.subject_id == "test:123"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_triple_when_validation_enabled(self, validating_service, mock_session):
        """Validates triple before creation when enabled."""
        from src.triples.models import ValidationErrorDetail

        # Mock validator to return invalid result
        mock_validation_result = ValidationResult(
            is_valid=False,
            errors=[ValidationErrorDetail(error_type="test_error", message="Test error")]
        )
        mock_validator = AsyncMock()
        mock_validator.validate.return_value = mock_validation_result
        validating_service._validator = mock_validator

        data = TripleCreate(
            subject_id="invalid:123",
            predicate="bad_prop",
            object_value="Value",
            object_type=ObjectType.STRING,
        )

        with pytest.raises(TripleValidationError):
            await validating_service.create_triple(data)


class TestDeleteTriple:
    """Tests for TripleService.delete_triple."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, service, mock_session):
        """Returns True when triple is deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await service.delete_triple(1)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, service, mock_session):
        """Returns False when triple doesn't exist."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await service.delete_triple(999)

        assert result is False


class TestDeleteSubject:
    """Tests for TripleService.delete_subject."""

    @pytest.mark.asyncio
    async def test_returns_count_of_deleted_triples(self, service, mock_session):
        """Returns count of deleted triples."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        result = await service.delete_subject("customer:123")

        assert result == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_triples(self, service, mock_session):
        """Returns 0 when no triples exist for subject."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await service.delete_subject("nonexistent:999")

        assert result == 0


class TestListSubjects:
    """Tests for TripleService.list_subjects."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_subjects(self, service, mock_session):
        """Returns empty list when no subjects exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_subjects()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_subject_ids(self, service, mock_session):
        """Returns list of subject IDs."""
        mock_rows = [
            MagicMock(subject_id="customer:101"),
            MagicMock(subject_id="customer:102"),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        result = await service.list_subjects()

        assert result == ["customer:101", "customer:102"]

    @pytest.mark.asyncio
    async def test_filters_by_class_name(self, service, mock_session):
        """Filters subjects by class name."""
        # Mock ontology service for class lookup
        now = datetime.now()

        # Create a proper mock row object with the required attributes
        class MockOntClass:
            id = 1
            class_name = "Customer"
            prefix = "customer"
            description = "A customer"
            parent_class_id = None
            created_at = now
            updated_at = now

        # First call returns ontology class, second returns subjects
        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # Ontology class lookup
                mock_result.fetchone.return_value = MockOntClass()
            else:
                # Subject list
                mock_result.fetchall.return_value = [MagicMock(subject_id="customer:101")]
            return mock_result

        mock_session.execute = mock_execute

        result = await service.list_subjects(class_name="Customer")

        assert len(result) == 1


class TestCreateTriplesBatch:
    """Tests for TripleService.create_triples_batch."""

    @pytest.mark.asyncio
    async def test_creates_multiple_triples(self, service, mock_session):
        """Creates multiple triples in batch."""
        now = datetime.now()

        # The service uses bulk insert with fetchall() to get all returned rows
        rows = [
            MagicMock(
                id=1,
                subject_id="customer:101",
                predicate="customer_name",
                object_value="Name 1",
                object_type="string",
                created_at=now,
                updated_at=now,
            ),
            MagicMock(
                id=2,
                subject_id="customer:102",
                predicate="customer_name",
                object_value="Name 2",
                object_type="string",
                created_at=now,
                updated_at=now,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        triples = [
            TripleCreate(
                subject_id="customer:101",
                predicate="customer_name",
                object_value="Name 1",
                object_type=ObjectType.STRING,
            ),
            TripleCreate(
                subject_id="customer:102",
                predicate="customer_name",
                object_value="Name 2",
                object_type=ObjectType.STRING,
            ),
        ]

        result = await service.create_triples_batch(triples)

        assert len(result) == 2


class TestUpsertTriplesBatch:
    """Tests for TripleService.upsert_triples_batch."""

    @pytest.mark.asyncio
    async def test_validates_subject_id_format(self, service, mock_session):
        """Validates subject_id contains colon separator."""
        from pydantic import ValidationError

        # Validation happens at model creation time (Pydantic field_validator)
        with pytest.raises(ValidationError, match="subject_id must be in format"):
            TripleCreate(
                subject_id="invalid_no_colon",
                predicate="test_prop",
                object_value="value",
                object_type=ObjectType.STRING,
            )

    @pytest.mark.asyncio
    async def test_validates_subject_id_has_prefix(self, service, mock_session):
        """Validates subject_id has non-empty prefix."""
        triples = [
            TripleCreate(
                subject_id=":123",
                predicate="test_prop",
                object_value="value",
                object_type=ObjectType.STRING,
            )
        ]

        with pytest.raises(ValueError, match="Prefix cannot be empty"):
            await service.upsert_triples_batch(triples)

    @pytest.mark.asyncio
    async def test_upserts_multiple_triples_atomically(self, service, mock_session):
        """Upserts multiple triples in single transaction."""
        now = datetime.now()

        # Mock select (for existing values), delete, and insert operations
        # 1. SELECT existing values
        select_result = MagicMock()
        select_result.fetchall.return_value = []  # No existing values

        # 2. DELETE
        delete_result = MagicMock()
        delete_result.rowcount = 2

        # 3. INSERT
        insert_rows = [
            MagicMock(
                id=1,
                subject_id="order:1",
                predicate="status",
                object_value="shipped",
                object_type="string",
                created_at=now,
                updated_at=now,
            ),
            MagicMock(
                id=2,
                subject_id="order:2",
                predicate="status",
                object_value="pending",
                object_type="string",
                created_at=now,
                updated_at=now,
            ),
        ]
        insert_result = MagicMock()
        insert_result.fetchall.return_value = insert_rows

        # Order: select existing, delete, insert
        mock_session.execute = AsyncMock(side_effect=[select_result, delete_result, insert_result])

        triples = [
            TripleCreate(
                subject_id="order:1",
                predicate="status",
                object_value="shipped",
                object_type=ObjectType.STRING,
            ),
            TripleCreate(
                subject_id="order:2",
                predicate="status",
                object_value="pending",
                object_type=ObjectType.STRING,
            ),
        ]

        result = await service.upsert_triples_batch(triples)

        assert len(result) == 2
        assert result[0].subject_id == "order:1"
        assert result[0].object_value == "shipped"
        assert result[1].subject_id == "order:2"
        assert result[1].object_value == "pending"

        # Verify select, delete, and insert were called
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_upsert_with_validation_enabled(self, validating_service, mock_session):
        """Validates triples before upserting when validation enabled."""
        from src.triples.models import ValidationErrorDetail

        # Mock validator to return invalid result
        mock_validation_result = ValidationResult(
            is_valid=False,
            errors=[ValidationErrorDetail(error_type="test_error", message="Test error")]
        )
        mock_validator = AsyncMock()
        # The validate method needs to return the result directly (it's awaited)
        mock_validator.validate = AsyncMock(return_value=mock_validation_result)
        validating_service._validator = mock_validator

        # Need to mock the select query that happens before validation
        select_result = MagicMock()
        select_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=select_result)

        triples = [
            TripleCreate(
                subject_id="order:1",
                predicate="invalid_prop",
                object_value="value",
                object_type=ObjectType.STRING,
            )
        ]

        with pytest.raises(TripleValidationError):
            await validating_service.upsert_triples_batch(triples)

    @pytest.mark.asyncio
    async def test_upsert_handles_empty_list(self, service, mock_session):
        """Handles empty triple list gracefully."""
        result = await service.upsert_triples_batch([])

        assert result == []
        # Should not make any database calls
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_deduplicates_delete_pairs(self, service, mock_session):
        """Deduplicates (subject_id, predicate) pairs for deletion."""
        now = datetime.now()

        # 1. SELECT existing values
        select_result = MagicMock()
        select_result.fetchall.return_value = []  # No existing values

        # 2. DELETE
        delete_result = MagicMock()
        delete_result.rowcount = 1

        # 3. INSERT
        insert_rows = [
            MagicMock(
                id=1,
                subject_id="order:1",
                predicate="status",
                object_value="shipped",
                object_type="string",
                created_at=now,
                updated_at=now,
            ),
            MagicMock(
                id=2,
                subject_id="order:1",
                predicate="status",
                object_value="delivered",
                object_type="string",
                created_at=now,
                updated_at=now,
            ),
        ]
        insert_result = MagicMock()
        insert_result.fetchall.return_value = insert_rows

        # Order: select existing, delete, insert
        mock_session.execute = AsyncMock(side_effect=[select_result, delete_result, insert_result])

        # Two triples with same subject_id and predicate
        triples = [
            TripleCreate(
                subject_id="order:1",
                predicate="status",
                object_value="shipped",
                object_type=ObjectType.STRING,
            ),
            TripleCreate(
                subject_id="order:1",
                predicate="status",
                object_value="delivered",
                object_type=ObjectType.STRING,
            ),
        ]

        result = await service.upsert_triples_batch(triples)

        # Should still insert both
        assert len(result) == 2
        # Verify all 3 operations were called: select, delete, insert
        assert mock_session.execute.call_count == 3


class TestTripleValidationError:
    """Tests for TripleValidationError exception."""

    def test_stores_validation_result(self):
        """Exception stores validation result."""
        from src.triples.models import ValidationErrorDetail

        errors = [ValidationErrorDetail(error_type="test", message="Test error")]
        validation_result = ValidationResult(is_valid=False, errors=errors)

        error = TripleValidationError(validation_result)

        assert error.validation_result == validation_result
        assert "validation failed" in str(error).lower()
