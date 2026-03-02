# Website Crawler and Screenshotter

This Python project uses Playwright to crawl a website starting from a given URL, dismiss common modals and dialogs, scroll to the bottom of each page, and take a screenshot of each page.

## Installation

1. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Install Playwright browsers:
   ```
   playwright install
   ```

## Usage

Run the script with a URL as an argument:
```
python main.py https://example.com
```

This will create a folder `output/example.com/screenshots` and save one screenshot per page visited.

## Features

- Crawls all internal links on the website.
- Dismisses common modals (e.g., cookie banners, close buttons).
- Scrolls to the bottom of each page before taking a screenshot.
- Saves screenshots in PNG format, numbered sequentially.

## Troubleshooting

- Ensure Playwright is installed and browsers are available.
- If the script fails on certain pages, check the console output for errors.