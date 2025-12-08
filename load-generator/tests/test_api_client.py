"""Tests for API client."""

import pytest
from datetime import datetime, timedelta

from loadgen.api_client import FreshMartAPIClient


@pytest.mark.asyncio
async def test_client_context_manager():
    """Test that client works as context manager."""
    async with FreshMartAPIClient() as client:
        assert client.base_url == "http://localhost:8080"


@pytest.mark.asyncio
async def test_client_custom_base_url():
    """Test client with custom base URL."""
    async with FreshMartAPIClient(base_url="http://example.com:9000") as client:
        assert client.base_url == "http://example.com:9000"


@pytest.mark.asyncio
async def test_client_strips_trailing_slash():
    """Test that trailing slash is stripped from base URL."""
    async with FreshMartAPIClient(base_url="http://example.com/") as client:
        assert client.base_url == "http://example.com"


def test_client_initialization():
    """Test client initialization."""
    client = FreshMartAPIClient(base_url="http://localhost:8080", timeout=60.0)
    assert client.base_url == "http://localhost:8080"
    assert client.timeout == 60.0
