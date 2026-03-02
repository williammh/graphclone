# Concurrency and crawl limits
CONCURRENT_WORKERS = 4
MAX_DEPTH = 2

# Browser
HEADLESS = False

# When a parent path produces more than this many distinct last-segment values,
# treat the last segment as a dynamic slug and collapse it to ':slug'.
SLUG_CARDINALITY_THRESHOLD = 5

# Wait for manual login before crawling
WAIT_FOR_LOGIN = True

# Stealth mode selection: "stealth" uses a larger set of flags; "standard" is smaller
 # "stealth" or "standard"
STEALTH_MODE = "standard" 

# Browser args for the two modes
STANDARD_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--disable-blink-features=AutomationControlled",
]

STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-zygote",
    "--disable-blink-features=AutomationControlled",
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
]
