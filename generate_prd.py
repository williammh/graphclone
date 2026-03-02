#!/usr/bin/env python3
"""
generate_prd.py — Generate a product-requirements PDF from the wireframe Next.js project.

For every page.tsx found under wireframe/src/app the script:
  1. Resolves the corresponding Next.js route URL.
  2. Takes a full-page screenshot via Playwright.
  3. Bundles all screenshots into a single PDF.

Usage:
  python generate_prd.py
  python generate_prd.py --port 3001   # custom dev-server port

Output: product-requirements.pdf  (workspace root)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
WIREFRAME_DIR = SCRIPT_DIR / "wireframe"
APP_DIR = WIREFRAME_DIR / "src" / "app"
OUTPUT_PDF = SCRIPT_DIR / "product-requirements.pdf"

DEFAULT_PORT = 3000
# Viewport width used for screenshots
VIEWPORT_WIDTH = 1440


# ---------------------------------------------------------------------------
# Route discovery
# ---------------------------------------------------------------------------
# Dynamic segment placeholder values – realistic enough that pages render.
_SEGMENT_PLACEHOLDERS: dict[str, str] = {
    "slug": "example",
    "id": "1",
}

def _placeholder_for(segment: str) -> str:
    """Return a placeholder value for a Next.js dynamic segment like [slug]."""
    inner = segment[1:-1]  # strip [ ]
    # catch-all: [[...slug]] or [...slug]
    inner = inner.lstrip(".")
    return _SEGMENT_PLACEHOLDERS.get(inner, "example")


def discover_routes(app_dir: Path) -> list[str]:
    """Walk app_dir and return a deduplicated, sorted list of Next.js route paths.

    Route groups wrapped in (parens) are transparent (not part of the URL).
    Dynamic segments [foo] are replaced with a placeholder value.
    """
    routes: list[str] = []
    for page_file in sorted(app_dir.rglob("page.tsx")):
        rel = page_file.parent.relative_to(app_dir)
        parts = list(rel.parts)

        url_parts: list[str] = []
        for part in parts:
            # Route groups: (group) → skip
            if part.startswith("(") and part.endswith(")"):
                continue
            # Dynamic: [slug] or [...slug] or [[...slug]]
            if part.startswith("[") and part.endswith("]"):
                url_parts.append(_placeholder_for(part))
            else:
                url_parts.append(part)

        route = ("/" + "/".join(url_parts)) if url_parts else "/"
        routes.append(route)

    seen: set[str] = set()
    unique: list[str] = []
    for r in routes:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


# ---------------------------------------------------------------------------
# Next.js server helpers
# ---------------------------------------------------------------------------

def start_nextjs(port: int) -> subprocess.Popen:
    """Launch `npm run dev` inside wireframe/ and return the Popen handle."""
    env = {**os.environ, "PORT": str(port)}
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(port)],
        cwd=str(WIREFRAME_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return proc


def wait_for_server(proc: subprocess.Popen, timeout: float = 90.0) -> bool:
    """Block until the Next.js dev server signals it is ready or timeout."""
    start = time.monotonic()
    assert proc.stdout is not None
    while time.monotonic() - start < timeout:
        if proc.poll() is not None:
            return False
        line = proc.stdout.readline()
        if line:
            print(f"  [next] {line}", end="", flush=True)
        low = line.lower()
        # Next.js prints "Ready in Xs" or "started server on … url: http://localhost:…"
        if "ready" in low or ("localhost" in low and ("started" in low or "url" in low)):
            return True
    return False


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------

async def screenshot_page(page: Page, url: str) -> bytes:
    """Navigate to *url* and return a full-page PNG screenshot."""
    for wait in ("networkidle", "domcontentloaded"):
        try:
            await page.goto(url, wait_until=wait, timeout=20_000)
            break
        except Exception:
            pass
    # Let any lazy-loaded content settle
    await page.wait_for_timeout(600)
    return await page.screenshot(full_page=True, type="png")


# ---------------------------------------------------------------------------
# PDF assembly
# ---------------------------------------------------------------------------

def build_pdf_html(entries: list[dict]) -> str:
    """Return an HTML document that embeds all screenshots, one per PDF page."""

    def page_block(entry: dict) -> str:
        route: str = entry["route"]
        data_url: str = entry["data_url"]
        label = entry.get("label", route)
        return f"""
    <div class="pdf-page">
      <div class="page-header">
        <span class="route-label">{label}</span>
        <span class="route-url">{route}</span>
      </div>
      <div class="screenshot-wrap">
        <img src="{data_url}" alt="Screenshot of {route}" />
      </div>
    </div>"""

    pages_html = "\n".join(page_block(e) for e in entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Product Requirements</title>
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #ffffff;
      color: #111111;
    }}

    /* ---- Cover page ---- */
    .cover-page {{
      page-break-after: always;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 48px;
      text-align: center;
      background: #f8f8f8;
    }}
    .cover-page h1 {{
      font-size: 36px;
      font-weight: 700;
      margin-bottom: 16px;
    }}
    .cover-page p {{
      font-size: 16px;
      color: #555;
    }}

    /* ---- Regular pages ---- */
    .pdf-page {{
      page-break-after: always;
      padding: 32px 32px 24px;
    }}
    .pdf-page:last-child {{
      page-break-after: avoid;
    }}

    .page-header {{
      display: flex;
      align-items: baseline;
      gap: 16px;
      padding-bottom: 10px;
      margin-bottom: 16px;
      border-bottom: 2px solid #222;
    }}
    .route-label {{
      font-size: 20px;
      font-weight: 700;
    }}
    .route-url {{
      font-family: monospace;
      font-size: 13px;
      color: #555;
    }}

    .screenshot-wrap img {{
      width: 100%;
      height: auto;
      display: block;
      border: 1px solid #e0e0e0;
    }}

    @media print {{
      .pdf-page {{ padding: 0; }}
    }}
  </style>
</head>
<body>

  <!-- Cover page -->
  <div class="cover-page">
    <h1>Product Requirements</h1>
    <p>Wireframe — {len(entries)} page(s)</p>
    <p style="margin-top:8px;font-family:monospace;font-size:13px;color:#888;">
      Generated by generate_prd.py
    </p>
  </div>

  {pages_html}

</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(port: int) -> None:
    base_url = f"http://localhost:{port}"

    # 1. Discover routes
    routes = discover_routes(APP_DIR)
    if not routes:
        print("No page.tsx files found under wireframe/src/app.")
        sys.exit(1)

    print(f"Discovered {len(routes)} route(s):")
    for r in routes:
        print(f"  {r}")

    # 2. Start dev server
    print(f"\nStarting Next.js dev server (port {port}) …")
    server = start_nextjs(port)
    try:
        if not wait_for_server(server):
            print("ERROR: Next.js server failed to start.")
            server.terminate()
            sys.exit(1)
        print("Next.js server is ready.\n")

        # Drain remaining stdout so the pipe doesn't block
        async def _drain_stdout() -> None:
            assert server.stdout
            loop = asyncio.get_event_loop()
            while server.poll() is None:
                line = await loop.run_in_executor(None, server.stdout.readline)
                if not line:
                    break

        drain_task = asyncio.create_task(_drain_stdout())

        # Give it a moment to fully compile the first request
        await asyncio.sleep(2)

        entries: list[dict] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": 900},
                device_scale_factor=1,
            )
            page = await context.new_page()

            for route in routes:
                url = base_url + route
                print(f"  Screenshotting {url} …", end=" ", flush=True)
                try:
                    png = await screenshot_page(page, url)
                    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
                    # Derive a human-readable label from the route
                    label = route.strip("/").replace("/", " › ") or "Home"
                    entries.append({"route": route, "label": label, "data_url": data_url})
                    print(f"OK  ({len(png) // 1024} KB)")
                except Exception as exc:
                    print(f"FAILED — {exc}")

            # 3. Assemble & export PDF
            print("\nAssembling PDF …")
            html = build_pdf_html(entries)
            pdf_page = await context.new_page()
            await pdf_page.set_content(html, wait_until="networkidle")
            await pdf_page.pdf(
                path=str(OUTPUT_PDF),
                format="A4",
                print_background=True,
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
            )
            print(f"\nPDF written to: {OUTPUT_PDF}")

            await browser.close()

        drain_task.cancel()

    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate product-requirements.pdf from the wireframe Next.js project."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to run the Next.js dev server on (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()
    asyncio.run(run(args.port))


if __name__ == "__main__":
    main()
