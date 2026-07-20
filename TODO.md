# TODO: InvestTalk Podcast Notes Automation Improvements

This document lists the recommended improvements and bug fixes for the InvestTalk podcast notes extraction project.

## 🐛 Bug Fixes & Reliability Improvements

### 1. Robust Date Parsing
- **Current Issue:** Slicing raw RSS `pubDate` using `pub_date[:25].strip()` assumes a fixed double-digit day-of-month and standard weekday format. Single-digit days (e.g. `Fri, 7 Jul...`) fail `strptime` matching, polluting the database keys and breaking chronological sorting.
- **Proposed Fix:** Use Python's built-in `email.utils.parsedate_to_datetime` to reliably parse RFC 822 format dates regardless of length or timezone format.

### 2. Remove Weekend Execution Restrictions for File Generation
- **Current Issue:** The script checks `is_today_weekend` using `datetime.now()` to skip generating `summary.md` and `summary.html` on weekends. If a user runs the script on Saturday to catch up on Friday's episode, it skips generating the summaries.
- **Proposed Fix:** Remove the check `is_today_weekend` and allow summaries to be generated whenever the script is executed. The actual episodes within the reports are already filtered to weekdays anyway.

### 3. HTML Injection & Special Character Escaping
- **Current Issue:** Values extracted from Gemini are directly inserted into the HTML template without escaping, causing parsing/rendering issues if the reasons contain characters like `&`, `<`, or `>`.
- **Proposed Fix:** Use `html.escape` to escape all values (ticker, verdict, reason, summary) prior to formatting the HTML output.

### 4. Non-Ticker Description Matches (Noise Filtering)
- **Current Issue:** The regex `\(([A-Z]{1,5})\)` matches non-ticker parenthetical abbreviations in show descriptions like `(AI)`, `(US)`, `(GDP)`, `(ETF)`, and `(IPO)`. This leads to useless and potentially hallucinated Gemini queries.
- **Proposed Fix:** Filter out a blacklist of common non-ticker financial and generic abbreviations inside `extract_tickers_from_description`.

---

## ⚡ Performance & Usability Improvements

### 6. Script-Relative Paths for Automation
- **Current Issue:** Paths for `summaries_data.json`, `summary.md`, and `summary.html` are relative to the current working directory, which breaks local file resolution if run via cron, Launchd, or from another folder.
- **Proposed Fix:** Resolve all paths relative to the script directory using `os.path.dirname(os.path.abspath(__file__))`.
