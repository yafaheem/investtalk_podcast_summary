import os
import re
import sys
import json
import argparse
import urllib.request
from datetime import datetime

# Optional dependencies loaded dynamically
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rss_extractor import get_feed_url, parse_rss_feed
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

TICKER_EXCHANGE_MAP = {
    "AVGO": "NASDAQ", "NEM": "NYSE", "CINF": "NASDAQ", "POWR": "NASDAQ",
    "VOLT": "NASDAQ", "AIPO": "NASDAQ", "RDDT": "NASDAQ", "SFM": "NASDAQ",
    "COHR": "NYSE", "DIVB": "NASDAQ", "LII": "NYSE", "ABNB": "NASDAQ",
    "CHTR": "NASDAQ", "MU": "NASDAQ", "EWY": "NYSEARCA", "SKHY": "NASDAQ",
    "CELH": "NASDAQ", "COST": "NASDAQ", "SPGI": "NYSE", "ANET": "NYSE",
    "RELX": "NYSE", "MO": "NYSE", "PM": "NYSE", "ZIM": "NYSE",
    "NFLX": "NASDAQ", "ZION": "NASDAQ", "AVAV": "NASDAQ", "TTMI": "NASDAQ",
    "TS": "NYSE", "BTG": "NYSE", "MUSA": "NYSE", "GGG": "NYSE",
    "RMBS": "NASDAQ", "VRT": "NYSE", "FLIN": "NYSEARCA", "OKE": "NYSE",
    "MSFT": "NASDAQ", "CNSWF": "OTCMKTS", "KARO": "SGX", "MELI": "NASDAQ",
    "WMB": "NYSE", "EQT": "NYSE", "MOS": "NYSE", "VHT": "NYSEARCA",
    "IXJ": "NYSEARCA", "BKE": "NYSE"
}

def get_google_finance_url(ticker, exchange=None):
    """Generate a valid Google Finance quote URL for a stock ticker."""
    if not ticker:
        return ""
    ex = exchange or TICKER_EXCHANGE_MAP.get(ticker.upper(), "NASDAQ")
    return f"https://www.google.com/finance/quote/{ticker.upper()}:{ex.upper()}"


def extract_tickers_from_description(description):
    """Extract tickers inside parentheses from the show description."""
    # Find patterns like (AVAV), (TTMI), (TS), (BTG)
    tickers = re.findall(r'\(([A-Z]{1,5})\)', description)
    # Remove common non-ticker capital abbreviations of length 1-5
    blacklist = {"AI", "US", "USA", "ETF", "IPO", "GDP", "EPS", "FED", "SEC", "REIT", "IRA", "YOY", "QOQ", "CEO", "CFO"}
    # Remove duplicates but keep order
    seen = set()
    unique_tickers = [x for x in tickers if x not in blacklist and not (x in seen or seen.add(x))]
    return unique_tickers

def clean_vtt(vtt_text):
    """Clean WebVTT transcript file into speaker turns plain text."""
    lines = vtt_text.splitlines()
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == 'WEBVTT':
            continue
        if '-->' in line:
            continue
        if line.startswith('NOTE') or line.startswith('STYLE'):
            continue
        if re.match(r'^\d+$', line):
            continue
        clean_lines.append(line)
        
    turns = []
    current_speaker = None
    current_text = []
    
    for line in clean_lines:
        speaker_match = re.match(r'^\[([^\]]+)\]:\s*(.*)', line)
        if speaker_match:
            if current_text:
                turns.append(f"{current_speaker}: {' '.join(current_text)}")
            current_speaker = speaker_match.group(1)
            current_text = [speaker_match.group(2)]
        else:
            if current_speaker:
                current_text.append(line)
            else:
                turns.append(line)
                
    if current_text and current_speaker:
        turns.append(f"{current_speaker}: {' '.join(current_text)}")
        
    return '\n'.join(turns)

def fetch_transcript_data(vtt_url):
    """Download the raw VTT text from the WebVTT URL."""
    if not vtt_url:
        return None
    req = urllib.request.Request(vtt_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode('utf-8')

def fetch_transcript(vtt_url):
    """Download and clean the transcript from WebVTT URL."""
    vtt_text = fetch_transcript_data(vtt_url)
    if not vtt_text:
        return None
    return clean_vtt(vtt_text)

def run_gemini_extraction(transcript, tickers, api_key):
    """Call Gemini to extract stock ticker recommendations and reasons from transcript."""
    # Try importing google-genai
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Analyze the following podcast transcript. Focus on discussions regarding these stock tickers: {', '.join(tickers)}.\n\n"
            "For each ticker, extract the host's opinion and recommendation:\n"
            "- Exchange: The primary listing exchange for the stock (e.g. NASDAQ, NYSE, AMEX, OTCMKTS).\n"
            "- Recommendation: Buy, Sell, Hold, Watchlist, or Neutral.\n"
            "- Reason: A concise summary of their reasoning or key arguments mentioned.\n\n"
            "Format the output strictly as a JSON list of objects, e.g.:\n"
            "[\n"
            "  {\"ticker\": \"TICKER\", \"exchange\": \"NASDAQ/NYSE\", \"recommendation\": \"Buy/Sell/Hold/Neutral\", \"reason\": \"Summary of arguments\"}\n"
            "]\n\n"
            f"Transcript:\n{transcript}"
        )

        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error calling google-genai: {e}")
        # Try fallback to google-generativeai
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=api_key)
            model = legacy_genai.GenerativeModel('gemini-1.5-flash')
            prompt = (
                f"Analyze the following podcast transcript. Focus on discussions regarding these stock tickers: {', '.join(tickers)}.\n\n"
                "For each ticker, extract the host's opinion and recommendation:\n"
                "- Recommendation: Buy, Sell, Hold, or Neutral.\n"
                "- Reason: A concise summary of their reasoning or key arguments mentioned.\n\n"
                "Format the output strictly as a JSON list of objects, e.g.:\n"
                "[\n"
                "  {\"ticker\": \"TICKER\", \"recommendation\": \"Buy/Sell/Hold/Neutral\", \"reason\": \"Summary of arguments\"}\n"
                "]"
            )
            response = model.generate_content(prompt + f"\n\nTranscript:\n{transcript}")
            # Extract JSON from Markdown code blocks if any
            text = response.text.strip()
            if text.startswith("```json"):
                text = text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            elif text.startswith("```"):
                text = text.split("```", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e_legacy:
            print(f"Legacy google-generativeai call failed: {e_legacy}")
            raise e

def generate_topic_summary(transcript, api_key):
    """Call Gemini to generate a summary of the main podcast topic, excluding stock Q&A."""
    prompt = (
        "Analyze the following podcast transcript. Identify the main market, economic, or educational topic "
        "discussed by the hosts. Write a concise summary (around 1-3 paragraphs) of this topic.\n\n"
        "CRITICAL: Do NOT include discussions, opinions, or recommendations about specific stock tickers "
        "that callers asked about. Focus only on the main, general educational or market topic discussed.\n\n"
        f"Transcript:\n{transcript}"
    )

    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error calling google-genai for topic summary: {e}")
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=api_key)
            model = legacy_genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e_legacy:
            print(f"Legacy google-generativeai call for topic summary failed: {e_legacy}")
            raise e


def save_episode_data(date_str, title, summary, recommendations):
    """Save episode data to summaries_data.json and return the full dictionary."""
    db_file = "summaries_data.json"
    data = {}
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load existing database ({e}). Creating new.")
            
    data[date_str] = {
        'title': title,
        'summary': summary,
        'recommendations': recommendations
    }
    
    try:
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving database: {e}")
        
    return data

def generate_cumulative_markdown(episodes):
    """Generate a single unified Markdown file with all episodes sorted by date descending."""
    filename = "summary.md"
    content = [
        "# InvestTalk Episode Summaries",
        "",
        "This file contains cumulative summaries and stock ticker verdicts extracted from the InvestTalk podcast.",
        "",
    ]
    
    sorted_dates = sorted(episodes.keys(), reverse=True)
    for idx, date_str in enumerate(sorted_dates):
        ep = episodes[date_str]
        content.extend([
            f"## Episode: {ep['title']}",
            f"**Date:** {date_str}",
            "",
            "### Topic Summary",
            ep['summary'],
            "",
            "### Stock Discussions & Verdicts",
            "| Ticker | Verdict | Reason |",
            "|---|---|---|",
        ])
        
        for rec in ep.get('recommendations', []):
            ticker = rec.get('ticker', '')
            exchange = rec.get('exchange')
            verdict = rec.get('recommendation', '')
            reason = rec.get('reason', '')
            reason_escaped = reason.replace("|", "\\|")
            url = get_google_finance_url(ticker, exchange)
            ticker_cell = f"[{ticker}]({url})" if ticker else ""
            content.append(f"| {ticker_cell} | {verdict} | {reason_escaped} |")

            
        content.append("")
        if idx < len(sorted_dates) - 1:
            content.append("---")
            content.append("")
            
    content_str = "\n".join(content) + "\n"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content_str)
    print(f"Successfully updated unified Markdown summary file: {filename}")

def generate_cumulative_html(episodes):
    """Generate a unified, styled HTML file with all episodes sorted by date descending."""
    filename = "summary.html"
    
    def md_to_html(text):
        import html
        escaped = html.escape(text)
        formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped)
        return Markup(formatted)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(script_dir, 'templates')
    
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template('summary_template.html')
    
    html_content = template.render(
        episodes=episodes,
        md_to_html=md_to_html,
        get_google_finance_url=get_google_finance_url
    )

    
    for fname in ["summary.html", "index.html"]:
        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Successfully updated unified HTML summary file: {fname}")
        except Exception as e:
            print(f"Warning: Could not write {fname}: {e}")

def main():
    parser = argparse.ArgumentParser(description="InvestTalk Stock Ticker Extractor")
    parser.add_argument("--dry-run", action="store_true", help="Download and parse transcript locally without calling API")
    parser.add_argument("--date", help="Target episode publication date (YYYY-MM-DD)")
    parser.add_argument("--start-date", help="Start of range publication date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End of range publication date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Force extraction even if episode is cached")
    args = parser.parse_args()
    
    print("Resolving RSS Feed URL...")
    feed_url = get_feed_url()
    print(f"RSS Feed URL: {feed_url}")
    
    print("Parsing feed for episodes...")
    try:
        episodes = parse_rss_feed(
            feed_url, 
            target_date=args.date, 
            start_date=args.start_date, 
            end_date=args.end_date
        )
    except ValueError as e:
        print(f"Warning: {e}")
        episodes = []
    
    # Load existing summaries database to support caching checks
    db_file = "summaries_data.json"
    episodes_db = {}
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                episodes_db = json.load(f)
        except Exception:
            pass
            
    # API key check
    api_key = None
    if not args.dry_run:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                from google.colab import userdata
                api_key = userdata.get("GEMINI_API_KEY")
            except ImportError:
                pass
        if not api_key:
            print("Error: GEMINI_API_KEY not found in environment or Colab secrets.")
            print("Please set it in your environment or use --dry-run.")
            sys.exit(1)

    print(f"Found {len(episodes)} matching episode(s) to process.")
    
    for idx, episode in enumerate(episodes):
        date_str = episode['date_str']
        print(f"\n[{idx+1}/{len(episodes)}] Processing Episode: {episode['title']}")
        print(f"Date: {date_str} (parsed from: {episode['pub_date']})")
        
        # Check cache
        if date_str in episodes_db and not args.force:
            print(f"-> Episode for {date_str} already processed and cached in summaries_data.json. Skipping.")
            continue
            
        tickers = extract_tickers_from_description(episode['description'])
        print(f"Tickers found in description: {tickers}")
        
        print("Fetching and cleaning transcript...")
        transcript = fetch_transcript(episode['vtt_url'])
        if not transcript:
            print("-> Warning: No transcript URL found or failed to fetch transcript. Skipping.")
            continue
            
        print(f"Transcript length: {len(transcript)} characters.")
        
        if args.dry_run:
            print("[DRY RUN MODE] Generating placeholder data...")
            placeholder_recs = [{"ticker": t, "recommendation": "Buy (Dry Run Placeholder)", "reason": "Reason (Dry Run Placeholder)"} for t in tickers]
            episodes_db = save_episode_data(
                date_str, 
                episode['title'], 
                "This is a dry-run placeholder summary of the main topic.", 
                placeholder_recs
            )
            continue
            
        # Live processing
        print("Running Gemini LLM extraction...")
        results = []
        if tickers:
            try:
                results = run_gemini_extraction(transcript, tickers, api_key)
            except Exception as e:
                print(f"Error extracting ticker recommendations: {e}")
                results = [{"ticker": t, "recommendation": "Error", "reason": f"Failed to extract: {e}"} for t in tickers]
        else:
            print("No tickers to extract recommendations for.")
            
        print("Generating Gemini Topic Summary...")
        try:
            topic_summary = generate_topic_summary(transcript, api_key)
        except Exception as e:
            print(f"Error generating topic summary: {e}")
            topic_summary = f"Error generating summary: {e}"
            
        print("\nTopic Summary:")
        print(topic_summary)
        
        # Save to database
        episodes_db = save_episode_data(date_str, episode['title'], topic_summary, results)
        
    # Post loop updates
    print("\nRegenerating cumulative summary files...")
    generate_cumulative_markdown(episodes_db)
    generate_cumulative_html(episodes_db)
        
    print("\nExecution completed successfully!")

if __name__ == "__main__":
    main()
