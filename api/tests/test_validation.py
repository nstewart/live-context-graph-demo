"""Triple validation tests."""

import pytest

from src.triples.models import ObjectType, TripleCreate, ValidationErrorDetail, ValidationResult
from src.triples.validator import TripleValidator


class MockOntologyService:
    """Mock ontology service for testing."""

    def __init__(self):
        self.classes = {
            1: {"id": 1, "class_name": "Customer", "prefix": "customer", "parent_class_id": None},
            2: {"id": 2, "class_name": "Order", "prefix": "order", "parent_class_id": None},
            3: {"id": 3, "class_name": "Store", "prefix": "store", "parent_class_id": None},
        }
        self.properties = {
            "customer_name": {
                "prop_name": "customer_name",
                "domain_class_id": 1,
                "domain_class_name": "Customer",
                "range_kind": "string",
                "range_class_id": None,
            },
            "order_status": {
                "prop_name": "order_status",
                "domain_class_id": 2,
                "domain_class_name": "Order",
                "range_kind": "string",
                "range_class_id": None,
            },
            "placed_by": {
                "prop_name": "placed_by",
                "domain_class_id": 2,
                "domain_class_name": "Order",
                "range_kind": "entity_ref",
                "range_class_id": 1,
            },
        }

    async def get_class(self, class_id: int):
        data = self.classes.get(class_id)
        if data:
            return type("OntologyClass", (), data)()
        return None

    async def get_class_by_prefix(self, prefix: str):
        for data in self.classes.values():
            if data["prefix"] == prefix:
                return type("OntologyClass", (), data)()
        return None

    async def get_property_by_name(self, prop_name: str):
        data = self.properties.get(prop_name)
        if data:
            return type("OntologyProperty", (), data)()
        return None


@pytest.fixture
def validator():
    """Create validator with mock ontology."""
    return TripleValidator(MockOntologyService())


@pytest.mark.asyncio
async def test_valid_string_property(validator):
    """Test validation passes for valid string property."""
    triple = TripleCreate(
        subject_id="customer:123",
        predicate="customer_name",
        object_value="John Doe",
        object_type=ObjectType.STRING,
    )
    result = await validator.validate(triple)
    assert result.is_valid
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_valid_entity_ref(validator):
    """Test validation passes for valid entity reference."""
    triple = TripleCreate(
        subject_id="order:FM-1001",
        predicate="placed_by",
        object_value="customer:123",
        object_type=ObjectType.ENTITY_REF,
    )
    result = await validator.validate(triple)
    assert result.is_valid


@pytest.mark.asyncio
async def test_unknown_predicate(validator):
    """Test validation fails for unknown predicate."""
    triple = TripleCreate(
        subject_id="customer:123",
        predicate="unknown_property",
        object_value="value",
        object_type=ObjectType.STRING,
    )
    result = await validator.validate(triple)
    assert not result.is_valid
    assert any(e.error_type == "unknown_predicate" for e in result.errors)


@pytest.mark.asyncio
async def test_domain_violation(validator):
    """Test validation fails for domain violation."""
    # Using customer_name on an order (wrong domain)
    triple = TripleCreate(
        subject_id="order:FM-1001",
        predicate="customer_name",
        object_value="John",
        object_type=ObjectType.STRING,
    )
    result = await validator.validate(triple)
    assert not result.is_valid
    assert any(e.error_type == "domain_violation" for e in result.errors)


@pytest.mark.asyncio
async def test_type_mismatch(validator):
    """Test validation fails for type mismatch."""
    triple = TripleCreate(
        subject_id="customer:123",
        predicate="customer_name",
        object_value="John",
        object_type=ObjectType.INT,  # Should be string
    )
    result = await validator.validate(triple)
    assert not result.is_valid
    assert any(e.error_type == "range_type_mismatch" for e in result.errors)


@pytest.mark.asyncio
async def test_unknown_class(validator):
    """Test validation fails for unknown subject class."""
    triple = TripleCreate(
        subject_id="unknown:123",
        predicate="customer_name",
        object_value="John",
        object_type=ObjectType.STRING,
    )
    result = await validator.validate(triple)
    assert not result.is_valid
    assert any(e.error_type == "unknown_class" for e in result.errors)


def test_invalid_literal_int():
    """Test integer literal validation."""
    validator = TripleValidator(MockOntologyService())
    error = validator._validate_literal("not_a_number", ObjectType.INT)
    assert error is not None
    assert error.error_type == "invalid_literal"


def test_valid_literal_int():
    """Test valid integer literal."""
    validator = TripleValidator(MockOntologyService())
    error = validator._validate_literal("42", ObjectType.INT)
    assert error is None


def test_invalid_literal_bool():
    """Test boolean literal validation."""
    validator = TripleValidator(MockOntologyService())
    error = validator._validate_literal("yes", ObjectType.BOOL)
    assert error is not None


def test_valid_literal_bool():
    """Test valid boolean literal."""
    validator = TripleValidator(MockOntologyService())
    assert validator._validate_literal("true", ObjectType.BOOL) is None
    assert validator._validate_literal("false", ObjectType.BOOL) is None
