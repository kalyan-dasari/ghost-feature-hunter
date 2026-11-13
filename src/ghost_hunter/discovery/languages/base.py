"""Base class for language and framework discovery adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.models import (
    ClientCall,
    ComponentDefinition,
    ModelDefinition,
    RouteDefinition,
    SymbolDefinition,
    UIAction,
    UnfinishedItem,
)


class BaseLanguageAdapter(ABC):
    """Abstract base class for language-specific static analysis."""

    @property
    @abstractmethod
    def language(self) -> str:
        """Name of the programming language (e.g. 'Python', 'JavaScript')."""
        ...

    @property
    @abstractmethod
    def file_extensions(self) -> set[str]:
        """Set of file extensions handled by this adapter (e.g. {'.py', '.pyw'})."""
        ...

    @property
    @abstractmethod
    def supported_frameworks(self) -> list[str]:
        """List of framework names supported by this adapter."""
        ...

    @abstractmethod
    def get_capabilities(self) -> dict[str, bool]:
        """Map of analysis capability flags implemented by this adapter."""
        ...

    @abstractmethod
    def get_limitations(self) -> list[str]:
        """List of explicit limitations for this adapter."""
        ...

    @abstractmethod
    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        """Identify frameworks present in the scanned files."""
        ...

    @abstractmethod
    def analyze_file(
        self,
        file_path: Path,
        root: Path,
    ) -> dict[str, Any]:
        """Perform static analysis on a single file.

        Returns a dictionary containing:
        - "routes": list[RouteDefinition]
        - "client_calls": list[ClientCall]
        - "models": list[ModelDefinition]
        - "components": list[ComponentDefinition]
        - "ui_actions": list[UIAction]
        - "unfinished": list[UnfinishedItem]
        - "symbols": list[SymbolDefinition]
        - "imports": list[str]
        - "exports": list[str]
        """
        ...

