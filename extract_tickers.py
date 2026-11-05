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
from audio_transcriber import is_url, download_audio, transcribe_audio
try:
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup
except ImportError:
    Environment = None
    FileSystemLoader = None
    Markup = str

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
    """Extract tickers inside parentheses or hyphenated lists from the show description."""
    # Pattern 1: (AVAV), (TTMI), (TS), (BTG)
    tickers_paren = re.findall(r'\(([A-Z]{1,5})\)', description)
    # Pattern 2: EME - Emcor group Inc., MDT - Medtronic PLC, CLS- Celestica
    tickers_hyphen = re.findall(r'\b([A-Z]{1,5})\s*-\s*[A-Za-z]', description)
    # Remove common non-ticker capital abbreviations of length 1-5
    blacklist = {"AI", "US", "USA", "ETF", "IPO", "GDP", "EPS", "FED", "SEC", "REIT", "IRA", "YOY", "QOQ", "CEO", "CFO", "GLP"}
    # Remove duplicates but keep order
    seen = set()
    unique_tickers = [x for x in tickers_paren + tickers_hyphen if x not in blacklist and not (x in seen or seen.add(x))]
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

def build_unified_prompt(tickers, transcript=None):
    """
    Build a unified prompt that instructs Gemini to extract BOTH the main educational
    topic summary and all stock ticker verdicts in a single structured JSON response.

    Why this matters:
    Previously, the pipeline made up to 3 separate Gemini requests per episode:
      1. Audio -> Full verbatim text transcript (~12,000 output tokens)
      2. Transcript -> Stock ticker recommendations JSON
      3. Transcript -> Topic summary text
    By combining these into a single structured prompt that works on either a text
    transcript OR directly on an uploaded podcast audio file, we reduce API requests
    by 66% (from 3 calls to 1 call) and eliminate ~35,000+ redundant input/output tokens.
    """
    # Dynamically label the input modality so the prompt reads naturally whether
    # Gemini is reading a WebVTT text transcript or listening to a raw MP3 file.
    source_label = "podcast transcript" if transcript else "podcast episode audio"

    # If regex pre-extracted candidate tickers from the RSS show description, guide
    # Gemini to evaluate those specifically while still allowing discovery of any
    # additional tickers discussed during caller Q&A.
    if tickers:
        ticker_instructions = (
            f"Focus on discussions regarding these stock/ETF tickers: {', '.join(tickers)}.\n"
            "If additional stock/ETF tickers are also substantively evaluated by the hosts, include them as well."
        )
    else:
        # When the RSS description doesn't list tickers in parentheses/hyphens,
        # instruct Gemini to discover every stock/ETF ticker evaluated in the episode.
        ticker_instructions = (
            "Identify all individual stock or ETF tickers that the hosts or callers discussed and evaluated."
        )

    prompt = (
        f"Analyze the following {source_label} and perform two tasks in a single JSON response:\n\n"
        "Task 1 - Topic Summary (`topic_summary`):\n"
        "Identify the main market, economic, or educational topic discussed by the hosts. "
        "Write a concise summary (around 1-3 paragraphs) of this topic.\n"
        "CRITICAL: Do NOT include discussions, opinions, or recommendations about specific stock tickers "
        "that callers asked about in `topic_summary`. Focus only on the main, general educational or market topic discussed.\n\n"
        "Task 2 - Stock Discussions & Verdicts (`recommendations`):\n"
        f"{ticker_instructions}\n"
        "For each ticker discussed, extract the host's opinion and recommendation:\n"
        "- `ticker`: The standard stock/ETF ticker symbol (e.g. AAPL, NVDA, SPY).\n"
        "- `exchange`: The primary listing exchange for the stock (e.g. NASDAQ, NYSE, NYSEARCA, AMEX, OTCMKTS).\n"
        "- `recommendation`: Buy, Sell, Hold, Watchlist, or Neutral.\n"
        "- `reason`: A concise summary of their reasoning or key arguments mentioned.\n\n"
        "Format the output strictly as a single JSON object matching this exact schema:\n"
        "{\n"
        "  \"topic_summary\": \"1-3 paragraph summary of the main educational/market topic...\",\n"
        "  \"recommendations\": [\n"
        "    {\"ticker\": \"TICKER\", \"exchange\": \"NASDAQ/NYSE\", \"recommendation\": \"Buy/Sell/Hold/Watchlist/Neutral\", \"reason\": \"Summary of arguments\"}\n"
        "  ]\n"
        "}"
    )

    # If we are on the fast WebVTT path, append the plain-text transcript directly to the prompt.
    # (If we are on the audio path, the audio file reference is passed alongside the prompt in `contents`.)
    if transcript:
        prompt += f"\n\nTranscript:\n{transcript}"
    return prompt


def _parse_unified_json_response(raw_text):
    """
    Parse and normalize the unified JSON output returned by Gemini.

    Handles:
    1. Stripping optional Markdown code fences (```json ... ```) if returned by legacy models.
    2. Normalizing the standard dict schema: `{"topic_summary": "...", "recommendations": [...]}`.
    3. Gracefully handling edge cases where a model or mock returns a bare JSON list `[...]`.
    """
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
    elif text.startswith("```"):
        text = text.split("```", 1)[1].rsplit("```", 1)[0].strip()

    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return {
            "topic_summary": (parsed.get("topic_summary") or parsed.get("summary") or "").strip(),
            "recommendations": parsed.get("recommendations") if isinstance(parsed.get("recommendations"), list) else []
        }
    elif isinstance(parsed, list):
        # Fallback if a legacy caller/mock returned a raw list of ticker objects
        return {
            "topic_summary": "",
            "recommendations": parsed
        }
    return {"topic_summary": "", "recommendations": []}


def analyze_episode_with_gemini(transcript=None, audio_source=None, tickers=None, api_key=None, model_name="gemini-2.5-flash", temp_dir=None):
    """
    Single unified Gemini entry point that processes EITHER a text transcript OR raw episode audio,
    returning both `topic_summary` and `recommendations` in ONE API request.

    Execution paths:
    - Path A (`transcript` provided):
        Sends `prompt + transcript` directly to `client.models.generate_content()` with
        `response_mime_type="application/json"`. No file upload needed.
    - Path B (`transcript` is None, `audio_source` provided):
        1. If `audio_source` is an HTTP/HTTPS URL, streams the MP3 to a temporary local file.
        2. Uploads the MP3 to Google's GenAI File API (`client.files.upload`).
        3. Calls `client.models.generate_content(contents=[uploaded_file, prompt])` ONCE to
           extract both the topic summary and stock verdicts directly from the audio without
           generating a full verbatim transcript first.
        4. Guarantees cleanup of both the remote File API object (`client.files.delete`)
           and the local temporary MP3 file via nested `finally` blocks.
    """
    if not transcript and not audio_source:
        raise ValueError("Either `transcript` or `audio_source` must be provided.")

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY not found in environment or arguments.")

    # Construct the unified prompt (appends transcript text only if `transcript` is present)
    prompt = build_unified_prompt(tickers or [], transcript=transcript)

    # Step 1: Resolve local audio file if we are on the audio fallback path (no WebVTT transcript)
    temp_audio_path = None
    local_audio_path = None
    if not transcript and audio_source:
        if is_url(audio_source):
            # Stream remote podcast MP3 into a temporary local file
            temp_audio_path = download_audio(audio_source, temp_dir=temp_dir)
            local_audio_path = temp_audio_path
        else:
            # Use existing local file path directly without deleting it afterwards
            if not os.path.isfile(audio_source):
                raise FileNotFoundError(f"Audio file not found: {audio_source}")
            local_audio_path = audio_source

    # Outer try/finally ensures any temporary downloaded MP3 on disk is ALWAYS removed
    try:
        # Primary path: Modern `google-genai` SDK
        try:
            from google import genai
            try:
                from google.genai import types
                gen_config = types.GenerateContentConfig(response_mime_type="application/json")
            except ImportError:
                gen_config = {"response_mime_type": "application/json"}

            client = genai.Client(api_key=key)
            uploaded_file = None

            # Inner try/finally ensures any file uploaded to Google's servers is ALWAYS deleted
            try:
                if local_audio_path:
                    print(f"Uploading audio file '{local_audio_path}' to Google GenAI File API...")
                    uploaded_file = client.files.upload(file=local_audio_path)
                    print(f"Uploaded audio (Name: {uploaded_file.name}). Running unified single-call analysis with {model_name}...")
                    # Multimodal input: pass both the uploaded audio handle and the unified text instructions
                    contents = [uploaded_file, prompt]
                else:
                    # Text-only input: pass the prompt (which already includes the WebVTT transcript)
                    contents = prompt

                # THE SINGLE GEMINI CALL: produces {"topic_summary": ..., "recommendations": [...]}
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=gen_config
                )
                return _parse_unified_json_response(response.text)
            finally:
                # Always delete the remote audio file from Google's File API storage
                if uploaded_file is not None:
                    try:
                        print(f"Cleaning up GenAI File API remote file: {uploaded_file.name}")
                        client.files.delete(name=uploaded_file.name)
                    except Exception as del_err:
                        print(f"Warning: Failed to delete remote file from GenAI File API: {del_err}")

        except Exception as e:
            print(f"Error calling google-genai: {e}")
            # Secondary fallback: Legacy `google-generativeai` SDK
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=key)
                model = legacy_genai.GenerativeModel('gemini-1.5-flash')
                uploaded_file = None
                try:
                    if local_audio_path:
                        uploaded_file = legacy_genai.upload_file(local_audio_path)
                        contents = [uploaded_file, prompt]
                    else:
                        contents = prompt
                    response = model.generate_content(contents)
                    return _parse_unified_json_response(response.text)
                finally:
                    if uploaded_file is not None:
                        try:
                            uploaded_file.delete()
                        except Exception as del_err:
                            print(f"Warning: Failed to delete remote file: {del_err}")
            except Exception as e_legacy:
                print(f"Legacy google-generativeai call failed: {e_legacy}")
                raise e
    finally:
        # Clean up temporary local MP3 download if we created one
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


def run_gemini_extraction(transcript, tickers, api_key):
    """Backward-compatible wrapper returning ticker recommendations via the unified Gemini call."""
    res = analyze_episode_with_gemini(transcript=transcript, tickers=tickers, api_key=api_key)
    return res.get("recommendations", [])


def generate_topic_summary(transcript, api_key):
    """Backward-compatible wrapper returning topic summary via the unified Gemini call."""
    res = analyze_episode_with_gemini(transcript=transcript, tickers=[], api_key=api_key)
    return res.get("topic_summary", "")


def generate_audio_for_episode(date_str, title, summary, recommendations, audio_dir="audio", force=False):
    """Generate a natural neural MP3 audio file for an episode using edge-tts."""
    os.makedirs(audio_dir, exist_ok=True)
    output_file = os.path.join(audio_dir, f"{date_str}.mp3")
    if os.path.exists(output_file) and not force:
        return output_file

    lines = [f"InvestTalk Podcast summary for {date_str}. {title}.", ""]
    lines.append("Topic summary:")
    clean_summary = re.sub(r'[*_#`]', '', summary)
    lines.append(clean_summary)
    lines.append("")

    if recommendations:
        lines.append("Stock discussions and verdicts:")
        for rec in recommendations:
            ticker = rec.get("ticker", "")
            verdict = rec.get("recommendation", "")
            reason = rec.get("reason", "")
            reason_clean = re.sub(r'[*_#`]', '', reason)
            spaced_ticker = ". ".join(list(ticker.upper())) + "." if ticker else ""
            lines.append(f"For ticker {spaced_ticker} Verdict: {verdict}. Reason: {reason_clean}")

    script_text = "\n".join(lines)

    async def _speak():
        import edge_tts
        communicate = edge_tts.Communicate(script_text, "en-US-AriaNeural")
        await communicate.save(output_file)

    try:
        import asyncio
        print(f"Generating Edge-TTS neural audio for {date_str}...")
        asyncio.run(_speak())
        print(f"Successfully saved neural audio to {output_file}")
        return output_file
    except Exception as e:
        print(f"Warning: Failed to generate audio with edge-tts for {date_str}: {e}")
        return None

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
        
        print("Resolving episode source...")
        transcript = None
        vtt_url = episode.get('vtt_url')
        audio_url = episode.get('audio_url')
        if vtt_url:
            print(f"Found WebVTT transcript URL: {vtt_url}")
            try:
                transcript = fetch_transcript(vtt_url)
            except Exception as e:
                print(f"Warning: Failed to fetch WebVTT transcript ({e}).")
                transcript = None

        if transcript:
            print(f"Transcript length: {len(transcript)} characters.")
        elif audio_url:
            print(f"WebVTT transcript not found or failed. Will use single-call Google GenAI audio analysis from: {audio_url}")
        else:
            print(f"ERROR: Neither WebVTT transcript nor audio stream is available for episode '{episode['title']}' ({date_str}).")
            print("Failing job to trigger GitHub Actions alert.")
            sys.exit(1)

        if args.dry_run:
            if not transcript and audio_url:
                print("[DRY RUN MODE] Skipping remote audio download and using dry-run placeholder data.")
            else:
                print("[DRY RUN MODE] Generating placeholder data...")
            placeholder_recs = [{"ticker": t, "recommendation": "Buy (Dry Run Placeholder)", "reason": "Reason (Dry Run Placeholder)"} for t in tickers]
            episodes_db = save_episode_data(
                date_str, 
                episode['title'], 
                "This is a dry-run placeholder summary of the main topic.", 
                placeholder_recs
            )
            continue

        # Live processing: single unified Gemini call for both topic summary and ticker verdicts
        print("Running unified Gemini LLM analysis (single API call)...")
        try:
            analysis = analyze_episode_with_gemini(
                transcript=transcript,
                audio_source=None if transcript else audio_url,
                tickers=tickers,
                api_key=api_key
            )
            topic_summary = analysis.get("topic_summary", "")
            results = analysis.get("recommendations", [])
            if not results:
                print("No ticker recommendations identified by Gemini.")
            else:
                print(f"Successfully extracted {len(results)} ticker recommendation(s) and topic summary in 1 call.")
        except Exception as e:
            print(f"Error during unified Gemini analysis: {e}")
            if not transcript:
                print(f"ERROR: Single-call audio analysis failed for episode '{episode['title']}' ({date_str}).")
                print("Failing job to trigger GitHub Actions alert.")
                sys.exit(1)
            topic_summary = f"Error generating summary: {e}"
            if tickers:
                results = [{"ticker": t, "recommendation": "Error", "reason": f"Failed to extract: {e}"} for t in tickers]
            else:
                results = []

        print("\nTopic Summary:")
        print(topic_summary)
        
        # Save to database
        episodes_db = save_episode_data(date_str, episode['title'], topic_summary, results)
        
    # Post loop updates
    print("\nGenerating Neural Edge-TTS audio files for episodes...")
    for date_str, ep in episodes_db.items():
        generate_audio_for_episode(
            date_str,
            ep.get('title', ''),
            ep.get('summary', ''),
            ep.get('recommendations', []),
            force=args.force
        )

    print("\nRegenerating cumulative summary files...")
    generate_cumulative_markdown(episodes_db)
    generate_cumulative_html(episodes_db)

        
    print("\nExecution completed successfully!")

if __name__ == "__main__":
    main()
