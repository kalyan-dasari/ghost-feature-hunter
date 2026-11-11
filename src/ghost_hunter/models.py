"""Validated journey and evidence models shared by the engine and adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class AdapterName(StrEnum):
    HTTP = "http"
    DATABASE = "database"
    BROWSER = "browser"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class JourneyStep(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    checkpoint: str = Field(min_length=1)
    adapter: AdapterName
    expected_behavior: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class Journey(StrictModel):
    schema_version: str = "1.0"
    feature: str = Field(min_length=1)
    description: str = ""
    steps: list[JourneyStep] = Field(min_length=1, max_length=100)

    @field_validator("steps")
    @classmethod
    def unique_step_ids(cls, steps: list[JourneyStep]) -> list[JourneyStep]:
        ids = [step.id for step in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("journey step ids must be unique")
        return steps


class EvidenceItem(StrictModel):
    reference: str = Field(min_length=1)
    observed_at: datetime = Field(default_factory=utc_now)
    summary: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class CheckResult(StrictModel):
    feature: str
    checkpoint_id: str
    checkpoint: str
    expected_behavior: str
    actual_observation: str
    status: Status
    evidence: list[EvidenceItem] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)
    reproducibility: str
    confidence_rationale: str
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def observed_results_need_evidence(self) -> "CheckResult":
        if self.status in {Status.PASS, Status.FAIL} and not self.evidence:
            raise ValueError("PASS and FAIL results require at least one evidence item")
        return self


class ReportSummary(StrictModel):
    total: int
    pass_count: int
    fail_count: int
    unknown_count: int


class AuditReport(StrictModel):
    schema_version: str = "1.0"
    tool_version: str
    project_path: str
    generated_at: datetime = Field(default_factory=utc_now)
    results: list[CheckResult]
    summary: ReportSummary
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def summary_must_match_results(self) -> "AuditReport":
        expected = ReportSummary(
            total=len(self.results),
            pass_count=sum(result.status is Status.PASS for result in self.results),
            fail_count=sum(result.status is Status.FAIL for result in self.results),
            unknown_count=sum(result.status is Status.UNKNOWN for result in self.results),
        )
        if self.summary != expected:
            raise ValueError("report summary counts must match the result statuses")
        return self

    @classmethod
    def build(
        cls,
        project_path: Path,
        results: list[CheckResult],
        limitations: list[str] | None = None,
    ) -> "AuditReport":
        results = list(results)
        return cls(
            tool_version=_tool_version(),
            project_path=str(project_path.resolve()),
            results=results,
            summary=ReportSummary(
                total=len(results),
                pass_count=sum(r.status is Status.PASS for r in results),
                fail_count=sum(r.status is Status.FAIL for r in results),
                unknown_count=sum(r.status is Status.UNKNOWN for r in results),
            ),
            limitations=limitations or [],
        )


def _tool_version() -> str:
    from ghost_hunter import __version__

    return __version__
