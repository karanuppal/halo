from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin

from services.api.app.models.order import OrderItemInput, OrderItemPriced
from services.api.app.services.amazon_base import (
    AmazonAdapterError,
    AmazonBotCheckError,
    AmazonCheckoutTotalDriftError,
    AmazonLinkRequiredError,
    AmazonPlaywrightMissingError,
    DraftResult,
    ExecuteResult,
)


@dataclass(frozen=True, slots=True)
class _BrowserConfig:
    base_url: str
    headless: bool
    slow_mo_ms: int
    storage_state_dir: Path
    artifacts_dir: Path
    dry_run: bool
    max_total_drift_ratio: float


class AmazonBrowserAdapter:
    """Amazon adapter implemented via Playwright browser automation.

    Warning: this is inherently brittle. Expect to iterate on selectors.

    Spend boundary:
    - build_draft: reads product info (best effort)
    - execute: attempts to place an order unless HALO_AMAZON_DRY_RUN=true

    Required local setup (once):
    - Create a linked session via scripts/amazon_link.py (storage_state JSON per household).

    Env vars:
    - HALO_AMAZON_ADAPTER=browser
    - HALO_AMAZON_STORAGE_STATE_DIR (default: .local/amazon_sessions)
    - HALO_AMAZON_BASE_URL (default: https://www.amazon.com)
    - HALO_AMAZON_HEADLESS (default: true)
    - HALO_AMAZON_SLOW_MO_MS (default: 0)
    - HALO_AMAZON_ARTIFACTS_DIR (default: .local/amazon_artifacts)
    - HALO_AMAZON_DRY_RUN (default: true)
    - HALO_AMAZON_MAX_TOTAL_DRIFT_RATIO (default: 0.05)
    """

    vendor = "AMAZON_BROWSER"

    def __init__(self, cfg: _BrowserConfig) -> None:
        self._cfg = cfg

    @classmethod
    def from_env(cls) -> "AmazonBrowserAdapter":
        base_url = os.getenv("HALO_AMAZON_BASE_URL", "https://www.amazon.com").rstrip("/")
        storage_state_dir = Path(
            os.getenv("HALO_AMAZON_STORAGE_STATE_DIR", ".local/amazon_sessions")
        ).expanduser()
        artifacts_dir = Path(
            os.getenv("HALO_AMAZON_ARTIFACTS_DIR", ".local/amazon_artifacts")
        ).expanduser()

        headless = _parse_bool(os.getenv("HALO_AMAZON_HEADLESS", "true"))
        dry_run = _parse_bool(os.getenv("HALO_AMAZON_DRY_RUN", "true"))
        slow_mo_ms = int(os.getenv("HALO_AMAZON_SLOW_MO_MS", "0"))
        max_total_drift_ratio = float(os.getenv("HALO_AMAZON_MAX_TOTAL_DRIFT_RATIO", "0.05"))

        return cls(
            _BrowserConfig(
                base_url=base_url,
                headless=headless,
                slow_mo_ms=slow_mo_ms,
                storage_state_dir=storage_state_dir,
                artifacts_dir=artifacts_dir,
                dry_run=dry_run,
                max_total_drift_ratio=max_total_drift_ratio,
            )
        )

    def build_draft(self, household_id: str, items: list[OrderItemInput]) -> DraftResult:
        state_path = self._storage_state_path(household_id)
        run_dir = self._new_run_dir(household_id)

        warnings: list[str] = []
        priced: list[OrderItemPriced] = []

        with _sync_playwright() as p:
            browser = p.chromium.launch(headless=self._cfg.headless, slow_mo=self._cfg.slow_mo_ms)
            context = browser.new_context(storage_state=str(state_path))
            page = context.new_page()

            try:
                for item in items:
                    product_url = self._resolve_product_url(page, item.name)
                    unit_price_cents = self._get_unit_price_cents(page, product_url)
                    if unit_price_cents <= 0:
                        warnings.append(
                            f"Could not determine a price for {item.name!r}. "
                            "Total may differ at checkout."
                        )

                    line_total_cents = max(unit_price_cents, 0) * item.quantity
                    priced.append(
                        OrderItemPriced(
                            name=item.name,
                            quantity=item.quantity,
                            unit_price_cents=max(unit_price_cents, 0),
                            line_total_cents=line_total_cents,
                            product_url=product_url,
                        )
                    )
            except Exception as e:
                artifact = _write_debug_artifacts(page, run_dir, prefix="draft_error")
                if _is_bot_check(page):
                    raise AmazonBotCheckError(artifact) from e
                raise AmazonAdapterError(
                    f"Amazon browser draft failed: {type(e).__name__}: {e}. Artifact: {artifact}"
                ) from e
            finally:
                browser.close()

        estimated_total_cents = sum(i.line_total_cents for i in priced)

        # Best-effort. We avoid entering checkout during draft.
        return DraftResult(
            items=priced,
            estimated_total_cents=estimated_total_cents,
            delivery_window="See Amazon",
            payment_method_masked="Amazon default",
            warnings=warnings,
        )

    def execute(
        self,
        household_id: str,
        items: list[OrderItemPriced],
        expected_total_cents: int,
    ) -> ExecuteResult:
        state_path = self._storage_state_path(household_id)
        run_dir = self._new_run_dir(household_id)

        with _sync_playwright() as p:
            browser = p.chromium.launch(headless=self._cfg.headless, slow_mo=self._cfg.slow_mo_ms)
            context = browser.new_context(storage_state=str(state_path))
            page = context.new_page()

            try:
                self._empty_cart(page)

                for item in items:
                    product_url = item.product_url or self._resolve_product_url(page, item.name)
                    self._add_to_cart(page, product_url, item.quantity)

                page.goto(f"{self._cfg.base_url}/gp/cart/view.html", wait_until="domcontentloaded")
                self._proceed_to_checkout(page)

                actual_total_cents = self._best_effort_read_total_cents(page)
                if actual_total_cents is not None and expected_total_cents > 0:
                    drift = _drift_ratio(actual_total_cents, expected_total_cents)
                    if drift > self._cfg.max_total_drift_ratio:
                        raise AmazonCheckoutTotalDriftError(
                            expected_total_cents=expected_total_cents,
                            actual_total_cents=actual_total_cents,
                        )

                if self._cfg.dry_run:
                    page.screenshot(path=str(run_dir / "checkout.png"), full_page=True)
                    return ExecuteResult(
                        receipt_id=f"dryrun_{int(time.time())}",
                        total_cents=actual_total_cents or expected_total_cents,
                        summary=f"Dry run: stopped at checkout. Screenshot: {run_dir}/checkout.png",
                    )

                self._place_order(page)
                page.screenshot(path=str(run_dir / "confirmation.png"), full_page=True)

                receipt_id = _extract_order_number(page) or f"amz_{int(time.time())}"
                return ExecuteResult(
                    receipt_id=receipt_id,
                    total_cents=actual_total_cents or expected_total_cents,
                    summary="Order placed",
                )
            except Exception as e:
                artifact = _write_debug_artifacts(page, run_dir, prefix="execute_error")
                if _is_bot_check(page):
                    raise AmazonBotCheckError(artifact) from e
                raise AmazonAdapterError(
                    f"Amazon browser execute failed: {type(e).__name__}: {e}. Artifact: {artifact}"
                ) from e
            finally:
                browser.close()

    def _storage_state_path(self, household_id: str) -> Path:
        state_path = (self._cfg.storage_state_dir / f"{household_id}.json").expanduser()
        if not state_path.exists():
            raise AmazonLinkRequiredError(state_path)
        return state_path

    def _new_run_dir(self, household_id: str) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        run_dir = (self._cfg.artifacts_dir / household_id / ts).expanduser()
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _resolve_product_url(self, page: Any, raw: str) -> str:
        raw = raw.strip()

        asin = _maybe_asin(raw)
        if asin is not None:
            return f"{self._cfg.base_url}/dp/{asin}"

        if raw.startswith("http://") or raw.startswith("https://"):
            return raw

        search_url = f"{self._cfg.base_url}/s?k={quote_plus(raw)}"

        page.goto(search_url, wait_until="domcontentloaded")
        # Amazon's markup changes frequently. Prefer grabbing the first result element, then
        # extracting a product link or falling back to the result ASIN.
        page.wait_for_selector(
            'div[data-component-type="s-search-result"][data-asin]',
            timeout=20_000,
        )

        results = page.query_selector_all('div[data-component-type="s-search-result"][data-asin]')
        for result in results:
            asin_attr = (result.get_attribute("data-asin") or "").strip()
            if not asin_attr:
                continue

            link_selectors = (
                "a.a-link-normal.s-no-outline[href]",
                'a.a-link-normal[href*="/dp/"][href]',
                'a[href*="/dp/"]',
            )
            for sel in link_selectors:
                link = result.query_selector(sel)
                if link is None:
                    continue
                href = link.get_attribute("href")
                if not href or "/dp/" not in href:
                    continue
                return urljoin(self._cfg.base_url, href)

            asin = _maybe_asin(asin_attr)
            if asin is not None:
                return f"{self._cfg.base_url}/dp/{asin}"

        raise RuntimeError(f"No search results found for: {raw!r}")

    def _get_unit_price_cents(self, page: Any, product_url: str) -> int:
        page.goto(product_url, wait_until="domcontentloaded")

        selectors = [
            "#corePriceDisplay_desktop_feature_div span.a-offscreen",
            "#corePrice_feature_div span.a-offscreen",
            "span.a-price span.a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
        ]

        for sel in selectors:
            el = page.query_selector(sel)
            if el is None:
                continue
            text = (el.inner_text() or "").strip()
            cents = _parse_price_to_cents(text)
            if cents is not None:
                return cents

        return 0

    def _empty_cart(self, page: Any) -> None:
        page.goto(f"{self._cfg.base_url}/gp/cart/view.html", wait_until="domcontentloaded")

        # If the cart is already empty, do not touch "Saved for later" items.
        body_text = (page.inner_text("body") or "").lower()
        if "your amazon cart is empty" in body_text or "your shopping cart is empty" in body_text:
            return

        # Only delete *cart* items (not "saved for later").
        delete_selector = 'input[value="Delete"][name^="submit.delete."]'

        for _ in range(25):
            if page.query_selector(delete_selector) is None:
                break
            page.click(delete_selector)
            page.wait_for_timeout(750)

    def _add_to_cart(self, page: Any, product_url: str, quantity: int) -> None:
        page.goto(product_url, wait_until="domcontentloaded")

        if page.query_selector("select#quantity") is not None:
            try:
                page.select_option("select#quantity", str(quantity))
            except Exception:
                pass

        for sel in ("#add-to-cart-button", "input#add-to-cart-button"):
            btn = page.query_selector(sel)
            if btn is not None:
                btn.click()
                page.wait_for_timeout(1500)
                return

        raise RuntimeError("Could not find add-to-cart button")

    def _proceed_to_checkout(self, page: Any) -> None:
        selectors = ('input[name="proceedToRetailCheckout"]', "#sc-buy-box-ptc-button input")

        for sel in selectors:
            btn = page.query_selector(sel)
            if btn is None:
                continue
            btn.click()
            page.wait_for_load_state("domcontentloaded")
            return

        raise RuntimeError("Could not find proceed-to-checkout button")

    def _best_effort_read_total_cents(self, page: Any) -> int | None:
        selectors = (
            "#subtotals-marketplace-spp-bottom .a-color-price",
            "#orderSummaryPrimaryActionBtn .a-color-price",
            "#checkout-summary-table .a-color-price",
        )

        for sel in selectors:
            el = page.query_selector(sel)
            if el is None:
                continue
            text = (el.inner_text() or "").strip()
            cents = _parse_price_to_cents(text)
            if cents is not None:
                return cents

        return None

    def _place_order(self, page: Any) -> None:
        selectors = (
            "#placeYourOrder input",
            "input#placeYourOrder",
            'input[name="placeYourOrder1"]',
        )

        for sel in selectors:
            btn = page.query_selector(sel)
            if btn is None:
                continue
            btn.click()
            page.wait_for_load_state("domcontentloaded")
            return

        raise RuntimeError("Could not find place-order button")


def _sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise AmazonPlaywrightMissingError() from e

    return sync_playwright()


def _write_debug_artifacts(page: Any, run_dir: Path, prefix: str) -> Path:
    screenshot_path = run_dir / f"{prefix}.png"
    html_path = run_dir / f"{prefix}.html"

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception:
        pass

    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

    return screenshot_path


def _is_bot_check(page: Any) -> bool:
    try:
        if page.query_selector("input#captchacharacters") is not None:
            return True
        if page.query_selector("form[action*='validateCaptcha']") is not None:
            return True

        url = getattr(page, "url", "") or ""
        if "/ap/signin" in url and page.query_selector("input#ap_email") is not None:
            return True

        title = (page.title() or "").lower()
        if "robot check" in title or "captcha" in title:
            return True
    except Exception:
        return False

    return False


_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)


def _maybe_asin(value: str) -> str | None:
    value = value.strip()
    if _ASIN_RE.fullmatch(value):
        return value.upper()
    return None


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


_PRICE_RE = re.compile(r"(\d[\d,]*)(?:\.(\d{2}))?")


def _parse_price_to_cents(text: str) -> int | None:
    match = _PRICE_RE.search(text)
    if not match:
        return None

    dollars = int(match.group(1).replace(",", ""))
    cents = int(match.group(2) or "0")
    return dollars * 100 + cents


def _drift_ratio(actual_total_cents: int, expected_total_cents: int) -> float:
    if expected_total_cents <= 0:
        return 0.0
    return abs(actual_total_cents - expected_total_cents) / expected_total_cents


def _extract_order_number(page: Any) -> str | None:
    body = page.text_content("body") or ""
    match = re.search(r"Order\s*#\s*([0-9-]{6,})", body)
    if not match:
        return None

    return match.group(1)
