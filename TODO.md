# TODO: InvestTalk Podcast Notes Automation Improvements

This document tracks completed features, active architectural improvements, and proposed future features for the InvestTalk podcast notes extraction pipeline.

---

## ✅ Completed Tasks

- [x] **KPP Financial Header & Podcast Links:** Added a modern pill-style credit banner inside the dashboard header (`templates/summary_template.html`), clearly stating that this dashboard is a personal project summarizing the 1-hour weekday podcast created by KPP Financial, alongside direct hyperlinks to their official advisory site and full episode audio hub.
- [x] **'Driving Mode' Native Replay Widget with Neural Edge-TTS:** Implemented an interactive audio playback engine directly inside the HTML dashboard (`templates/summary_template.html`). Integrates Microsoft `edge-tts` in Python to pre-render hyper-realistic neural `.mp3` podcast summary narration (`en-US-AriaNeural`), complete with Apple Podcasts-inspired minimalist controls, smooth seeking, and automatic client-side Web Speech API fallback.

- [x] **GitHub Actions 24/7 Automated Workflow:** Configured `.github/workflows/daily_extraction.yml` to automatically execute the extraction pipeline every weekday at 7:00 PM Pacific (with manual workflow dispatch support) using GitHub Actions, guaranteeing consistent daily summary generation without requiring a local machine.
- [x] **Git Repository & Tracking Cleanup:** Untracked dynamically generated runtime data and compiled markdown/HTML view files (`summaries_data.json`, `summary.html`, `summary.md`) and added them to `.gitignore` to prevent unnecessary git commit churn and automated merge conflicts.
- [x] **Robust Date & Timezone Parsing:** Switched to `email.utils.parsedate_to_datetime` and applied `ZoneInfo("America/Los_Angeles")` to accurately resolve publication timestamps to local Pacific air dates (`rss_extractor.py`).
- [x] **Modular Architecture:** Refactored RSS parsing, feed URL lookups, and episode filtering into a standalone module (`rss_extractor.py`).
- [x] **Weekend Restriction Removal:** Removed hardcoded weekday restrictions to enable catch-up extraction runs and manual template regeneration regardless of the day of the week.
- [x] **Jinja2 HTML Templating:** Decoupled HTML layout generation from Python string concatenation into dedicated template files (`templates/summary_template.html`) using Jinja2.
- [x] **Google Finance Link Integration:** Automatically resolve listing exchanges (`NASDAQ`, `NYSE`, etc.) and render hyperlinked tickers (`https://www.google.com/finance/quote/AVGO:NASDAQ`) across Markdown and HTML dashboards.
- [x] **Noise & Blacklist Filtering:** Filter out non-ticker parenthetical macro abbreviations (e.g. `(AI)`, `(US)`, `(GDP)`) using an external `blacklist.txt` dictionary.
- [x] **Script-Relative Paths:** Enhanced reliability of template and configuration file loading using script-relative directory paths (`os.path.dirname(os.path.abspath(__file__))`).
- [x] **Local-First Architecture Cleanup:** Removed legacy `gspread` and `google-auth` sheet integrations in favor of a fast, portable local file database architecture.

---

## 🚀 Proposed Future Enhancements

### 1. Client-Side Search & Filter Bar for HTML Dashboard
- **Goal:** Add a lightweight search input and filter buttons directly into the dashboard (`templates/summary_template.html`).
- **Benefit:** Allows listeners to instantly filter historical discussions by ticker symbol (e.g., `AVGO`), verdict (`Buy`, `Sell`, `Hold`), or keyword without page reloads.

### 2. Rolling 30-Day Market & Sector Sentiment Analytics
- **Goal:** Introduce an analytical visual card or CLI flag (`--analytics`) aggregating host sentiment trends and sector weightings (e.g., Technology vs. Energy vs. Utilities) across rolling 30-day timeframes.

### 3. Automated Webhook Notifications (Discord / Telegram / Slack)
- **Goal:** Add optional webhook notification dispatchers in `extract_tickers.py` to instantly post daily episode takeaways and stock verdicts to automated communication channels upon processing.

### 4. Structured Static JSON API Export (`api/episodes.json`)
- **Goal:** Output an agnostic, structured `api/episodes.json` file during each extraction run.
- **Benefit:** Simplifies integration with third-party mobile widgets, personal finance tools, and custom dashboard clients.
