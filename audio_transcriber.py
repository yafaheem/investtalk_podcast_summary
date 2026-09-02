import os
import sys
import argparse
import tempfile
import urllib.request
from typing import Optional

# Optional dotenv loading
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def is_url(source: str) -> bool:
    """Check if the given source string is an HTTP or HTTPS URL."""
    return bool(source and (source.startswith("http://") or source.startswith("https://")))

def download_audio(audio_url: str, temp_dir: Optional[str] = None) -> str:
    """
    Download a remote audio stream to a temporary local MP3 file.
    
    Args:
        audio_url: Remote URL of the audio stream (e.g. from RSS <enclosure>).
        temp_dir: Optional directory to store the temporary file. Defaults to system temp.
        
    Returns:
        Absolute path to the downloaded temporary MP3 file.
    """
    if not is_url(audio_url):
        raise ValueError(f"Invalid audio URL: {audio_url}")
        
    temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", dir=temp_dir, delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    print(f"Downloading audio from {audio_url}...")
    req = urllib.request.Request(audio_url, headers={'User-Agent': 'Mozilla/5.0 (InvestTalk-Summary-Bot)'})
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response, open(temp_path, 'wb') as out_file:
            chunk_size = 1024 * 1024  # 1MB chunks
            total_bytes = 0
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                total_bytes += len(chunk)
        print(f"Downloaded {total_bytes / (1024 * 1024):.2f} MB audio to {temp_path}")
        return temp_path
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise RuntimeError(f"Failed to download audio from {audio_url}: {e}")

def transcribe_audio_file(file_path: str, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash") -> str:
    """
    Transcribe a local audio file using Google GenAI File API and Gemini models.
    
    Args:
        file_path: Absolute or relative path to the local audio file.
        api_key: Optional Gemini API key. If not provided, reads GEMINI_API_KEY env var.
        model_name: Gemini model name for transcription (default: 'gemini-2.5-flash').
        
    Returns:
        Plain-text transcript with speaker turns and financial terms preserved.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
        
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY not found in environment or arguments.")

    prompt = (
        "Generate a complete, high-fidelity transcript of this podcast audio.\n\n"
        "Requirements:\n"
        "1. Clearly attribute speaker turns where possible (e.g. [Justin Klein]: ..., [Luke Guerrero]: ..., [Caller]: ...).\n"
        "2. Accurately transcribe all financial terminology, company names, stock tickers, and conversational questions.\n"
        "3. Output only the plain text transcript without commentary."
    )

    # Primary: Modern google-genai SDK
    try:
        from google import genai
        client = genai.Client(api_key=key)
        
        print(f"Uploading audio file '{file_path}' to Google GenAI File API...")
        uploaded_file = client.files.upload(file=file_path)
        print(f"Uploaded audio to GenAI File API (Name: {uploaded_file.name}). Transcribing with {model_name}...")
        
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt]
            )
            transcript = response.text.strip()
            return transcript
        finally:
            try:
                print(f"Cleaning up GenAI File API remote file: {uploaded_file.name}")
                client.files.delete(name=uploaded_file.name)
            except Exception as del_err:
                print(f"Warning: Failed to delete remote file from GenAI File API: {del_err}")

    except ImportError:
        # Fallback: Legacy google-generativeai SDK
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=key)
            
            print(f"Uploading audio file '{file_path}' via legacy google.generativeai...")
            uploaded_file = legacy_genai.upload_file(file_path)
            print(f"Uploaded audio (Name: {uploaded_file.name}). Transcribing...")
            
            try:
                model = legacy_genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content([uploaded_file, prompt])
                return response.text.strip()
            finally:
                try:
                    uploaded_file.delete()
                except Exception as del_err:
                    print(f"Warning: Failed to delete remote file: {del_err}")
        except Exception as e_legacy:
            raise RuntimeError(f"Legacy google.generativeai transcription failed: {e_legacy}")

def transcribe_audio(source: str, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash", temp_dir: Optional[str] = None) -> str:
    """
    Polymorphic audio transcription entry point.
    
    Accepts either:
    - Remote HTTP/HTTPS URL: downloads to temporary file, transcribes, and removes temp file.
    - Local file path: directly uploads to Google GenAI without downloading or deleting original file.
    
    Args:
        source: Remote URL (e.g. RSS enclosure) or local file path.
        api_key: Optional Gemini API key.
        model_name: Model identifier (default: 'gemini-2.5-flash').
        temp_dir: Directory for temporary downloads when source is a remote URL.
        
    Returns:
        Generated text transcript string.
    """
    if is_url(source):
        temp_audio_path = download_audio(source, temp_dir=temp_dir)
        try:
            return transcribe_audio_file(temp_audio_path, api_key=api_key, model_name=model_name)
        finally:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
    else:
        return transcribe_audio_file(source, api_key=api_key, model_name=model_name)

def main():
    parser = argparse.ArgumentParser(description="InvestTalk Audio Transcriber via Google GenAI File API")
    parser.add_argument("--source", "-s", required=True, help="Audio source: Remote URL (HTTP/HTTPS) or local file path (.mp3)")
    parser.add_argument("--output", "-o", help="Optional output path to save transcript file (e.g. transcript.txt)")
    parser.add_argument("--api-key", help="Gemini API Key (defaults to GEMINI_API_KEY env var)")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model name (default: gemini-2.5-flash)")
    parser.add_argument("--temp-dir", help="Directory for temporary audio downloads")
    args = parser.parse_args()

    print(f"Initiating transcription for source: {args.source}")
    try:
        transcript = transcribe_audio(
            source=args.source,
            api_key=args.api_key,
            model_name=args.model,
            temp_dir=args.temp_dir
        )
        print("\n--- Transcription Completed ---")
        print(f"Transcript Length: {len(transcript)} characters")
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(transcript)
            print(f"Transcript saved successfully to {args.output}")
        else:
            print("\nPreview (first 500 chars):\n")
            print(transcript[:500] + ("..." if len(transcript) > 500 else ""))
            
    except Exception as e:
        print(f"Error during audio transcription: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
