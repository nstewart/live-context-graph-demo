"""Tests to validate requirements.txt is installable without conflicts.

This test ensures that dependency version specifications don't have conflicts
that would break Docker builds or fresh installs.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest


# Known incompatible version combinations that have caused issues
KNOWN_CONFLICTS = [
    # pytest-asyncio 0.23.x requires pytest<8
    (r"pytest==8\.", r"pytest-asyncio==0\.23\."),
    (r"pytest>=8", r"pytest-asyncio==0\.23\."),
]


class TestRequirementsConsistency:
    """Validate requirements.txt files are installable."""

    @pytest.fixture
    def requirements_path(self) -> Path:
        """Get path to requirements.txt."""
        return Path(__file__).parent.parent / "requirements.txt"

    @pytest.fixture
    def requirements_content(self, requirements_path: Path) -> str:
        """Read requirements file content."""
        return requirements_path.read_text()

    def test_requirements_file_exists(self, requirements_path: Path):
        """Requirements file should exist."""
        assert requirements_path.exists(), f"requirements.txt not found at {requirements_path}"

    def test_no_known_version_conflicts(self, requirements_content: str):
        """Check for known incompatible version combinations."""
        for pattern1, pattern2 in KNOWN_CONFLICTS:
            has_pattern1 = re.search(pattern1, requirements_content)
            has_pattern2 = re.search(pattern2, requirements_content)

            if has_pattern1 and has_pattern2:
                pytest.fail(
                    f"Known version conflict detected:\n"
                    f"  - {has_pattern1.group(0)}\n"
                    f"  - {has_pattern2.group(0)}\n"
                    f"These versions are incompatible. "
                    f"pytest-asyncio 0.23.x requires pytest<8."
                )

    def test_requirements_resolvable(self, requirements_path: Path):
        """Requirements should be resolvable by pip (if --dry-run available)."""
        # Try with --dry-run first (newer pip versions)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "-r", str(requirements_path)],
            capture_output=True,
            text=True,
        )

        # If --dry-run not available, skip this test
        if "no such option: --dry-run" in result.stderr:
            pytest.skip("pip --dry-run not available in this pip version")

        # Check for resolution errors
        assert "ResolutionImpossible" not in result.stderr, (
            f"Dependency resolution failed:\n{result.stderr}"
        )
        assert "conflicting dependencies" not in result.stderr.lower(), (
            f"Conflicting dependencies found:\n{result.stderr}"
        )

    def test_no_duplicate_packages(self, requirements_path: Path):
        """Requirements file should not have duplicate package entries."""
        packages = {}
        with open(requirements_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Extract package name (before any version specifier)
                package_name = line.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].lower()

                if package_name in packages:
                    pytest.fail(
                        f"Duplicate package '{package_name}' found on lines "
                        f"{packages[package_name]} and {line_num}"
                    )
                packages[package_name] = line_num

    def test_installed_packages_are_compatible(self):
        """Installed packages should pass pip check."""
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
        )

        # pip check returns 0 if no broken dependencies
        assert result.returncode == 0, (
            f"Installed packages have compatibility issues:\n{result.stdout}"
        )
