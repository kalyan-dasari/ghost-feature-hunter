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
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


@dataclass
class ClientCall:
    path: str
    method: str
    source: str
    line: int
    raw: str
    framework: str = "generic"
    caller_function: str = ""
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"
    target_service: str = ""
    call_type: str = "local"  # "local", "matching_service_route", "external_service_call", "reverse_proxy_candidate"


@dataclass
class ModelDefinition:
    name: str
    source: str
    line: int
    framework: str
    is_example: bool = False
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


@dataclass
class ComponentDefinition:
    name: str
    source: str
    line: int
    framework: str
    has_render: bool = True
    is_placeholder_render: bool = False
    placeholder_text: str = ""
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


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
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


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
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


@dataclass
class SymbolDefinition:
    name: str
    symbol_type: str  # "function", "class", "variable", "service"
    source: str
    line: int
    is_exported: bool = False
    has_local_callers: bool = False
    caller_count: int = 0
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


@dataclass
class FeatureFlagDefinition:
    name: str
    source: str
    line: int
    is_defined: bool = True
    has_consumers: bool = False
    consumer_count: int = 0
    raw: str = ""
    source_role: str = "application_source"
    app_name: str = ""
    scope: str = "primary_application"


@dataclass
class ApplicationBoundary:
    app_name: str
    relative_path: str
    absolute_path: str
    manifests: list[str] = field(default_factory=list)
    is_root: bool = False
    primary_role: str = "application_source"


@dataclass
class FrameworkCapability:
    language: str
    framework: str
    detected: bool
    status: str  # "supported", "partial", "inventory-only", "not detected"
    capabilities: dict[str, bool] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
