"""Data models for multi-language discovery and feature connection analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RouteDefinition:
    path: str
    methods: list[str]
    function: str
    source: str
    line: int
    framework: str
    is_example: bool = False
    prefix: str = ""
    is_empty_or_unfinished: bool = False
    raw_decorator: str = ""


@dataclass
class ClientCall:
    path: str
    method: str
    source: str
    line: int
    raw: str
    framework: str = "generic"
    caller_function: str = ""


@dataclass
class ModelDefinition:
    name: str
    source: str
    line: int
    framework: str
    is_example: bool = False


@dataclass
class ComponentDefinition:
    name: str
    source: str
    line: int
    framework: str
    has_render: bool = True
    is_placeholder_render: bool = False
    placeholder_text: str = ""


@dataclass
class UIAction:
    action_type: str  # "button", "link", "form"
    label: str
    target: str  # url, route, or handler name
    source: str
    line: int
    raw: str
    is_empty_handler: bool = False
    has_handler: bool = True


@dataclass
class UnfinishedItem:
    item_type: str  # "empty_function", "not_implemented", "todo_marker", "empty_handler", "silent_catch", "placeholder_component"
    name: str
    source: str
    line: int
    evidence: str
    explanation: str
    confidence: str  # "High", "Medium", "Low"
    is_abstract_or_protocol: bool = False
    why_intentional: str = ""


@dataclass
class SymbolDefinition:
    name: str
    symbol_type: str  # "function", "class", "variable", "service"
    source: str
    line: int
    is_exported: bool = False
    has_local_callers: bool = False
    caller_count: int = 0


@dataclass
class FrameworkCapability:
    language: str
    framework: str
    detected: bool
    status: str  # "supported", "partial", "inventory-only", "not detected"
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

