"""Ghost Hunter discovery package."""

from ghost_hunter.discovery.flask import discover_project, write_discovery
from ghost_hunter.discovery.project import detect_project_context, is_example_or_fixture
from ghost_hunter.discovery.audit import audit_repository_routes, estimate_duplicate_blocks

__all__ = [
    "discover_project",
    "write_discovery",
    "detect_project_context",
    "is_example_or_fixture",
    "audit_repository_routes",
    "estimate_duplicate_blocks",
]
