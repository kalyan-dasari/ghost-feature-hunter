"""Shared synchronous adapter interface and safe result construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ghost_hunter.config import HunterConfig
from ghost_hunter.models import CheckResult, EvidenceItem, Journey, JourneyStep, Status, utc_now


@dataclass(frozen=True)
class AdapterContext:
    project_root: Path
    config: HunterConfig
    base_url_override: str | None = None
    allow_writes: bool = False
    approve_production: bool = False

    @property
    def base_url(self) -> str | None:
        return self.base_url_override or self.config.base_url


def make_result(
    journey: Journey,
    step: JourneyStep,
    status: Status,
    actual: str,
    rationale: str,
    *,
    evidence: list[EvidenceItem] | None = None,
    start_time: float | None = None,
    limitations: list[str] | None = None,
) -> CheckResult:
    import time
    from ghost_hunter import __version__

    elapsed = max(0, int((time.monotonic() - start_time) * 1000)) if start_time is not None else 0
    return CheckResult(
        feature=journey.feature,
        checkpoint_id=step.id,
        checkpoint=step.checkpoint,
        expected_behavior=step.expected_behavior,
        actual_observation=actual,
        status=status,
        evidence=evidence or [],
        source_of_expectation=getattr(step, "source_of_expectation", "user_requirement"),
        timestamp=utc_now(),
        reproducibility=f"Run `ghost-hunter audit {journey.feature}` with this journey file.",
        confidence_rationale=rationale,
        adapter_name=step.adapter.value if hasattr(step, "adapter") else "",
        adapter_version=__version__,
        duration_ms=elapsed,
        limitations=limitations or [],
    )


def unknown_result(
    journey: Journey,
    step: JourneyStep,
    reason: str,
    start_time: float,
    limitations: list[str] | None = None,
) -> CheckResult:
    return make_result(
        journey,
        step,
        Status.UNKNOWN,
        reason,
        "The adapter could not establish a reliable observation, so this is not a pass or failure.",
        start_time=start_time,
        limitations=limitations,
    )
