# Graphclone

Graphclone is a structural website mapping tool that crawls complex site hierarchies and converts them into a normalized graph abstraction. The resulting structure feeds a TypeScript/React wireframe builder that generates visual documentation and exportable artifacts for engineering scoping and architectural analysis.
Graphclone is intended for authorized environments such as internal systems, owned properties, or sites where you have explicit permission to perform automated analysis.

## ✨ Features

### 🌐 Structural Crawling
- Traverses nested directory structures and dynamic routing patterns while preventing infinite loops and redundant traversal.

### 🔒 Authenticated Session Support
- `WAIT_FOR_LOGIN` allows the user to login with their credentials like they would normally
- Keeps passwords private by never requiring your password to be entered into Graphclone
- Enables scraping of gated content.

### 🔗 URL Canonicalization
- Applies structural heuristics to normalize dynamic URLs
- Handles parameterized routes to prevent duplicate mapping
- Configurable thresholds for predictable outputs

### 📸 Snapshot & Screenshot Capture 
- Raw HTML snapshot
- Page screenshot
- Canonicalized route metadata

### 🧩 Wireframe & Export Pipeline 
Structured outputs feed directly into a Next.js TypeScript application `/wireframe` that reconstructs page layouts and component hierarchies for review, documentation, and scoping workflows.

### 🏗️ Architecture 
- Scraper (main.py)
- Asynchronous Python
- Playwright-driven browser automation

### 📁 Output stored in /scrape-results 
- HTML snapshots
- screenshot.png
- Route metadata
- Wireframe Builder `/wireframe`
- Next.js
- TypeScript
- Consumes structural mapping output
- Renders interactive wireframes
- Supports PDF export

### ⚙️ Setup & Installation 

1. Install Python Dependencies
`pip install -r requirements.txt`
and `playwright install chrome`
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
`WAIT_FOR_LOGIN = True` When enabled: A visible browser window opens. Log into your website as you normally would. Return to the terminal and press Enter. Crawling continues using the authenticated session.
Authenticated runs are be labeled with a suffix in the `_logged_in` to distinguish them from public crawls.
5. With the scrape results, feed into an LLM of your choice (`.github/agents/graphclone-builder.md` is recommended) to output to `/wireframe`
6. Generate your Product requirements document with `python generate_prd.py`


### 🧪 Automated tests 
`python -m pytest tests -q`