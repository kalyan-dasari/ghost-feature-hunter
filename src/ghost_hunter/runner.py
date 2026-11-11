"""Journey runner that dispatches explicit steps to adapters."""

from __future__ import annotations

import time

from ghost_hunter.adapters.base import AdapterContext, unknown_result
from ghost_hunter.adapters.http import HTTPAdapter
from ghost_hunter.models import CheckResult, Journey


def _adapter_registry():
    from ghost_hunter.adapters.browser import BrowserAdapter
    from ghost_hunter.adapters.database import DatabaseAdapter

    return {
        "http": HTTPAdapter(),
        "database": DatabaseAdapter(),
        "browser": BrowserAdapter(),
    }


def run_journey(
    context: AdapterContext,
    journey: Journey,
) -> list[CheckResult]:
    adapters = _adapter_registry()
    results: list[CheckResult] = []
    for step in journey.steps:
        start = time.monotonic()
        try:
            results.append(adapters[step.adapter.value].verify(context, journey, step))
        except Exception as exc:  # An adapter defect is UNKNOWN, never a fabricated pass.
            results.append(
                unknown_result(
                    journey,
                    step,
                    f"Adapter could not complete the check ({type(exc).__name__}).",
                    start,
                )
            )
    return results
