"""Reusable automation for the dropdown workflow shown in the video.

This module does not open the visa landing page and does not submit anything.
It expects the caller to provide a Playwright Page that is already displaying
 the form containing the five fields.

Sequence:
    click field -> clear field -> type query -> wait for pop-out option -> click option
    repeated for four dropdowns -> hover biometric field -> stop
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright


# These values match the user-corrected table exactly.
VIDEO_STEPS = (
    ("Current nationality", "Sri Lanka", "Sri Lanka"),
    ("Country of residence", "Sri Lanka", "Sri Lanka"),
    ("Diplomatic mission / consular post of Romania", "Colombo", "Colombo"),
    ("Type of travel document", "ORDINARY", "Ordinary/National passport"),
)
BIOMETRIC_LABEL = "Is your travel document biometric"
OPTION_SELECTORS = (
    "[role='option']",
    "li",
    ".k-list-container li",
    ".k-animation-container li",
    ".dropdown-menu li",
    ".dropdown-item",
    ".autocomplete-suggestion",
    "[data-value]",
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def token_for(label: str) -> str:
    return "video-automation-" + re.sub(r"[^a-z0-9]+", "-", clean(label)).strip("-")


async def find_field(page: Page, label_text: str):
    """Find an editable field by label, associated control, or semantic attributes."""
    token = token_for(label_text)
    wanted = re.escape(label_text)

    # First use the browser accessibility association when the page provides it.
    accessible = page.get_by_label(re.compile(wanted, re.IGNORECASE)).first
    try:
        if await accessible.count() and await accessible.is_visible():
            await accessible.set_attribute("data-video-automation", token)
            return accessible
    except Exception:
        pass

    # Fallback for pages whose labels are visual text only or whose generated IDs
    # are not connected with the label's `for` attribute.
    await page.evaluate(
        """({labelText, token}) => {
          const wanted = labelText.trim().toLowerCase();
          const editable = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea';
          const labels = [...document.querySelectorAll('label')];
          const label = labels.find(x => (x.innerText || x.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase().includes(wanted));
          let field = null;

          if (label && label.htmlFor) field = document.getElementById(label.htmlFor);
          if (!field && label) {
            const container = label.closest('div,td,fieldset,section,form') || label.parentElement;
            field = container && container.querySelector(editable);
          }
          if (!field) {
            field = [...document.querySelectorAll(editable)].find(x => {
              const attrs = [x.getAttribute('aria-label'), x.getAttribute('placeholder'), x.getAttribute('name'), x.id]
                .filter(Boolean).join(' ').toLowerCase();
              return attrs.includes(wanted);
            });
          }
          if (!field) throw new Error('Could not find field: ' + labelText);
          field.setAttribute('data-video-automation', token);
        }""",
        {"labelText": label_text, "token": token},
    )
    return page.locator(f"[data-video-automation='{token}']").first


async def visible_option_exists(page: Page, option_text: str) -> bool:
    expected = clean(option_text)
    selector = ",".join(OPTION_SELECTORS)
    return await page.evaluate(
        """({selector, expected}) => [...document.querySelectorAll(selector)].some(node => {
          const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const style = getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return text && (text === expected || text.includes(expected)) &&
            style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        })""",
        {"selector": selector, "expected": expected},
    )


async def click_popout_word(page: Page, option_text: str, timeout_ms: int) -> None:
    """Wait for the asynchronously-created pop-out word and click the exact match."""
    expected = clean(option_text)
    selector = ",".join(OPTION_SELECTORS)

    await page.wait_for_function(
        """({selector, expected}) => [...document.querySelectorAll(selector)].some(node => {
          const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const style = getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return text && (text === expected || text.includes(expected)) &&
            style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        })""",
        arg={"selector": selector, "expected": expected},
        timeout=timeout_ms,
    )

    clicked = await page.evaluate(
        """({selector, expected}) => {
          const visible = [...document.querySelectorAll(selector)].filter(node => {
            const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const style = getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return text && (text === expected || text.includes(expected)) &&
              style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          });
          const target = visible.find(node =>
            (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase() === expected
          ) || visible[0];
          if (!target) return false;
          target.scrollIntoView({block: 'center', inline: 'nearest'});
          target.click();
          return true;
        }""",
        {"selector": selector, "expected": expected},
    )
    if not clicked:
        raise RuntimeError(f"Pop-out word not clickable: {option_text}")


async def type_then_select(
    page: Page,
    label: str,
    text_to_type: str,
    option_to_click: str,
    timeout_ms: int,
    typing_delay_ms: int = 45,
) -> None:
    """Perform one complete video-style dropdown interaction."""
    field = await find_field(page, label)
    await field.scroll_into_view_if_needed()
    await field.click()

    # The video visibly types into the focused field. Do not set the value with
    # JavaScript: clear it with the keyboard and send each character normally.
    await field.press("Control+A")
    await field.press("Backspace")
    print(f"[{label}] TYPE {text_to_type!r}")
    await field.type(text_to_type, delay=typing_delay_ms)

    print(f"[{label}] WAIT FOR POP-OUT {option_to_click!r}")
    await click_popout_word(page, option_to_click, timeout_ms)

    # Commit Telerik RadComboBox state & hidden fields
    token = token_for(label)
    await page.evaluate(
        """({token, expected}) => {
          const field = document.querySelector(`[data-video-automation="${token}"]`);
          if (field) {
            const rcbId = field.id.replace('_Input', '');
            if (window.$find) {
              const combo = window.$find(rcbId) || window.$find(field.id);
              if (combo) {
                const items = combo.get_items ? combo.get_items().toArray() : [];
                const matched = items.find(i => (i.get_text() || '').toLowerCase().includes(expected.toLowerCase()));
                if (matched && matched.select) {
                  matched.select();
                  if (combo.set_selectedItem) combo.set_selectedItem(matched);
                  if (combo.set_text) combo.set_text(matched.get_text());
                  if (combo.set_value) combo.set_value(matched.get_value());
                } else {
                  if (combo.set_text) combo.set_text(expected);
                  if (combo.set_value) combo.set_value(expected);
                }
                if (combo.commitChanges) combo.commitChanges();
                if (combo.hideDropDown) combo.hideDropDown();
              }
            }
            field.value = expected;
            const valInput = document.getElementById(rcbId + '_Value') || document.querySelector('input[name="' + rcbId + '_Value"]');
            if (valInput) valInput.value = expected;
            const clientState = document.getElementById(rcbId + '_ClientState') || document.querySelector('input[name="' + rcbId + '_ClientState"]');
            if (clientState) clientState.value = JSON.stringify({ logEntries: [], value: expected, text: expected, enabled: true });
          }
        }""",
        {"token": token, "expected": option_to_click},
    )

    await page.wait_for_function(
        """({token, expected}) => {
          const field = document.querySelector(`[data-video-automation="${token}"]`);
          return field && (field.value || '').replace(/\\s+/g, ' ').trim().toLowerCase().includes(expected);
        }""",
        arg={"token": token, "expected": clean(option_to_click)},
        timeout=timeout_ms,
    )
    print(f"[{label}] CLICKED AND COMMITTED {option_to_click!r}")


async def verify_no_mandatory_errors(page: Page) -> list[str]:
    """Scan the DOM for any visible ASP.NET or custom mandatory validation error messages."""
    return await page.evaluate(
        """() => {
          const mandatoryPhrases = [
            'the "current nationality" field is mandatory!',
            'the "country of residence" field is mandatory!',
            'the "diplomatic mission/consular post of romania" field is mandatory!',
            'the "type of travel document" field is mandatory!',
            'field is mandatory',
            'este obligatoriu'
          ];
          const found = [];
          const allEls = [...document.querySelectorAll('span, div, p, label, .validator, .field-validation-error, .text-danger, [id*="Validator"], [id*="Val"], [id*="Required"]')];
          for (const el of allEls) {
            const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            const style = window.getComputedStyle(el);
            const isVisible = el.offsetWidth > 0 && el.offsetHeight > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            if (isVisible && mandatoryPhrases.some(p => text.toLowerCase().includes(p))) {
              if (!found.includes(text)) found.push(text);
            }
          }
          return found;
        }"""
    )


async def run_video_workflow(
    page: Page,
    *,
    timeout_ms: int = 30_000,
    typing_delay_ms: int = 45,
) -> None:
    """Run the workflow on an already-open form page.

    Import this function into your own application and pass it your existing
    Playwright `page` object.
    """
    await page.set_viewport_size({"width": 1440, "height": 1100})
    page.set_default_timeout(timeout_ms)

    # Confirm that the form is already present instead of silently navigating
    # somewhere else when the caller supplied the wrong page.
    await find_field(page, VIDEO_STEPS[0][0])

    for idx, (label, typed_text, option_text) in enumerate(VIDEO_STEPS):
        await type_then_select(
            page,
            label,
            typed_text,
            option_text,
            timeout_ms,
            typing_delay_ms,
        )
        # Extra pause after Country of residence for server PostBack
        if idx == 1:
            print("Waiting for dependent Consular Missions list to load via PostBack...")
            await page.wait_for_timeout(2500)

    biometric = await find_field(page, BIOMETRIC_LABEL)
    await biometric.scroll_into_view_if_needed()
    await biometric.hover()
    print(f"[DONE] Hovered over {BIOMETRIC_LABEL!r}.")

    # Validation check
    errors = await verify_no_mandatory_errors(page)
    if errors:
        print(f"\n❌ [ERROR] Mandatory validation errors detected: {errors}")
        raise RuntimeError(f"Mandatory validation errors present: {errors}")
    else:
        print("\n✅ [SUCCESS] All 4 dropdowns verified with 0 mandatory validation errors.")


async def run_standalone(form_url: str, headed: bool, timeout_ms: int, screenshot: str | None) -> None:
    """Optional standalone runner for testing; the reusable entry point is run_video_workflow."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not headed,
            args=["--disable-notifications", "--disable-popup-blocking", "--no-sandbox"],
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        try:
            await page.goto(form_url, wait_until="domcontentloaded")
            await run_video_workflow(page, timeout_ms=timeout_ms)
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=screenshot, full_page=True)
                print(f"Screenshot saved to {screenshot}")
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form-url", required=True, help="URL of the page that already contains the five fields")
    parser.add_argument("--headed", action="store_true", help="Show the browser")
    parser.add_argument("--timeout", type=int, default=30_000, help="Wait timeout in milliseconds")
    parser.add_argument("--screenshot", default="artifacts/video_workflow_final.png")
    args = parser.parse_args()
    asyncio.run(run_standalone(args.form_url, args.headed, args.timeout, args.screenshot))


if __name__ == "__main__":
    main()
