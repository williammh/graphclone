# Graphclone

Graphclone is a structural website mapping tool that crawls complex site hierarchies and converts them into a normalized graph abstraction. The resulting structure feeds a TypeScript/React wireframe builder that generates visual documentation and exportable artifacts for engineering scoping and architectural analysis.
Graphclone is intended for authorized environments such as internal systems, owned properties, or sites where you have explicit permission to perform automated analysis.
## Features
Structural Crawling
Traverses nested directory structures and dynamic routing patterns while preventing infinite loops and redundant traversal.
Authenticated Session Support
Supports crawling authenticated environments.
When WAIT_FOR_LOGIN is enabled, a visible browser session launches, allowing manual login before automated traversal continues using the authenticated context to scrape gated content.
URL Canonicalization
Applies structural heuristics to normalize dynamic URLs (e.g., parameterized routes, infinite scrolling patterns, hashed segments) into reusable route templates. This prevents duplicate mapping and ensures stable structural output.
## Snapshot & Screenshot Capture
For each mapped page, graphclone stores:
- Raw HTML snapshot
- Page screenshot
- Canonicalized route metadata

## Wireframe & Export Pipeline
Structured outputs feed directly into a Next.js TypeScript application (/wireframe) that reconstructs page layouts and component hierarchies for review, documentation, and scoping workflows.
## Architecture
- Scraper (main.py)
- Asynchronous Python
- Playwright-driven browser automation
## Output stored in /scrape-results

- HTML snapshots
- screenshot.png
- Route metadata
- Wireframe Builder (/wireframe)
- Next.js
- TypeScript
- Consumes structural mapping output
- Renders interactive wireframes
- Supports PDF export

## Setup & Installation

1. Install Python Dependencies
Bash
Copy code
pip install -r requirements.txt
playwright install chrome
2. Setup Next.js Wireframe Builder
Bash
Copy code
cd wireframe
npm install
Usage
1. Run the Mapper
Bash
Copy code
python main.py <URL>
2. Authenticated Mode (Optional)
In config.py:
Python
Copy code
WAIT_FOR_LOGIN = True
When enabled:
A visible browser window opens.
Manually authenticate.
Return to the terminal and press Enter.
Crawling continues using the authenticated session.
Authenticated runs may optionally be labeled with a suffix (e.g., _logged_in) to distinguish them from public crawls.


## Unit tests
`python -m pytest tests -q`