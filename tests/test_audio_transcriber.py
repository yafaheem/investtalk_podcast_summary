import os
import unittest
from unittest.mock import patch, MagicMock
from audio_transcriber import is_url, download_audio, transcribe_audio_file, transcribe_audio

class TestAudioTranscriber(unittest.TestCase):

    def test_is_url(self):
        """Test URL format detection."""
        self.assertTrue(is_url("http://example.com/audio.mp3"))
        self.assertTrue(is_url("https://example.com/stream.mp3"))
        self.assertFalse(is_url("/local/path/audio.mp3"))
        self.assertFalse(is_url("relative/path/audio.mp3"))
        self.assertFalse(is_url(""))

    @patch("urllib.request.urlopen")
    def test_download_audio_success(self, mock_urlopen):
        """Test streaming download of remote audio to temp file."""
        mock_response = MagicMock()
        mock_response.read.side_effect = [b"mock_audio_chunk_1", b"mock_audio_chunk_2", b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        temp_path = download_audio("https://example.com/test.mp3")
        try:
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "rb") as f:
                content = f.read()
            self.assertEqual(content, b"mock_audio_chunk_1mock_audio_chunk_2")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch("urllib.request.urlopen")
    def test_download_audio_failure(self, mock_urlopen):
        """Test download failure cleans up temporary file and raises error."""
        mock_urlopen.side_effect = Exception("Connection timed out")
        with self.assertRaises(RuntimeError):
            download_audio("https://example.com/failing.mp3")

    @patch("google.genai.Client")
    def test_transcribe_audio_file(self, mock_genai_client_class):
        """Test audio file transcription via Google GenAI File API."""
        mock_client = MagicMock()
        mock_genai_client_class.return_value = mock_client

        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/test-file-123"
        mock_client.files.upload.return_value = mock_uploaded_file

        mock_response = MagicMock()
        mock_response.text = "Justin Klein: Welcome to InvestTalk.\nCaller: Should I buy AAPL?"
        mock_client.models.generate_content.return_value = mock_response

        # Create a real dummy file to test path validation
        dummy_file = "test_dummy_audio.mp3"
        with open(dummy_file, "wb") as f:
            f.write(b"fake_mp3_data")

        try:
            transcript = transcribe_audio_file(dummy_file, api_key="test-key")
            self.assertEqual(transcript, "Justin Klein: Welcome to InvestTalk.\nCaller: Should I buy AAPL?")
            
            mock_client.files.upload.assert_called_once_with(file=dummy_file)
            mock_client.models.generate_content.assert_called_once()
            mock_client.files.delete.assert_called_once_with(name="files/test-file-123")
        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)

    @patch("audio_transcriber.download_audio")
    @patch("audio_transcriber.transcribe_audio_file")
    def test_transcribe_audio_with_url(self, mock_transcribe_file, mock_download):
        """Test transcribe_audio polymorphic wrapper with a remote URL."""
        mock_download.return_value = "/tmp/mock_downloaded.mp3"
        mock_transcribe_file.return_value = "Transcribed text from URL"

        # Create a dummy file so os.remove doesn't fail
        with open("/tmp/mock_downloaded.mp3", "wb") as f:
            f.write(b"test")

        result = transcribe_audio("https://example.com/episode.mp3", api_key="test-key")
        self.assertEqual(result, "Transcribed text from URL")
        mock_download.assert_called_once_with("https://example.com/episode.mp3", temp_dir=None)
        mock_transcribe_file.assert_called_once_with("/tmp/mock_downloaded.mp3", api_key="test-key", model_name="gemini-2.5-flash")
        self.assertFalse(os.path.exists("/tmp/mock_downloaded.mp3"))

    @patch("audio_transcriber.transcribe_audio_file")
    def test_transcribe_audio_with_local_file(self, mock_transcribe_file):
        """Test transcribe_audio polymorphic wrapper with a local file."""
        mock_transcribe_file.return_value = "Transcribed text from local file"
        result = transcribe_audio("/local/path/episode.mp3", api_key="test-key")
        self.assertEqual(result, "Transcribed text from local file")
        mock_transcribe_file.assert_called_once_with("/local/path/episode.mp3", api_key="test-key", model_name="gemini-2.5-flash")

if __name__ == "__main__":
    unittest.main()
