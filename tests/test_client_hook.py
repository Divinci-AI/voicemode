#!/usr/bin/env python3
"""
Unit Tests for Voice Coordination Client and Hook System

Tests the client-side coordination logic and hook integration.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import uuid
from datetime import datetime

# Import the components under test
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from claude_code_voice_hook import (
    VoiceCoordinationClient,
    extract_voice_params,
    voice_coordination_hook
)

class TestVoiceCoordinationClient:
    """Test VoiceCoordinationClient"""
    
    @pytest.fixture
    def client(self):
        """Create a test client"""
        return VoiceCoordinationClient(
            server_url="ws://localhost:8765",
            agent_name="test-agent"
        )
    
    def test_client_initialization(self, client):
        """Test client initialization"""
        assert client.server_url == "ws://localhost:8765"
        assert client.agent_name == "test-agent"
        assert client.connected is False
        assert client.websocket is None
    
    @pytest.mark.asyncio
    async def test_connection_success(self, client):
        """Test successful connection to server"""
        mock_websocket = AsyncMock()
        
        # Mock successful connection and registration
        mock_websocket.send.return_value = None
        mock_websocket.recv.return_value = json.dumps({
            "type": "registration_confirmed",
            "agent_id": client.agent_id
        })
        
        with patch('websockets.connect', return_value=mock_websocket):
            result = await client.connect()
            
            assert result is True
            assert client.connected is True
            assert client.websocket == mock_websocket
            
            # Verify registration message was sent
            mock_websocket.send.assert_called_once()
            sent_data = json.loads(mock_websocket.send.call_args[0][0])
            assert sent_data["type"] == "register"
            assert sent_data["name"] == "test-agent"
            assert sent_data["type"] == "claude-code"
    
    @pytest.mark.asyncio
    async def test_connection_failure(self, client):
        """Test connection failure"""
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            result = await client.connect()
            
            assert result is False
            assert client.connected is False
    
    @pytest.mark.asyncio
    async def test_request_speak_success(self, client):
        """Test successful speak request"""
        client.connected = True
        
        mock_response = {
            "request_id": "req-123",
            "queued_at": datetime.now().isoformat(),
            "queue_position": 1,
            "estimated_wait": 5.0
        }
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = mock_response
            
            result = await client.request_speak("Test message", 10.0, 5)
            
            assert result == mock_response
            mock_post.assert_called_once()
            
            # Verify request data
            call_args = mock_post.call_args
            assert "speak" in call_args[0][0]  # URL contains "speak"
            request_data = call_args[1]["json"]
            assert request_data["message"] == "Test message"
            assert request_data["estimated_duration"] == 10.0
            assert request_data["priority"] == 5
    
    @pytest.mark.asyncio
    async def test_request_speak_fallback(self, client):
        """Test speak request fallback when not connected"""
        client.connected = False
        
        result = await client.request_speak("Test message")
        
        assert result["granted"] is True
        assert result["fallback"] is True
    
    @pytest.mark.asyncio
    async def test_wait_for_permission_granted(self, client):
        """Test waiting for permission - granted"""
        client.connected = True
        mock_websocket = AsyncMock()
        client.websocket = mock_websocket
        
        # Mock receiving permission
        mock_websocket.recv.return_value = json.dumps({
            "type": "speak_granted",
            "request_id": "req-123"
        })
        
        result = await client.wait_for_permission(timeout=1.0)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_wait_for_permission_denied(self, client):
        """Test waiting for permission - denied"""
        client.connected = True
        mock_websocket = AsyncMock()
        client.websocket = mock_websocket
        
        # Mock receiving denial
        mock_websocket.recv.return_value = json.dumps({
            "type": "speak_denied",
            "reason": "Higher priority request"
        })
        
        result = await client.wait_for_permission(timeout=1.0)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_wait_for_permission_timeout(self, client):
        """Test waiting for permission - timeout"""
        client.connected = True
        mock_websocket = AsyncMock()
        client.websocket = mock_websocket
        
        # Mock timeout
        mock_websocket.recv.side_effect = asyncio.TimeoutError()
        
        result = await client.wait_for_permission(timeout=0.1)
        assert result is True  # Fallback to allow
    
    @pytest.mark.asyncio
    async def test_notify_speech_complete(self, client):
        """Test notifying speech completion"""
        client.connected = True
        mock_websocket = AsyncMock()
        client.websocket = mock_websocket
        
        await client.notify_speech_complete()
        
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data["type"] == "speech_complete"
        assert "timestamp" in sent_data
    
    @pytest.mark.asyncio
    async def test_update_status(self, client):
        """Test updating agent status"""
        client.connected = True
        mock_websocket = AsyncMock()
        client.websocket = mock_websocket
        
        await client.update_status("speaking")
        
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data["type"] == "status_update"
        assert sent_data["status"] == "speaking"

class TestVoiceParameterExtraction:
    """Test voice parameter extraction from tool calls"""
    
    def test_extract_basic_params(self):
        """Test extracting basic parameters"""
        tool_call = 'converse(message="Hello world", listen_duration=15.0)'
        
        params = extract_voice_params(tool_call)
        
        assert params["message"] == "Hello world"
        assert params["estimated_duration"] == 5.0  # 15/3
        assert params["priority"] == 5
    
    def test_extract_no_listen_duration(self):
        """Test extraction without listen_duration"""
        tool_call = 'converse(message="Quick message")'
        
        params = extract_voice_params(tool_call)
        
        assert params["message"] == "Quick message"
        assert params["estimated_duration"] == 10.0  # Default
    
    def test_extract_complex_message(self):
        """Test extraction with complex message"""
        tool_call = 'converse(message="This is a longer message with punctuation!", listen_duration=30.0, wait_for_response=True)'
        
        params = extract_voice_params(tool_call)
        
        assert params["message"] == "This is a longer message with punctuation!"
        assert params["estimated_duration"] == 10.0  # 30/3
    
    def test_extract_malformed_call(self):
        """Test extraction from malformed tool call"""
        tool_call = 'some_other_function(param="value")'
        
        params = extract_voice_params(tool_call)
        
        # Should return defaults
        assert params["message"] == ""
        assert params["estimated_duration"] == 10.0
        assert params["priority"] == 5
    
    def test_extract_edge_cases(self):
        """Test extraction edge cases"""
        # Empty message
        tool_call = 'converse(message="", listen_duration=5.0)'
        params = extract_voice_params(tool_call)
        assert params["message"] == ""
        assert params["estimated_duration"] == 5.0  # Minimum
        
        # Very long duration
        tool_call = 'converse(message="Test", listen_duration=120.0)'
        params = extract_voice_params(tool_call)
        assert params["estimated_duration"] == 40.0  # 120/3

class TestVoiceCoordinationHook:
    """Test the voice coordination hook system"""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock coordination client"""
        client = Mock()
        client.update_status = AsyncMock()
        client.request_speak = AsyncMock()
        client.wait_for_permission = AsyncMock()
        client.notify_speech_complete = AsyncMock()
        return client
    
    @pytest.mark.asyncio
    async def test_hook_ignores_non_voice_tools(self):
        """Test hook ignores non-voice tool calls"""
        data = {
            "tool_name": "some_other_tool",
            "tool_call": "some_other_tool(param=value)",
            "result": None
        }
        
        result = await voice_coordination_hook("tool_call", data)
        
        # Should pass through unchanged
        assert result == data
    
    @pytest.mark.asyncio
    async def test_hook_processes_voice_tools(self, mock_client):
        """Test hook processes voice tool calls"""
        data = {
            "tool_name": "mcp__voice-mode__converse",
            "tool_call": 'converse(message="Test message", listen_duration=15.0)',
            "result": None
        }
        
        # Mock successful permission grant
        mock_client.request_speak.return_value = {"granted": True, "fallback": True}
        
        with patch('claude_code_voice_hook.get_coordination_client', return_value=mock_client):
            result = await voice_coordination_hook("tool_call", data)
            
            # Verify client interactions
            mock_client.update_status.assert_any_call("requesting_speech")
            mock_client.request_speak.assert_called_once()
            mock_client.update_status.assert_any_call("speaking")
            
            # Should not skip execution
            assert "skip_execution" not in result
    
    @pytest.mark.asyncio
    async def test_hook_queues_when_denied(self, mock_client):
        """Test hook behavior when speech is denied/queued"""
        data = {
            "tool_name": "mcp__voice-mode__converse",
            "tool_call": 'converse(message="Test message")',
            "result": None
        }
        
        # Mock denied request
        mock_client.request_speak.return_value = {
            "granted": False,
            "queue_position": 2,
            "estimated_wait": 15.0
        }
        
        with patch('claude_code_voice_hook.get_coordination_client', return_value=mock_client):
            result = await voice_coordination_hook("tool_call", data)
            
            # Should skip execution and provide queue info
            assert result["skip_execution"] is True
            assert "queued" in result["result"].lower()
            assert "15.0" in result["result"]
    
    @pytest.mark.asyncio
    async def test_hook_handles_permission_timeout(self, mock_client):
        """Test hook handles permission timeout"""
        data = {
            "tool_name": "mcp__voice-mode__converse",
            "tool_call": 'converse(message="Test message")',
            "result": None
        }
        
        # Mock granted but needs to wait
        mock_client.request_speak.return_value = {"granted": True, "fallback": False}
        mock_client.wait_for_permission.return_value = False  # Timeout
        
        with patch('claude_code_voice_hook.get_coordination_client', return_value=mock_client):
            result = await voice_coordination_hook("tool_call", data)
            
            # Should skip execution due to timeout
            assert result["skip_execution"] is True
            assert "denied" in result["result"].lower()
    
    @pytest.mark.asyncio
    async def test_hook_fallback_on_error(self):
        """Test hook fallback when coordination fails"""
        data = {
            "tool_name": "mcp__voice-mode__converse",
            "tool_call": 'converse(message="Test message")',
            "result": None
        }
        
        # Mock client error
        with patch('claude_code_voice_hook.get_coordination_client', side_effect=Exception("Connection failed")):
            result = await voice_coordination_hook("tool_call", data)
            
            # Should fallback and allow execution
            assert result == data

class TestIntegrationScenarios:
    """Test integration scenarios between client and server"""
    
    @pytest.mark.asyncio
    async def test_complete_coordination_flow(self):
        """Test a complete coordination flow from client perspective"""
        client = VoiceCoordinationClient(agent_name="integration-test")
        
        # Mock successful flow
        mock_websocket = AsyncMock()
        
        # Mock connection sequence
        connection_responses = [
            json.dumps({"type": "registration_confirmed", "agent_id": client.agent_id}),
            json.dumps({"type": "speak_granted", "request_id": "req-123"})
        ]
        mock_websocket.recv.side_effect = connection_responses
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = {"granted": True, "request_id": "req-123"}
        
        with patch('websockets.connect', return_value=mock_websocket), \
             patch('requests.post', return_value=mock_http_response):
            
            # Connect
            connected = await client.connect()
            assert connected is True
            
            # Request speak
            result = await client.request_speak("Integration test message", 5.0)
            assert result["granted"] is True
            
            # Wait for permission (already granted)
            permission = await client.wait_for_permission()
            assert permission is True
            
            # Notify completion
            await client.notify_speech_complete()
            
            # Verify all interactions occurred
            assert mock_websocket.send.call_count >= 2  # Register + speech complete

if __name__ == "__main__":
    pytest.main([__file__, "-v"])