# TODO: InvestTalk Podcast Notes Automation Improvements

This document tracks completed features, active architectural improvements, and proposed future features for the InvestTalk podcast notes extraction pipeline.

---

## ✅ Completed Tasks

- [x] **Robust Date & Timezone Parsing:** Switched to `email.utils.parsedate_to_datetime` and applied `ZoneInfo("America/Los_Angeles")` to resolve publication timestamps to local Pacific air dates (`rss_extractor.py`).
- [x] **Modular Architecture:** Refactored RSS parsing, feed url lookups, and episode filtering into `rss_extractor.py`.
- [x] **Weekend Restriction Removal:** Removed weekend checks to allow file generation and catch-up runs whenever the script is executed.
- [x] **Jinja2 HTML Templating:** Decoupled HTML generation from inline strings into `templates/summary_template.html` using Jinja2.
- [x] **Google Finance Link Integration:** Automatically resolve listing exchanges (`NASDAQ`, `NYSE`, etc.) and render ticker links (`https://www.google.com/finance/quote/AVGO:NASDAQ`) in Markdown and HTML.
- [x] **Noise & Blacklist Filtering:** Filter out non-ticker parenthetical abbreviations (e.g. `(AI)`, `(US)`, `(GDP)`) using `blacklist.txt`.
- [x] **Script-Relative Paths:** Resolved template loading using `os.path.dirname(os.path.abspath(__file__))`.
- [x] **Google Sheets Cleanup:** Removed legacy `gspread` and `google-auth` code for a cleaner local-first file database architecture.

---

## 🚀 Proposed Future Enhancements

### 1. GitHub Actions 24/7 Automated Workflow with GitHub Models
- **Goal:** Run the extraction pipeline automatically every weekday at 7:00 PM Pacific on GitHub's cloud servers.
- **LLM Provider:** Integrate **GitHub Models** (`gpt-4o-mini` / `Llama-3.3-70B`) via `https://models.inference.ai.azure.com` authenticated using built-in `secrets.GITHUB_TOKEN`.
- **Benefit:** Guarantees daily updates to `summary.md` and `summary.html` even when your personal laptop is closed or turned off, with **zero external API key management**.

### 2. Client-Side Search & Filter Bar for HTML Dashboard
- **Goal:** Add a lightweight search input and filter buttons in `templates/summary_template.html`.
- **Benefit:** Allows users to filter by ticker symbol (e.g. `AVGO`), verdict (`Buy`, `Sell`, `Hold`), or keyword directly in the browser without reloading the page.

### 3. Rolling 30-Day Market & Sector Sentiment Analytics
- **Goal:** Add a CLI flag `--analytics` or a summary card aggregating host sentiment trends across sectors (e.g., Tech vs. Energy vs. Utilities).
- **Benefit:** Provides macro-level insights into how host sentiment evolves over time.

### 4. Automated Webhook Notifications (Discord / Telegram / Slack)
- **Goal:** Add an optional webhook trigger in `extract_tickers.py` to post a daily summary message to a Discord channel or Telegram bot when a new episode is processed.

### 5. Structured Static JSON API Export (`api/episodes.json`)
- **Goal:** Output a clean `api/episodes.json` static file on every build.
- **Benefit:** Makes the historical data easily consumable by third-party mobile apps, widgets, or web portals.

### 6. Credit KPPfinancial
- **Goal:** Clearly credit KPPfinancial and link to their site in the outputs.

### 7. 'Driving Mode' ReadAloud Integration
- **Goal:** Add a button to enable a simple chrome extension like ReadAloud that will read back the summary. Call it 'Driving Mode'.
