"""Test speed parameter handling in converse tool."""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from voice_mode.tools.converse import converse as converse_tool

# The converse function is wrapped by @mcp.tool(), so we need to access the actual function
converse = converse_tool.fn


class TestSpeedParameter:
    """Test speed parameter type conversion and validation."""
    
    @pytest.mark.asyncio
    async def test_speed_accepts_float(self):
        """Test that speed parameter accepts float values."""
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            with patch('voice_mode.tools.converse.text_to_speech_with_failover', new_callable=AsyncMock) as mock_tts:
                mock_tts.return_value = (True, {'generation': 1.0, 'playback': 2.0}, {})
                
                result = await converse(
                    message="Test",
                    wait_for_response=False,
                    speed=1.5
                )
                
                assert "Message spoken successfully" in result
                # Verify speed was passed correctly
                _, kwargs = mock_tts.call_args
                assert kwargs['speed'] == 1.5
    
    @pytest.mark.asyncio
    async def test_speed_converts_string_to_float(self):
        """Test that string speed values are converted to float."""
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            with patch('voice_mode.tools.converse.text_to_speech_with_failover', new_callable=AsyncMock) as mock_tts:
                mock_tts.return_value = (True, {'generation': 1.0, 'playback': 2.0}, {})
                
                # This is what happens when MCP passes the parameter
                result = await converse(
                    message="Test",
                    wait_for_response=False,
                    speed="1.5"  # String value
                )
                
                assert "Message spoken successfully" in result
                # Verify speed was converted and passed correctly
                _, kwargs = mock_tts.call_args
                assert kwargs['speed'] == 1.5
                assert isinstance(kwargs['speed'], float)
    
    @pytest.mark.asyncio
    async def test_speed_invalid_string_error(self):
        """Test that invalid string speed values return error."""
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            result = await converse(
                message="Test",
                wait_for_response=False,
                speed="invalid"
            )
            
            assert "Error: speed must be a number" in result
    
    @pytest.mark.asyncio
    async def test_speed_out_of_range_error(self):
        """Test that out of range speed values return error."""
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            # Test too low
            result = await converse(
                message="Test",
                wait_for_response=False,
                speed=0.1
            )
            assert "Error: speed must be between 0.25 and 4.0" in result
            
            # Test too high
            result = await converse(
                message="Test",
                wait_for_response=False,
                speed=5.0
            )
            assert "Error: speed must be between 0.25 and 4.0" in result
    
    @pytest.mark.asyncio
    async def test_speed_none_is_valid(self):
        """Test that None speed value is valid (uses default)."""
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            with patch('voice_mode.tools.converse.text_to_speech_with_failover', new_callable=AsyncMock) as mock_tts:
                mock_tts.return_value = (True, {'generation': 1.0, 'playback': 2.0}, {})
                
                result = await converse(
                    message="Test",
                    wait_for_response=False,
                    speed=None
                )
                
                assert "Message spoken successfully" in result
                # Verify speed was passed as None
                _, kwargs = mock_tts.call_args
                assert kwargs['speed'] is None
    
    @pytest.mark.asyncio
    async def test_speed_edge_cases(self):
        """Test speed parameter edge cases."""
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            with patch('voice_mode.tools.converse.text_to_speech_with_failover', new_callable=AsyncMock) as mock_tts:
                mock_tts.return_value = (True, {'generation': 1.0, 'playback': 2.0}, {})
                
                # Test minimum valid speed
                result = await converse(
                    message="Test",
                    wait_for_response=False,
                    speed=0.25
                )
                assert "Message spoken successfully" in result
                
                # Test maximum valid speed
                result = await converse(
                    message="Test",
                    wait_for_response=False,
                    speed=4.0
                )
                assert "Message spoken successfully" in result
                
                # Test integer speed (should work)
                result = await converse(
                    message="Test",
                    wait_for_response=False,
                    speed=2
                )
                assert "Message spoken successfully" in result