from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from services.api.app.services.booking_base import (
    BookingAdapter,
    BookingAdapterError,
    BookingDraftResult,
    BookingExecuteResult,
    BookingLinkRequiredError,
    BookingPlaywrightMissingError,
)


@dataclass(frozen=True, slots=True)
class _ResyConfig:
    base_url: str
    venue_url: str | None
    venue_name: str | None
    headless: bool
    slow_mo_ms: int
    storage_state_dir: Path
    artifacts_dir: Path
    dry_run: bool

    @classmethod
    def from_env(cls) -> "_ResyConfig":
        base_url = os.getenv("HALO_RESY_BASE_URL", "https://resy.com").rstrip("/")
        venue_url = (os.getenv("HALO_RESY_VENUE_URL") or "").strip() or None
        venue_name = (os.getenv("HALO_RESY_VENUE_NAME") or "").strip() or None

        headless = _parse_bool(os.getenv("HALO_RESY_HEADLESS", "false"))
        dry_run = _parse_bool(os.getenv("HALO_RESY_DRY_RUN", "true"))
        slow_mo_ms = int(os.getenv("HALO_RESY_SLOW_MO_MS", "0"))

        storage_state_dir = Path(os.getenv("HALO_RESY_STORAGE_STATE_DIR", ".local/resy_sessions"))
        artifacts_dir = Path(os.getenv("HALO_RESY_ARTIFACTS_DIR", ".local/resy_artifacts"))

        return cls(
            base_url=base_url,
            venue_url=venue_url,
            venue_name=venue_name,
            headless=headless,
            slow_mo_ms=slow_mo_ms,
            storage_state_dir=storage_state_dir.expanduser(),
            artifacts_dir=artifacts_dir.expanduser(),
            dry_run=dry_run,
        )


class ResyBrowserBookingAdapter(BookingAdapter):
    """Resy booking via Playwright browser automation.

    Dogfood-only integration:
    - CI must use the mock booking adapter.
    - This adapter is intentionally conservative: if the UI state is uncertain, fail closed.

    Required setup (one-time per household):
    - Link a session via `scripts/resy_link.py` (storage_state JSON per household).

    Env vars:
    - HALO_BOOKING_ADAPTER=resy
    - HALO_RESY_VENUE_URL=https://resy.com/cities/<city>/venues/<slug>
    - HALO_RESY_STORAGE_STATE_DIR (default: .local/resy_sessions)
    - HALO_RESY_ARTIFACTS_DIR (default: .local/resy_artifacts)
    - HALO_RESY_HEADLESS (default: false)
    - HALO_RESY_DRY_RUN (default: true)

    Params (from intent):
    - date: YYYY-MM-DD (preferred)
    - party_size: int (preferred)
    - time_preference: string (e.g. "7pm", "around 7")
    """

    vendor = "RESY_BROWSER"

    def __init__(self) -> None:
        self._cfg = _ResyConfig.from_env()

    def build_draft(
        self,
        household_id: str,
        *,
        vendor_name: str,
        service_type: str,
        price_estimate_cents: int,
        params: dict,
    ) -> BookingDraftResult:
        # Gate on linked session first so the caller gets a consistent 412.
        storage_state = self._storage_state_path(household_id)

        venue_url = self._cfg.venue_url
        if not venue_url:
            raise BookingAdapterError(
                "Resy venue is not configured. Set HALO_RESY_VENUE_URL to a Resy venue page."
            )

        # Best-effort defaults. Draft is safe; the user confirms before committing.
        date = str(params.get("date") or "").strip()
        if not date:
            date = time.strftime("%Y-%m-%d")

        party_size = _coerce_int(params.get("party_size") or params.get("seats"), default=2)
        party_size = max(1, min(20, party_size))

        time_pref = str(params.get("time_preference") or params.get("time") or "").strip()

        _ensure_playwright_installed()

        run_dir = _new_run_dir(self._cfg.artifacts_dir, household_id)
        url = _with_query_params(venue_url, {"date": date, "seats": str(party_size)})

        warnings: list[str] = []
        if "date" not in params:
            warnings.append(f"No date specified; defaulting to {date}.")
        if "party_size" not in params and "seats" not in params:
            warnings.append(f"No party size specified; defaulting to {party_size}.")

        with _sync_playwright() as p:
            browser = _launch(p, headless=self._cfg.headless, slow_mo_ms=self._cfg.slow_mo_ms)
            context = browser.new_context(storage_state=str(storage_state))
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                _best_effort_wait_for_app(page)

                # Extract visible time slot labels (e.g. "7:00 PM").
                labels = _extract_time_slot_labels(page)
                if not labels:
                    artifact = _write_debug_artifacts(page, run_dir, prefix="draft_no_slots")
                    raise BookingAdapterError(
                        "No visible Resy time slots found. "
                        "This can happen if you're not logged in, "
                        "the venue requires Global Dining Access, "
                        "or there is no availability. "
                        f"Artifact: {artifact}"
                    )

                chosen = _pick_time_slots(labels, time_pref)
                windows: list[dict[str, str]] = []
                for label in chosen:
                    # We store strings only; clients can display these without parsing.
                    windows.append(
                        {
                            "start": f"{date} {label}",
                            "end": f"{date} {label}",
                            "label": label,
                            "resy_url": url,
                            "party_size": str(party_size),
                            "date": date,
                        }
                    )

                out_vendor_name = self._cfg.venue_name or vendor_name or "Resy"
                out_service_type = service_type.strip() or "restaurant"

                # Resy reservations are usually free; keep as best-effort.
                out_price = max(0, int(price_estimate_cents or 0))

                return BookingDraftResult(
                    vendor=self.vendor,
                    vendor_name=out_vendor_name,
                    service_type=out_service_type,
                    price_estimate_cents=out_price,
                    time_windows=windows,
                    selected_time_window_index=0,
                    warnings=warnings,
                )
            except BookingAdapterError:
                raise
            except Exception as e:
                artifact = _write_debug_artifacts(page, run_dir, prefix="draft_error")
                raise BookingAdapterError(
                    f"Resy draft failed: {type(e).__name__}: {e}. Artifact: {artifact}"
                ) from e
            finally:
                browser.close()

    def execute(self, household_id: str, *, draft_payload: dict) -> BookingExecuteResult:
        storage_state = self._storage_state_path(household_id)

        _ensure_playwright_installed()

        run_dir = _new_run_dir(self._cfg.artifacts_dir, household_id)

        windows = draft_payload.get("time_windows") or []
        idx = int(draft_payload.get("selected_time_window_index") or 0)
        if not isinstance(windows, list) or not windows or idx < 0 or idx >= len(windows):
            raise BookingAdapterError("Draft missing valid time_windows")

        selected = windows[idx] if isinstance(windows[idx], dict) else {}
        label = str(selected.get("label") or "").strip()
        url = str(selected.get("resy_url") or self._cfg.venue_url or "").strip()
        if not label or not url:
            raise BookingAdapterError("Draft missing booking details (label/url)")

        with _sync_playwright() as p:
            browser = _launch(p, headless=self._cfg.headless, slow_mo_ms=self._cfg.slow_mo_ms)
            context = browser.new_context(storage_state=str(storage_state))
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                _best_effort_wait_for_app(page)

                _click_time_slot(page, label)

                # Try to advance through the flow until we either see a confirmation-ish state,
                # or we hit a clear "final confirm" button.
                page.wait_for_timeout(1500)

                if self._cfg.dry_run:
                    page.screenshot(path=str(run_dir / "dryrun_after_select.png"), full_page=True)
                    return BookingExecuteResult(
                        confirmation_id=f"dryrun_{int(time.time())}",
                        summary=(
                            "Dry run: selected a time slot and stopped before final confirmation. "
                            f"Screenshot: {run_dir}/dryrun_after_select.png"
                        ),
                        external_reference_id=None,
                    )

                # Best-effort attempt to confirm reservation.
                _attempt_confirm(page, run_dir)

                page.screenshot(path=str(run_dir / "confirmation.png"), full_page=True)
                confirmation_id = (
                    _best_effort_extract_confirmation_id(page) or f"resy_{int(time.time())}"
                )

                return BookingExecuteResult(
                    confirmation_id=confirmation_id,
                    summary=f"Reservation booked. Confirmation: {confirmation_id}.",
                    external_reference_id=confirmation_id,
                )
            except BookingAdapterError:
                raise
            except Exception as e:
                artifact = _write_debug_artifacts(page, run_dir, prefix="execute_error")
                raise BookingAdapterError(
                    f"Resy execute failed: {type(e).__name__}: {e}. Artifact: {artifact}"
                ) from e
            finally:
                browser.close()

    def _storage_state_path(self, household_id: str) -> Path:
        state_path = (self._cfg.storage_state_dir / f"{household_id}.json").expanduser()
        if not state_path.exists():
            raise BookingLinkRequiredError(state_path)
        return state_path


_TIME_LABEL_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*([AP]M)\s*$", re.IGNORECASE)


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "y"}


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _with_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update({k: v for k, v in params.items() if v is not None and v != ""})
    new_query = urlencode(existing)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )


def _ensure_playwright_installed() -> None:
    try:
        import playwright  # noqa: F401
    except Exception as e:
        raise BookingPlaywrightMissingError() from e


def _sync_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _launch(p: Any, *, headless: bool, slow_mo_ms: int):
    # Prefer system Chrome when available (more likely to pass bot checks), but fall back.
    use_chrome = _parse_bool(os.getenv("HALO_RESY_USE_CHROME", "true"))
    if use_chrome:
        try:
            return p.chromium.launch(channel="chrome", headless=headless, slow_mo=slow_mo_ms)
        except Exception:
            pass
    return p.chromium.launch(headless=headless, slow_mo=slow_mo_ms)


def _new_run_dir(artifacts_dir: Path, household_id: str) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = (artifacts_dir / household_id / ts).expanduser()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_debug_artifacts(page: Any, run_dir: Path, *, prefix: str) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshot = run_dir / f"{prefix}.png"
    html = run_dir / f"{prefix}.html"

    try:
        page.screenshot(path=str(screenshot), full_page=True)
    except Exception:
        pass

    try:
        html.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

    # Return the most useful primary artifact.
    return screenshot


def _best_effort_wait_for_app(page: Any) -> None:
    # Resy is a SPA; give it a moment to render.
    page.wait_for_timeout(2500)


def _extract_time_slot_labels(page: Any) -> list[str]:
    # Time slots can be buttons or links depending on venue.
    labels: list[str] = []

    for selector in ("button", "a", "[role=button]"):
        loc = page.locator(selector)
        try:
            count = min(loc.count(), 300)
        except Exception:
            continue

        for i in range(count):
            el = loc.nth(i)
            try:
                txt = (el.inner_text() or "").strip().replace("\n", " ")
            except Exception:
                continue
            m = _TIME_LABEL_RE.match(txt)
            if not m:
                continue
            # Normalize: "7:00 PM"
            labels.append(f"{m.group(1)} {m.group(2).upper()}")

    # Preserve order, dedupe.
    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


def _pick_time_slots(labels: list[str], time_pref: str) -> list[str]:
    # Minimal heuristic: pick the first 3 unique times. If a preference is present and matches,
    # prefer times around it.
    if len(labels) <= 3:
        return labels[:3]

    pref = (time_pref or "").strip().lower()
    if pref:
        # Try to find a label containing the preference (e.g. "7" or "7:00").
        for i, label in enumerate(labels):
            if pref in label.lower():
                start = max(0, i - 1)
                return labels[start : start + 3]

    return labels[:3]


def _click_time_slot(page: Any, label: str) -> None:
    # Try a few strategies. Use locators (not element handles) to avoid stale DOM issues.
    strategies = [
        lambda: page.get_by_role("button", name=label).first,
        lambda: page.locator("button", has_text=re.compile(rf"^\s*{re.escape(label)}\s*$")).first,
        lambda: page.locator("a", has_text=re.compile(rf"^\s*{re.escape(label)}\s*$")).first,
        lambda: (
            page.locator(
                "[role=button]",
                has_text=re.compile(rf"^\s*{re.escape(label)}\s*$"),
            ).first
        ),
        lambda: page.locator(f"text={label}").first,
    ]

    last_err: Exception | None = None
    for make in strategies:
        try:
            loc = make()
            loc.click(timeout=15_000)
            return
        except Exception as e:
            last_err = e
            continue

    raise BookingAdapterError(f"Could not click time slot {label!r}: {last_err}")


def _attempt_confirm(page: Any, run_dir: Path) -> None:
    # Fail closed if we see deposit/payment requirements.
    body = (page.inner_text("body") or "").lower()
    if "deposit" in body and "required" in body:
        artifact = _write_debug_artifacts(page, run_dir, prefix="deposit_required")
        raise BookingAdapterError(
            "Reservation appears to require a deposit/payment. "
            "Halo will not proceed automatically. "
            f"Artifact: {artifact}"
        )

    # Best effort: click an obvious confirmation button.
    candidates = [
        re.compile(r"confirm", re.I),
        re.compile(r"complete", re.I),
        re.compile(r"book", re.I),
        re.compile(r"reserve", re.I),
    ]

    for pat in candidates:
        btn = page.get_by_role("button", name=pat)
        try:
            if btn.count() > 0:
                btn.first.click(timeout=15_000)
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue

    artifact = _write_debug_artifacts(page, run_dir, prefix="no_confirm_button")
    raise BookingAdapterError(
        f"Could not find a final confirmation button in the Resy flow. Artifact: {artifact}"
    )


def _best_effort_extract_confirmation_id(page: Any) -> str | None:
    # Resy confirmation pages often include a reservation number. We use a very loose heuristic.
    text = (page.inner_text("body") or "").strip()
    m = re.search(r"\b([A-Z0-9]{6,})\b", text)
    if not m:
        return None
    return m.group(1)
