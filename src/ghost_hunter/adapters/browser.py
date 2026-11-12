"""Optional Playwright browser journey adapter with killable worker process isolation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from ghost_hunter.adapters.base import AdapterContext, make_result, unknown_result
from ghost_hunter.evidence.redaction import redact_text, safe_url
from ghost_hunter.models import CheckResult, EvidenceItem, Journey, JourneyStep, Status, utc_now

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
_ASSERTION_ACTIONS = {"expect_visible", "expect_text", "expect_url_contains"}


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, (parsed.hostname or "").lower(), port


def _allow_request(url: str, method: str, base_origin: tuple[str, str, int | None], allow_writes: bool) -> bool:
    origin_allowed = url.startswith("data:") or _origin(url) == base_origin
    method_allowed = method.upper() in _READ_METHODS or allow_writes
    return origin_allowed and method_allowed


def probe_playwright(timeout_seconds: float = 2.5) -> bool:
    """Pre-flight check to verify whether Playwright driver can start in this environment."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.stop()",
            ],
            capture_output=True,
            timeout=timeout_seconds,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError, Exception):
        return False


def _create_windows_job():
    """Create a Windows Job Object configured to terminate child processes on close."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", ctypes.c_ulonglong * 8),
                ("IoInfo", ctypes.c_ulonglong * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryLimit", ctypes.c_size_t),
                ("PeakJobMemoryLimit", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info.BasicLimitInformation[2] = 0x2000
        ctypes.windll.kernel32.SetInformationJobObject(
            job,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        return job
    except Exception:
        return None


def _assign_process_to_job(job, proc: subprocess.Popen) -> None:
    if job and sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.AssignProcessToJobObject(job, proc._handle)
        except Exception:
            pass


def _terminate_process_tree(job, proc: subprocess.Popen) -> None:
    """Forcibly kill the worker process and all descendant child processes."""
    if sys.platform == "win32":
        if job:
            try:
                import ctypes

                ctypes.windll.kernel32.TerminateJobObject(job, 1)
                ctypes.windll.kernel32.CloseHandle(job)
            except Exception:
                pass
        try:
            proc.kill()
        except Exception:
            pass
    else:
        try:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    try:
        proc.wait(timeout=2.0)
    except Exception:
        pass


def _finish_browser_result(
    journey: Journey,
    step: JourneyStep,
    passed: bool,
    action_results: list[str],
    page_url: str,
    start: float,
) -> CheckResult:
    return make_result(
        journey,
        step,
        Status.PASS if passed else Status.FAIL,
        "; ".join(action_results),
        "All configured browser actions and assertions completed."
        if passed
        else "A configured browser assertion did not match the observed page.",
        evidence=[
            EvidenceItem(
                reference=f"browser:{safe_url(page_url)}",
                observed_at=utc_now(),
                summary="A headless Chromium page executed the configured same-origin actions.",
                details={"actions": action_results, "page_url": safe_url(page_url)},
            )
        ],
        start_time=start,
    )


def _run_browser_verification(
    context: AdapterContext,
    journey: Journey,
    step: JourneyStep,
    start: float,
) -> CheckResult:
    """Execute Playwright browser actions within the isolated worker process."""
    if step.settings.get("_simulate_blocking_hang"):
        time.sleep(300)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return unknown_result(
            journey, step, "Playwright is not installed; install ghost-feature-hunter[browser].", start
        )

    base_url = context.base_url
    assert base_url is not None
    actions = step.settings.get("actions", [])
    allow_browser_writes = context.config.allow_writes and context.allow_writes
    timeout_ms = min(int(context.config.timeout_seconds * 1000), 120_000)
    deadline = time.monotonic() + min(context.config.timeout_seconds, 120.0)
    action_results: list[str] = []
    page_url = base_url

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                browser_context = browser.new_context(
                    accept_downloads=False,
                    service_workers="block",
                    viewport={"width": 1280, "height": 800},
                )
                base_origin = _origin(base_url)

                def same_origin_only(route):
                    if _allow_request(
                        route.request.url,
                        route.request.method,
                        base_origin,
                        allow_browser_writes,
                    ):
                        route.continue_()
                    else:
                        route.abort()

                browser_context.route("**/*", same_origin_only)
                page = browser_context.new_page()
                page.set_default_timeout(timeout_ms)

                for action in actions:
                    remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                    page.set_default_timeout(remaining_ms)
                    if not isinstance(action, dict) or not isinstance(action.get("action"), str):
                        return unknown_result(journey, step, "Every browser action needs an action name.", start)
                    kind = action["action"]
                    if kind == "goto":
                        target = urljoin(base_url.rstrip("/") + "/", str(action.get("url", "/")))
                        if _origin(target) != base_origin:
                            return unknown_result(
                                journey, step, "Browser navigation outside the configured origin is blocked.", start
                            )
                        try:
                            response = page.goto(target, wait_until="domcontentloaded", timeout=remaining_ms)
                        except PlaywrightTimeoutError:
                            return unknown_result(
                                journey, step, "Browser navigation timed out before the page became observable.", start
                            )
                        if response is None:
                            return unknown_result(
                                journey, step, "Browser page navigation returned no HTTP response.", start
                            )
                        if response.status >= 400:
                            action_results.append(f"page navigation returned HTTP {response.status}")
                            return _finish_browser_result(journey, step, False, action_results, page.url, start)
                        page_url = page.url
                        action_results.append(f"navigated to {safe_url(page.url)} (HTTP {response.status})")
                    elif kind == "click":
                        selector = action.get("selector")
                        if not isinstance(selector, str) or not selector:
                            return unknown_result(journey, step, "click action requires a selector.", start)
                        expected_response = action.get("wait_for_response")
                        if expected_response is not None:
                            if not isinstance(expected_response, str) or not expected_response:
                                return unknown_result(journey, step, "wait_for_response must be a non-empty string.", start)
                            with page.expect_response(
                                lambda response: expected_response in response.url,
                                timeout=remaining_ms,
                            ) as response_info:
                                page.locator(selector).click()
                            response = response_info.value
                            expected_status = action["response_status"]
                            action_results.append(
                                f"click triggered configured response with HTTP {response.status}"
                            )
                            if response.status != expected_status:
                                return _finish_browser_result(journey, step, False, action_results, page.url, start)
                        else:
                            page.locator(selector).click()
                            action_results.append(f"clicked configured selector {redact_text(selector, 120)}")
                    elif kind == "fill":
                        selector, value = action.get("selector"), action.get("value")
                        if not isinstance(selector, str) or not isinstance(value, str):
                            return unknown_result(journey, step, "fill action requires string selector and value.", start)
                        page.locator(selector).fill(value)
                        action_results.append(f"filled configured selector {redact_text(selector, 120)}")
                    elif kind == "expect_visible":
                        selector = action.get("selector")
                        if not isinstance(selector, str) or not selector:
                            return unknown_result(journey, step, "expect_visible action requires a selector.", start)
                        visible = page.locator(selector).is_visible()
                        if not visible:
                            action_results.append(f"expected selector {redact_text(selector, 120)} was not visible")
                            return _finish_browser_result(journey, step, False, action_results, page_url, start)
                        action_results.append(f"expected selector {redact_text(selector, 120)} was visible")
                    elif kind == "expect_text":
                        selector, expected = action.get("selector"), action.get("text")
                        if not isinstance(selector, str) or not isinstance(expected, str):
                            return unknown_result(journey, step, "expect_text action requires string selector and text.", start)
                        actual = page.locator(selector).inner_text()
                        passed = expected in actual
                        action_results.append(
                            f"configured text assertion for {redact_text(selector, 120)} "
                            f"{'matched' if passed else 'did not match'}"
                        )
                        if not passed:
                            return _finish_browser_result(journey, step, False, action_results, page_url, start)
                    elif kind == "expect_url_contains":
                        expected = action.get("text")
                        if not isinstance(expected, str):
                            return unknown_result(journey, step, "expect_url_contains action requires string text.", start)
                        passed = expected in page.url
                        action_results.append(f"configured URL assertion {'matched' if passed else 'did not match'}")
                        page_url = page.url
                        if not passed:
                            return _finish_browser_result(journey, step, False, action_results, page_url, start)
                    elif kind == "wait_for_network_idle":
                        page.wait_for_load_state("networkidle", timeout=remaining_ms)
                        page_url = page.url
                        action_results.append("page reached network idle")
                    else:
                        return unknown_result(journey, step, f"Unsupported browser action: {kind}", start)
                return _finish_browser_result(journey, step, True, action_results, page_url, start)
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        return make_result(
            journey,
            step,
            Status.FAIL,
            f"An expected browser element or action timed out ({type(exc).__name__}).",
            "A configured browser action did not complete within the explicit timeout.",
            evidence=[
                EvidenceItem(
                    reference="browser:timeout",
                    summary="A browser action timed out.",
                    details={"actions_completed": len(action_results)},
                )
            ],
            start_time=start,
        )
    except PlaywrightError as exc:
        detail = redact_text(str(exc), 250)
        return unknown_result(
            journey,
            step,
            f"Browser could not establish a reliable result ({type(exc).__name__}): {detail}",
            start,
        )


def _worker_main() -> None:
    """CLI entrypoint executed inside the isolated killable worker process."""
    from ghost_hunter.config import HunterConfig

    try:
        raw = json.loads(sys.stdin.read())
        project_root = Path(raw["project_root"])
        config = HunterConfig.model_validate(raw["config"])
        context = AdapterContext(
            project_root=project_root,
            config=config,
            base_url_override=raw.get("base_url_override"),
            allow_writes=raw.get("allow_writes", False),
            approve_production=raw.get("approve_production", False),
        )
        journey = Journey.model_validate(raw["journey"])
        step = JourneyStep.model_validate(raw["step"])
        start_time = float(raw.get("start_time", time.monotonic()))
        result = _run_browser_verification(context, journey, step, start_time)
        sys.stdout.write(result.model_dump_json() + "\n")
        sys.stdout.flush()
    except Exception as exc:
        sys.stderr.write(f"WorkerError: {type(exc).__name__}: {exc}\n")
        sys.stderr.flush()
        sys.exit(1)


class BrowserAdapter:
    def verify(self, context: AdapterContext, journey: Journey, step: JourneyStep) -> CheckResult:
        start = time.monotonic()
        base_url = context.base_url
        if not base_url:
            return unknown_result(journey, step, "Browser step requires a configured base_url.", start)
        parsed_base = urlsplit(base_url)
        if (
            parsed_base.scheme not in {"http", "https"}
            or not parsed_base.hostname
            or parsed_base.username
            or parsed_base.password
            or parsed_base.query
            or parsed_base.fragment
        ):
            return unknown_result(
                journey,
                step,
                "Browser base_url must be an HTTP(S) origin without credentials or query data.",
                start,
            )
        if context.config.environment == "production" and not (
            context.config.production_approved and context.approve_production
        ):
            return unknown_result(
                journey, step, "Production browser target is blocked without explicit approval.", start
            )
        actions = step.settings.get("actions", [])
        if not isinstance(actions, list) or not actions:
            return unknown_result(journey, step, "Browser step must include an explicit actions list.", start)
        if len(actions) > 25:
            return unknown_result(journey, step, "Browser step exceeds the 25-action limit.", start)
        if not all(isinstance(action, dict) and isinstance(action.get("action"), str) for action in actions):
            return unknown_result(journey, step, "Every browser action needs an action name.", start)
        for action in actions:
            if action.get("action") == "click" and action.get("wait_for_response") is not None:
                status = action.get("response_status")
                if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
                    return unknown_result(
                        journey,
                        step,
                        "A configured click response check requires an HTTP response_status from 100 to 599.",
                        start,
                    )
        has_assertion = any(
            action.get("action") in _ASSERTION_ACTIONS
            or (action.get("action") == "click" and action.get("wait_for_response") is not None)
            for action in actions
        )
        if not has_assertion:
            return unknown_result(journey, step, "Browser step needs an explicit page or response assertion.", start)
        allow_browser_writes = context.config.allow_writes and context.allow_writes
        if (
            any(isinstance(action, dict) and action.get("action") in {"click", "fill"} for action in actions)
            and not allow_browser_writes
        ):
            return unknown_result(
                journey,
                step,
                "Browser interaction may submit data; set allow_writes in project config and pass --allow-writes.",
                start,
            )

        # Enforce configurable hard deadline
        step_timeout = float(step.settings.get("timeout_seconds", context.config.timeout_seconds))
        hard_deadline = max(0.5, step_timeout)

        payload = {
            "project_root": str(context.project_root.resolve()),
            "config": context.config.model_dump(mode="json"),
            "base_url_override": context.base_url_override,
            "allow_writes": context.allow_writes,
            "approve_production": context.approve_production,
            "journey": journey.model_dump(mode="json"),
            "step": step.model_dump(mode="json"),
            "start_time": start,
        }
        payload_json = json.dumps(payload)

        repo_src = str(Path(__file__).resolve().parents[2])
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = repo_src + (os.pathsep + child_env.get("PYTHONPATH", ""))

        job = _create_windows_job()
        proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", "from ghost_hunter.adapters.browser import _worker_main; _worker_main()"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=child_env,
                start_new_session=(sys.platform != "win32"),
            )
            _assign_process_to_job(job, proc)
            stdout, stderr = proc.communicate(input=payload_json, timeout=hard_deadline)
        except subprocess.TimeoutExpired:
            if proc:
                _terminate_process_tree(job, proc)
            return unknown_result(
                journey,
                step,
                f"Browser verification worker process exceeded hard deadline of {hard_deadline:.1f}s and was terminated.",
                start,
            )
        finally:
            if job and sys.platform == "win32":
                try:
                    import ctypes

                    ctypes.windll.kernel32.CloseHandle(job)
                except Exception:
                    pass

        if proc.returncode != 0:
            return unknown_result(
                journey,
                step,
                f"Browser worker process failed with exit code {proc.returncode}: {stderr.strip()[:300]}",
                start,
            )

        try:
            result_data = json.loads(stdout)
            return CheckResult.model_validate(result_data)
        except Exception as exc:
            return unknown_result(
                journey,
                step,
                f"Failed to parse result from browser worker ({type(exc).__name__}): {stdout[:100]}",
                start,
            )
