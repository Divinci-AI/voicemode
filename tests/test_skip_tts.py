"""Tests for skip_tts parameter in converse function"""

import os
import pytest
import pytest_asyncio
from unittest.mock import Mock, patch
from mcp.client.session import ClientSession
from voice_mode.server import FastMCP


@pytest.fixture
def original_skip_tts():
    """Save and restore original VOICEMODE_SKIP_TTS value"""
    original = os.environ.get("VOICEMODE_SKIP_TTS")
    yield
    if original is None:
        os.environ.pop("VOICEMODE_SKIP_TTS", None)
    else:
        os.environ["VOICEMODE_SKIP_TTS"] = original


@pytest_asyncio.fixture
async def voice_mode_server():
    """Create a voice mode server for testing"""
    async with FastMCP().run_stdio_async() as streams:
        yield streams


class TestSkipTTS:
    """Test skip_tts parameter functionality"""
    
    @pytest.mark.asyncio
    async def test_skip_tts_true_overrides_env(self, voice_mode_server, original_skip_tts):
        """Test that skip_tts=True skips TTS regardless of environment variable"""
        # Set environment variable to false
        os.environ["VOICEMODE_SKIP_TTS"] = "false"
        
        with patch("voice_mode.tools.converse.text_to_speech_with_failover") as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 1.0, "generation": 1.0, "playback": 2.0}, {"provider": "openai"})
            
            async with ClientSession(voice_mode_server) as client:
                result = await client.call_tool(
                    "converse",
                    {
                        "message": "Test message",
                        "skip_tts": True,
                        "wait_for_response": False
                    }
                )
                # Should not call TTS when skip_tts=True
                mock_tts.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_skip_tts_false_overrides_env(self, voice_mode_server, original_skip_tts):
        """Test that skip_tts=False uses TTS regardless of environment variable"""
        # Set environment variable to true
        os.environ["VOICEMODE_SKIP_TTS"] = "true"
        
        with patch("voice_mode.tools.converse.text_to_speech_with_failover") as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 1.0, "generation": 1.0, "playback": 2.0}, {"provider": "openai"})
            
            async with ClientSession(voice_mode_server) as client:
                result = await client.call_tool(
                    "converse",
                    {
                        "message": "Test message",
                        "skip_tts": False,
                        "wait_for_response": False
                    }
                )
                # Should call TTS when skip_tts=False
                mock_tts.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_skip_tts_none_follows_env_true(self, voice_mode_server, original_skip_tts):
        """Test that skip_tts=None follows environment variable when true"""
        # Set environment variable to true
        os.environ["VOICEMODE_SKIP_TTS"] = "true"
        
        with patch("voice_mode.tools.converse.text_to_speech_with_failover") as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 1.0, "generation": 1.0, "playback": 2.0}, {"provider": "openai"})
            
            async with ClientSession(voice_mode_server) as client:
                result = await client.call_tool(
                    "converse",
                    {
                        "message": "Test message",
                        "wait_for_response": False
                        # skip_tts not specified, should use environment variable
                    }
                )
                # Should not call TTS when env var is true
                mock_tts.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_skip_tts_none_follows_env_false(self, voice_mode_server, original_skip_tts):
        """Test that skip_tts=None follows environment variable when false"""
        # Set environment variable to false
        os.environ["VOICEMODE_SKIP_TTS"] = "false"
        
        with patch("voice_mode.tools.converse.text_to_speech_with_failover") as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 1.0, "generation": 1.0, "playback": 2.0}, {"provider": "openai"})
            
            async with ClientSession(voice_mode_server) as client:
                result = await client.call_tool(
                    "converse",
                    {
                        "message": "Test message",
                        "wait_for_response": False
                        # skip_tts not specified, should use environment variable
                    }
                )
                # Should call TTS when env var is false
                mock_tts.assert_called_once()