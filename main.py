import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import os
import sys
import re
from urllib.parse import urlparse, urlunparse
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from dataclasses import dataclass
import json

# Enable every available evasion and set realistic browser fingerprints.
# chrome_runtime is False by default in the library — explicitly enable it.
STEALTH = Stealth(
    chrome_app=True,
    chrome_csi=True,
    chrome_load_times=True,
    chrome_runtime=True,
    hairline=True,
    iframe_content_window=True,
    media_codecs=True,
    navigator_hardware_concurrency=True,
    navigator_languages=True,
    navigator_languages_override=("en-US", "en"),
    navigator_permissions=True,
    navigator_platform=True,
    navigator_platform_override="Win32",
    navigator_plugins=True,
    navigator_user_agent=True,
    navigator_vendor=True,
    navigator_vendor_override="Google Inc.",
    navigator_webdriver=True,
    error_prototype=True,
    sec_ch_ua=True,
    webgl_vendor=True,
    webgl_vendor_override="Intel Inc.",
    webgl_renderer_override="Intel Iris OpenGL Engine",
    init_scripts_only=False,
    script_logging=False,
)

@dataclass
class SegmentStats:
    """Per-path statistics used by Prong 2B (nav/structural signals)."""
    in_link_count: int = 0
    nav_link_count: int = 0
    first_seen_depth: int = -1


def _classify_segment(seg: str) -> str | None:
    """Prong 1: Structural heuristics on a single URL segment.

    Returns a placeholder (':id', ':slug', ':id-:slug') if the segment is
    clearly dynamic, or None if ambiguous (defer to Prong 2).

    Rules applied in order, short-circuiting on first match:
      1. Purely numeric -> :id
      2. Long hex string / UUID -> :id
      3. Numeric prefix + text -> :id-:slug
      4. High digit ratio (>30% digits, length > 4) -> :slug
      5. Very long segment (>40 chars) -> :slug
      6. Otherwise -> None (ambiguous)
    """
    if not seg:
        return None
    # 1. Purely numeric
    if re.fullmatch(r"\d+", seg):
        return ":id"
    # 2. Long hex string or UUID
    if re.fullmatch(r"[0-9a-fA-F]{8,}", seg) or re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        seg,
    ):
        return ":id"
    # 3. Numeric prefix + text (e.g. 1386286-trump-was-once)
    if re.match(r"^\d+[-_].+", seg):
        return ":id-:slug"
    # 4. High digit ratio (>30% digits and length > 4)
    if len(seg) > 4:
        digit_ratio = sum(c.isdigit() for c in seg) / len(seg)
        if digit_ratio > 0.3:
            return ":slug"
    # 5. Very long segment
    if len(seg) > 40:
        return ":slug"
    # 6. Ambiguous
    return None


def analyze_html_signals(html_path: str) -> bool:
    """Prong 2C: Analyze saved HTML for signals that a page is a dynamic template.

    Looks for schema.org markup, og:type meta tags, and canonical link tags
    that indicate the page is an instance of a repeating template (profile,
    article, product, etc.).

    Returns True if the page appears to be dynamic.
    """
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
    except (FileNotFoundError, OSError):
        return False

    # --- Schema.org structured data (JSON-LD) ---
    _DYNAMIC_SCHEMA_TYPES = frozenset({
        "Person", "Article", "Product", "NewsArticle", "BlogPosting",
        "UserProfile", "ProfilePage", "ItemPage",
    })
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string or ""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            schema_type = item.get("@type", "")
            types = schema_type if isinstance(schema_type, list) else [schema_type]
            if any(t in _DYNAMIC_SCHEMA_TYPES for t in types):
                return True

    # --- og:type meta tag ---
    og_type_tag = soup.find("meta", property="og:type")
    if og_type_tag:
        og_val = (og_type_tag.get("content") or "").lower()
        if og_val in ("profile", "article", "product"):
            return True

    # --- Canonical link that itself contains a dynamic segment ---
    canonical_tag = soup.find("link", rel="canonical")
    if canonical_tag:
        href = canonical_tag.get("href", "")
        canon_segs = [s for s in urlparse(href).path.split("/") if s]
        for seg in canon_segs:
            if _classify_segment(seg) is not None:
                return True

    return False


def canonicalize_url(
    url: str,
    observed_last_segment_values: dict | None = None,
    observed_static_segments: dict | None = None,
    segment_stats: dict | None = None,
    forced_dynamic_parents: set | None = None,
) -> str:
    """Return a canonical form of the URL for deduplication.

    Implements a two-pronged approach:

    Prong 1 -- Structural heuristics (_classify_segment):
      Replaces obviously dynamic segments (numeric IDs, hex hashes,
      id-slug combos, high digit ratio, very long slugs).

    Prong 2A -- Cardinality-based collapsing:
      When a parent path has produced more than SLUG_CARDINALITY_THRESHOLD
      distinct last-segment values, collapse future unseen segments to :slug.
      Segments observed *before* the threshold was crossed are locked in
      observed_static_segments and are never collapsed.

    Prong 2B -- Navigation/structural signals:
      A segment with nav_link_count >= 2 is treated as static and immune to
      both cardinality collapsing and forced-dynamic overrides.

    Prong 2C -- HTML content analysis (forced_dynamic_parents):
      Parent paths flagged by post-save HTML analysis force slug collapsing
      for any non-static child segment.

    Query strings and fragments are stripped.  Trailing slashes are removed
    (except for root paths).
    """
    parsed = urlparse(url)

    if not parsed.netloc:
        return url

    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"

    # Normalize trailing slash (keep root /)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    raw_segments = [seg for seg in path.split("/") if seg]
    segments = list(raw_segments)

    # --- Prong 1: structural heuristics on every segment ---
    for i, seg in enumerate(segments):
        placeholder = _classify_segment(seg)
        if placeholder is not None:
            segments[i] = placeholder

    # --- Prong 2: empirical evidence applied to every segment ---
    # Use raw_segments for parent construction so that replacements made
    # earlier in the loop do not corrupt the cardinality key for later segments.
    for i in range(len(segments)):
        # Skip if Prong 1 already classified this position.
        if segments[i] != raw_segments[i]:
            continue

        seg_raw = raw_segments[i]
        parent = tuple(raw_segments[:i])
        key = (netloc, parent)
        path_str = "/" + "/".join(raw_segments[: i + 1])
        stats_key = (netloc, path_str)

        # 2B: navigation signals — keep the path as static if seen in nav.
        is_nav_static = False
        if segment_stats is not None:
            stats = segment_stats.get(stats_key)
            if stats is not None and stats.nav_link_count >= 2:
                is_nav_static = True

        if not is_nav_static:
            # 2C: forced dynamic parents from HTML analysis
            if (
                forced_dynamic_parents is not None
                and key in forced_dynamic_parents
            ):
                static = (observed_static_segments or {}).get(key, set())
                if seg_raw not in static:
                    segments[i] = ":slug"
            # 2A: cardinality-based collapsing
            elif observed_last_segment_values is not None:
                vals = observed_last_segment_values.get(key)
                if vals and len(vals) >= SLUG_CARDINALITY_THRESHOLD:
                    static = (observed_static_segments or {}).get(key, set())
                    if seg_raw not in static:
                        segments[i] = ":slug"

    path = ("/" + "/".join(segments)) if segments else "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


# Runtime configuration
CONCURRENT_WORKERS = 4
MAX_DEPTH = 2
HEADLESS = False
# When a parent path produces more than this many distinct last-segment values,
# treat the last segment as a dynamic slug and collapse it to ':slug'.
SLUG_CARDINALITY_THRESHOLD = 5
# Resource types and URL patterns to block for speed
BLOCK_RESOURCE_TYPES = ("image", "font")
BLOCK_URL_PATTERNS = ("google-analytics", "api.mixpanel", "doubleclick.net", "googlesyndication")


def sanitize_segment(segment: str) -> str:
    # Keep alphanumerics, hyphens and underscores; replace others with '_'
    s = ''
    for c in segment:
        if c.isalnum() or c in ('-', '_'):
            s += c
        else:
            s += '_'
    return s or 'index'


def route_to_dir(start_url: str, page_url: str) -> str:
    """Return scrape-results directory for a page URL using Next.js-style routing.

    Examples:
      https://example.com/         -> scrape-results/example.com/index/screenshot.png
      https://example.com/about    -> scrape-results/example.com/about/screenshot.png
      https://example.com/a/b      -> scrape-results/example.com/a/b/screenshot.png
    """
    parsed = urlparse(page_url)
    host = parsed.netloc or urlparse(start_url).netloc
    path = parsed.path or '/'
    if path in ('', '/'):
        route = 'index'
    else:
        segments = [sanitize_segment(seg) for seg in path.split('/') if seg]
        route = os.path.join(*segments)
    return os.path.join('scrape-results', host, route)

async def crawl_and_screenshot(start_url):
    # screenshots are saved per-page under `scrape-results/<host>/<route>/screenshot.png`
    netloc_start = urlparse(start_url).netloc
    visited: set[str] = set()
    # observed last-segment values keyed by (netloc, parent_tuple)
    observed_last_segment_values: dict = {}
    # segments locked in as "known static" before cardinality threshold was hit
    observed_static_segments: dict = {}
    # per-path navigation / structural signals -- keyed by (netloc, path_str)
    segment_stats: dict[tuple[str, str], SegmentStats] = {}
    # parent paths flagged as dynamic by HTML analysis (Prong 2C)
    forced_dynamic_parents: set[tuple[str, tuple[str, ...]]] = set()

    async with STEALTH.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-infobars",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-client-side-phishing-detection",
                "--disable-component-extensions-with-background-pages",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-features=TranslateUI",
                "--disable-hang-monitor",
                "--disable-ipc-flooding-protection",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-renderer-backgrounding",
                "--disable-sync",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--safebrowsing-disable-auto-update",
                "--password-store=basic",
                "--use-mock-keychain",
            ],
            # Chromium's argument parser doesn't recognize a false value for --enable-automation
            ignore_default_args=["--enable-automation"],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
            device_scale_factor=1,
        )
        
        # block images/fonts and known analytics for speed
        async def _route_handler(route):
            req = route.request
            if req.resource_type in BLOCK_RESOURCE_TYPES:
                await route.abort()
                return
            for p in BLOCK_URL_PATTERNS:
                if p in req.url:
                    await route.abort()
                    return
            await route.continue_()

        await context.route("**/*", _route_handler)

        # use an asyncio queue with worker tasks for concurrency
        # queue holds tuples of (requested_url, canonical_key, depth)
        queue: asyncio.Queue[tuple] = asyncio.Queue()
        await queue.put((start_url, canonicalize_url(start_url), 0))
        # lock to make check-and-add on `visited` atomic across workers to solve race condition
        visited_lock = asyncio.Lock()

        async def worker():
            while True:
                try:
                    requested_url, canonical_requested, depth = await queue.get()
                except asyncio.CancelledError:
                    break
                async with visited_lock:
                    if canonical_requested in visited:
                        queue.task_done()
                        continue
                    visited.add(canonical_requested)
                page = await context.new_page()
                try:
                    print(f"Visiting {requested_url} (depth={depth})...")
                    try:
                        await page.goto(requested_url, timeout=8000)
                    except PlaywrightTimeoutError:
                        # proceed; page may still have useful content
                        pass

                    try:
                        await page.wait_for_load_state('domcontentloaded', timeout=4000)
                    except PlaywrightTimeoutError:
                        # domcontentloaded didn't happen in time; continue and check content
                        pass

                    await dismiss_modals(page)

                    # incremental scroll to trigger lazy loads
                    await page.evaluate(
                        "async () => {const step = Math.max(800, window.innerHeight); let pos=0; while(pos < document.body.scrollHeight){window.scrollBy(0, step); await new Promise(r=>setTimeout(r,150)); pos += step;}}"
                    )

                    # detect SPA frameworks (Next.js, Nuxt, React/Vue/Angular markers)
                    try:
                        is_spa = await page.evaluate(
                            "() => !!(window.__NEXT_DATA__ || window.__NUXT__ || document.getElementById('__next') || document.querySelector('[data-reactroot]') || window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || window.__VUE_DEVTOOLS_GLOBAL_HOOK__ || window.angular)"
                        )
                    except Exception:
                        is_spa = False
                    if is_spa:
                        print(f"Detected SPA on {requested_url}")

                    final_url = page.url
                    # if the canonical form of the fetched URL differs from the
                    # canonical form of the requested URL, print a message and
                    # skip further processing for this request
                    canonical_final = canonicalize_url(
                        final_url,
                        observed_last_segment_values,
                        observed_static_segments,
                        segment_stats,
                        forced_dynamic_parents,
                    )
                    try:
                        canonical_requested = canonicalize_url(
                            requested_url,
                            observed_last_segment_values,
                            observed_static_segments,
                            segment_stats,
                            forced_dynamic_parents,
                        )
                    except Exception:
                        canonical_requested = requested_url
                    if canonical_final != canonical_requested:
                        print(f"Canonicalized {requested_url} -> {canonical_final}; skipping.")
                        continue
                    # If the page routed off-site, skip link extraction
                    if urlparse(final_url).netloc != urlparse(start_url).netloc:
                        print(f"Redirected off-site to {final_url}; skipping.")
                        continue
                    else:
                        # Extract links (fast JS extraction)
                        try:
                            link_data = await page.eval_on_selector_all(
                                'a[href]',
                                """els => els.map(e => ({
                                    href: e.href,
                                    inNav: e.closest('nav, header, footer') !== null
                                }))""",
                            )
                        except Exception:
                            link_data = []
                        for item in link_data:
                            full_url = item["href"]
                            in_nav = item["inNav"]
                            try:
                                p = urlparse(full_url)
                                segs = [s for s in (p.path or '/').split('/') if s]
                                # Record cardinality and nav stats for EVERY segment
                                # position so that middle segments like the company
                                # name in /co/{company}/jobs are tracked correctly.
                                for i, seg in enumerate(segs):
                                    seg_parent = tuple(segs[:i])
                                    seg_key = (p.netloc, seg_parent)
                                    # Prong 2A: cardinality tracking
                                    cardinality_set = observed_last_segment_values.setdefault(seg_key, set())
                                    static_set = observed_static_segments.setdefault(seg_key, set())
                                    # Lock in segments seen before threshold as static
                                    if len(cardinality_set) < SLUG_CARDINALITY_THRESHOLD:
                                        static_set.add(seg)
                                    # Cap to avoid unbounded growth
                                    if len(cardinality_set) <= SLUG_CARDINALITY_THRESHOLD:
                                        cardinality_set.add(seg)
                                    # Prong 2B: nav/structural signals
                                    path_str = "/" + "/".join(segs[: i + 1])
                                    stats_key = (p.netloc, path_str)
                                    stats = segment_stats.get(stats_key)
                                    if stats is None:
                                        stats = SegmentStats(first_seen_depth=depth)
                                        segment_stats[stats_key] = stats
                                    stats.in_link_count += 1
                                    if in_nav:
                                        stats.nav_link_count += 1
                                # canonicalize with observed slugs + nav stats
                                canon = canonicalize_url(
                                    full_url,
                                    observed_last_segment_values,
                                    observed_static_segments,
                                    segment_stats,
                                    forced_dynamic_parents,
                                )
                            except Exception:
                                continue
                            if p.netloc == netloc_start and canon not in visited:
                                if depth + 1 <= MAX_DEPTH:
                                    await queue.put((full_url, canon, depth + 1))

                    out_dir = route_to_dir(start_url, canonical_final)
                    os.makedirs(out_dir, exist_ok=True)
                    
                    screenshot_path = os.path.join(out_dir, "screenshot.png")
                    await page.screenshot(path=screenshot_path, full_page=False)

                    html_path = os.path.join(out_dir, "page.html")
                    html_content = await page.content()
                    with open(html_path, 'w', encoding='utf-8') as f:
                        soup = BeautifulSoup(html_content, 'html.parser')
                        f.write(soup.prettify())

                    # --- Prong 2C: lazy HTML analysis ---
                    # If the saved page shows dynamic-template signals,
                    # mark its parent path so future siblings collapse to :slug.
                    if analyze_html_signals(html_path):
                        final_parsed = urlparse(final_url)
                        final_segs = [
                            s for s in (final_parsed.path or "/").split("/") if s
                        ]
                        if final_segs:
                            parent_key = (
                                final_parsed.netloc,
                                tuple(final_segs[:-1]),
                            )
                            forced_dynamic_parents.add(parent_key)


                except Exception as e:
                    print(f"Error on {requested_url}: {e}")
                finally:
                    await page.close()
                    queue.task_done()

        # start worker tasks
        workers = [asyncio.create_task(worker()) for _ in range(CONCURRENT_WORKERS)]
        await queue.join()
        for w in workers:
            w.cancel()
        
        await browser.close()

async def dismiss_modals(page):
    # Try to dismiss common modals
    selectors = [
        'button[aria-label="Close"]',
        'button:has-text("Close")',
        'button:has-text("Accept")',
        'button:has-text("OK")',
        '.modal .close',
        '#cookie-banner button',
    ]
    for selector in selectors:
        try:
            await page.locator(selector).first.click(timeout=1000)
        except:
            pass
    # Wait a bit
    await page.wait_for_timeout(1000)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <URL>")
        sys.exit(1)
    start_url = sys.argv[1]
    try:

        asyncio.run(crawl_and_screenshot(start_url))

    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        print("GG")
