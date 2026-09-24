import unittest
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

# Import the functions we want to test
from rss_extractor import (
    fetch_rss_data,
    parse_rss_xml,
    parse_item_date,
    filter_episodes,
    extract_audio_url
)
from extract_tickers import (
    extract_tickers_from_description,
    clean_vtt,
    fetch_transcript_data
)

class TestInvestTalkNotes(unittest.TestCase):

    def test_extract_tickers_from_description(self):
        """Test extraction of tickers and filtering of blacklist words."""
        desc = "Today we discuss Cincinnati Financial (CINF), Reddit (RDDT), and also general topics like AI (AI) and index funds (ETF)."
        tickers = extract_tickers_from_description(desc)
        self.assertEqual(tickers, ["CINF", "RDDT"])

        # Test duplicate handling
        desc_duplicates = "Look at (CINF) and then (CINF) again."
        tickers_duplicates = extract_tickers_from_description(desc_duplicates)
        self.assertEqual(tickers_duplicates, ["CINF"])

        # Test hyphenated format from newer descriptions
        desc_hyphen = "<p><strong>Also in this podcast:</strong> EME - Emcor group Inc., MDT - Medtronic PLC, GLW - Corning Inc., CROX - Crocs Inc., LULU - Lululemon Athletica Inc., BAH - Booz Allen Hamilton Holding Corp; also, a question about XRP</p>"
        tickers_hyphen = extract_tickers_from_description(desc_hyphen)
        self.assertEqual(tickers_hyphen, ["EME", "MDT", "GLW", "CROX", "LULU", "BAH"])

    def test_clean_vtt(self):
        """Test cleaning WebVTT transcript into speaker turns text."""
        raw_vtt = (
            "WEBVTT\n"
            "\n"
            "00:01.087 --> 00:10.292\n"
            "[SPEAKER_03]: This is Invest Talk.\n"
            "\n"
            "NOTE style formatting\n"
            "STYLE\n"
            "\n"
            "00:11.193 --> 00:13.934\n"
            "[SPEAKER_01]: Here's your host.\n"
        )
        cleaned = clean_vtt(raw_vtt)
        expected = "SPEAKER_03: This is Invest Talk.\nSPEAKER_01: Here's your host."
        self.assertEqual(cleaned, expected)

    def test_parse_item_date(self):
        """Test robust date parsing using RFC 822 format."""
        # Double digit day (noon UTC is Friday morning Pacific)
        xml_str_1 = "<item><pubDate>Fri, 17 Jul 2026 12:00:00 +0000</pubDate></item>"
        item_1 = ET.fromstring(xml_str_1)
        self.assertEqual(parse_item_date(item_1), "2026-07-17")

        # Single digit day
        xml_str_2 = "<item><pubDate>Fri, 7 Jul 2026 12:00:00 GMT</pubDate></item>"
        item_2 = ET.fromstring(xml_str_2)
        self.assertEqual(parse_item_date(item_2), "2026-07-07")

        # Missing date
        xml_str_3 = "<item></item>"
        item_3 = ET.fromstring(xml_str_3)
        self.assertIsNone(parse_item_date(item_3))

    def test_extract_audio_url(self):
        """Test extracting audio stream URL from enclosure tag."""
        xml_with_enclosure = '<item><enclosure url="https://example.com/podcast.mp3" length="12345" type="audio/mpeg" /></item>'
        item_1 = ET.fromstring(xml_with_enclosure)
        self.assertEqual(extract_audio_url(item_1), "https://example.com/podcast.mp3")

        xml_without_enclosure = '<item><title>No Enclosure</title></item>'
        item_2 = ET.fromstring(xml_without_enclosure)
        self.assertIsNone(extract_audio_url(item_2))

    def test_filter_episodes_latest(self):
        """Test filtering without parameters defaults to latest episode."""
        xml_str = (
            "<rss><channel>"
            "<item>"
            "  <title>Latest Episode</title>"
            "  <description>Discussing (RDDT)</description>"
            "  <pubDate>Fri, 17 Jul 2026 12:00:00 +0000</pubDate>"
            "  <enclosure url=\"https://example.com/latest.mp3\" />"
            "</item>"
            "<item>"
            "  <title>Older Episode</title>"
            "  <description>Discussing (CINF)</description>"
            "  <pubDate>Thu, 16 Jul 2026 12:00:00 +0000</pubDate>"
            "</item>"
            "</channel></rss>"
        )
        root = ET.fromstring(xml_str)
        episodes = filter_episodes(root)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]['title'], "Latest Episode")
        self.assertEqual(episodes[0]['date_str'], "2026-07-17")
        self.assertEqual(episodes[0]['audio_url'], "https://example.com/latest.mp3")

    def test_filter_episodes_target_date(self):
        """Test filtering by a specific target date."""
        xml_str = (
            "<rss><channel>"
            "<item>"
            "  <title>Latest Episode</title>"
            "  <description>Discussing (RDDT)</description>"
            "  <pubDate>Fri, 17 Jul 2026 12:00:00 +0000</pubDate>"
            "</item>"
            "<item>"
            "  <title>Older Episode</title>"
            "  <description>Discussing (CINF)</description>"
            "  <pubDate>Thu, 16 Jul 2026 12:00:00 +0000</pubDate>"
            "</item>"
            "</channel></rss>"
        )
        root = ET.fromstring(xml_str)
        episodes = filter_episodes(root, target_date="2026-07-16")
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]['title'], "Older Episode")

    @patch("urllib.request.urlopen")
    def test_fetch_rss_data(self, mock_urlopen):
        """Test that RSS data fetch handles response reading successfully."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"<mock_rss></mock_rss>"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        rss_data = fetch_rss_data("http://example.com/feed")
        self.assertEqual(rss_data, b"<mock_rss></mock_rss>")
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_fetch_transcript_data(self, mock_urlopen):
        """Test transcript data fetch returns decoded string."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"WEBVTT\n\n00:00 -> 00:01\nHi"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        vtt_data = fetch_transcript_data("http://example.com/transcript.vtt")
        self.assertEqual(vtt_data, "WEBVTT\n\n00:00 -> 00:01\nHi")
        mock_urlopen.assert_called_once()

    def test_filter_episodes_vtt_none(self):
        """Test that items without a transcript tag result in vtt_url=None."""
        xml_str = (
            "<rss><channel>"
            "<item>"
            "  <title>No Transcript Episode</title>"
            "  <pubDate>Fri, 17 Jul 2026 12:00:00 +0000</pubDate>"
            "</item>"
            "</channel></rss>"
        )
        root = ET.fromstring(xml_str)
        episodes = filter_episodes(root)
        self.assertIsNone(episodes[0]['vtt_url'])

    @patch("extract_tickers.parse_rss_feed")
    @patch("extract_tickers.get_feed_url")
    def test_main_fails_on_missing_vtt_and_audio(self, mock_get_feed_url, mock_parse_rss_feed):
        """Confirm main() raises SystemExit(1) gracefully when both transcript and audio are missing."""
        from extract_tickers import main
        mock_get_feed_url.return_value = "http://example.com/feed"
        mock_parse_rss_feed.return_value = [{
            'title': 'Test Missing All Episode',
            'description': 'Test description',
            'pub_date': 'Fri, 17 Jul 2026 12:00:00 +0000',
            'date_str': '2099-01-01',  # Uncached date
            'vtt_url': None,
            'audio_url': None
        }]

        with patch("sys.argv", ["extract_tickers.py", "--dry-run"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)

    @patch("extract_tickers.generate_cumulative_html")
    @patch("extract_tickers.generate_cumulative_markdown")
    @patch("extract_tickers.generate_audio_for_episode")
    @patch("extract_tickers.save_episode_data")
    @patch("extract_tickers.parse_rss_feed")
    @patch("extract_tickers.get_feed_url")
    def test_main_fallback_to_audio_on_missing_vtt(self, mock_get_feed_url, mock_parse_rss_feed, mock_save, mock_gen_audio, mock_gen_md, mock_gen_html):
        """Confirm main() uses audio fallback when vtt_url is None and audio_url is present."""
        from extract_tickers import main
        mock_get_feed_url.return_value = "http://example.com/feed"
        mock_parse_rss_feed.return_value = [{
            'title': 'Test Audio Fallback Episode',
            'description': 'Discussing (AAPL)',
            'pub_date': 'Fri, 17 Jul 2026 12:00:00 +0000',
            'date_str': '2099-01-02',  # Uncached date
            'vtt_url': None,
            'audio_url': 'https://example.com/podcast.mp3'
        }]
        mock_save.return_value = {}

        with patch("sys.argv", ["extract_tickers.py", "--dry-run"]):
            # Should not raise SystemExit
            main()
            mock_save.assert_called_once()

    @patch("google.genai.Client")
    def test_run_gemini_extraction_with_and_without_tickers(self, mock_client_cls):
        """Test run_gemini_extraction handles both explicit tickers and dynamic transcript extraction."""
        from extract_tickers import run_gemini_extraction
        import json
        
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = json.dumps([
            {"ticker": "NVDA", "exchange": "NASDAQ", "recommendation": "Buy", "reason": "Strong GPU demand"}
        ])
        mock_client.models.generate_content.return_value = mock_response

        # 1. With explicit tickers
        res_with_tickers = run_gemini_extraction("Transcript mentioning NVDA", ["NVDA"], api_key="fake-key")
        self.assertEqual(len(res_with_tickers), 1)
        self.assertEqual(res_with_tickers[0]["ticker"], "NVDA")
        
        # Verify prompt contained explicit tickers
        call_args = mock_client.models.generate_content.call_args[1]
        self.assertIn("NVDA", call_args["contents"])

        # 2. Without tickers (empty list)
        res_no_tickers = run_gemini_extraction("Transcript mentioning NVDA", [], api_key="fake-key")
        self.assertEqual(len(res_no_tickers), 1)
        self.assertEqual(res_no_tickers[0]["ticker"], "NVDA")
        
        # Verify prompt instructed dynamic extraction
        call_args_2 = mock_client.models.generate_content.call_args[1]
        self.assertIn("Identify all individual stock or ETF tickers", call_args_2["contents"])

if __name__ == "__main__":
    unittest.main()


