# graphclone

graphclone is an advanced, stealthy production-grade website mapper. It crawls complex directory structures and distills them into a structural abstraction designed to feed a TypeScript React wireframe builder, which later exports comprehensive PDFs for software engineering teams and client project scoping.

## Features
- 🛡️ **Enterprise Bot Protection Bypass:** Bypasses Cloudflare, DataDome, and other advanced anti-bot protections. Instead of relying on predictable JavaScript proxy injections that trigger deep profiling, Dominatrix leverages genuine Chrome signatures in non-headless mode with realistic, native browser fingerprints.
- 🔐 **Authenticated Scraping Flow:** Supports crawling gated content that requires user authentication. Simply enable `WAIT_FOR_MANUAL_LOGIN` in the configuration, provide your credentials manually when the browser spawns, press `Enter`, and the crawler will seamlessly map the internal authenticated site structure with its automated workers.
- 🧠 **Smart URL Canonicalization:** Employs structural heuristics, navigation cardinality, and schema analysis to map unpredictable dynamic URLs (e.g., infinite scrolling pages, user profiles, or raw hashes) into clean static templates, guaranteeing a complete site map without infinite looping.
- 🖼️ **Wireframe & PDF Generation Pipeline:** Mapped structural data, HTML content, and screenshots feed directly into the modern Next.js TypeScript app (`/wireframe`), which visually reconstructs each page and its component breakdowns for contract scoping.

## Architecture
- **Scraper (`main.py`)**: Asynchronous Python + Playwright stealth crawler generating `.html` and `screenshot.png` outputs structurally organized in the `/scrape-results` directory.
- **Wireframe Builder (`/wireframe`)**: A complete Next.js / TypeScript project that consumes mapped components for rendering.

## Setup & Installation

**1. Install Python Dependencies**
```bash
pip install -r requirements.txt
playwright install chrome
```

**2. Setup Next.js Wireframe Builder**
```bash
cd wireframe
npm install
```

## Usage

**1. Run the Mapper**
Run the core crawling script against your target start URL:
```bash
python main.py <URL>
```
**2. Authentication (Optional)**
Edit your `config.py` and set `WAIT_FOR_MANUAL_LOGIN = True`. 
When initialized, a visible Chrome window will open. Manually log into your account, close out of any extraneous popups or 2FA, switch back to your terminal, and press **Enter** to hand off the authenticated context to the asynchronous crawlers. 

*(Output mapped results will seamlessly reflect an `_logged_in` route suffix so you can distinguish public/private structural runs).*
