#!/usr/bin/env python3
"""
Unit Tests for Voice Coordination Server

Tests the core coordination logic, queue management, and priority handling.
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch
import uuid

# Import the components under test
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from voice_coordination_server import (
    VoiceCoordinationServer, 
    Agent, 
    VoiceRequest
)

class TestAgent:
    """Test Agent dataclass"""
    
    def test_agent_creation(self):
        """Test creating an agent"""
        agent = Agent(
            id="test-123",
            name="Test Agent",
            type="claude-code",
            status="idle",
            connected_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            priority=5
        )
        
        assert agent.id == "test-123"
        assert agent.name == "Test Agent"
        assert agent.type == "claude-code"
        assert agent.status == "idle"
        assert agent.priority == 5

class TestVoiceRequest:
    """Test VoiceRequest dataclass"""
    
    def test_voice_request_creation(self):
        """Test creating a voice request"""
        request = VoiceRequest(
            id="req-123",
            agent_id="agent-123",
            message="Test message",
            priority=5,
            request_time=datetime.now(timezone.utc),
            estimated_duration=10.0
        )
        
        assert request.id == "req-123"
        assert request.agent_id == "agent-123"
        assert request.message == "Test message"
        assert request.priority == 5
        assert request.estimated_duration == 10.0

class TestVoiceCoordinationServer:
    """Test VoiceCoordinationServer core logic"""
    
    @pytest.fixture
    def server(self):
        """Create a test server instance"""
        return VoiceCoordinationServer(port=8766)  # Different port for testing
    
    @pytest.fixture
    def sample_agent(self):
        """Create a sample agent"""
        return Agent(
            id="test-agent-1",
            name="Test Agent 1",
            type="claude-code",
            status="idle",
            connected_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            priority=5
        )
    
    @pytest.fixture
    def sample_voice_request(self):
        """Create a sample voice request"""
        return VoiceRequest(
            id=str(uuid.uuid4()),
            agent_id="test-agent-1",
            message="Test message",
            priority=5,
            request_time=datetime.now(timezone.utc),
            estimated_duration=8.0
        )
    
    def test_server_initialization(self, server):
        """Test server initialization"""
        assert server.port == 8766
        assert server.agents == {}
        assert server.voice_queue == []
        assert server.current_speaker is None
        assert server.speaking_start_time is None
    
    def test_coordination_status(self, server, sample_agent):
        """Test getting coordination status"""
        # Add sample agent
        server.agents[sample_agent.id] = sample_agent
        
        status = server.get_coordination_status()
        
        assert status["total_agents"] == 1
        assert status["current_speaker"] is None
        assert status["queue_length"] == 0
        assert "server_time" in status
        assert "agents_by_status" in status
    
    @pytest.mark.asyncio
    async def test_queue_voice_request(self, server, sample_voice_request):
        """Test queuing voice requests"""
        # Add agent to server
        agent = Agent(
            id=sample_voice_request.agent_id,
            name="Test Agent",
            type="test",
            status="idle",
            connected_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc)
        )
        server.agents[agent.id] = agent
        
        # Mock websocket
        mock_websocket = AsyncMock()
        server.websockets[agent.id] = mock_websocket
        
        # Queue the request
        result = await server.queue_voice_request(sample_voice_request)
        
        # Verify request was queued
        assert "request_id" in result
        assert "queued_at" in result
        assert result["queue_position"] >= 0
        
        # Verify agent was granted permission (first in queue)
        assert server.current_speaker == sample_voice_request.agent_id
        assert server.agents[agent.id].status == "speaking"
        
        # Verify websocket message was sent
        mock_websocket.send_json.assert_called()
    
    @pytest.mark.asyncio
    async def test_priority_queue_ordering(self, server):
        """Test that voice requests are queued by priority"""
        # Create agents
        agent1 = Agent("agent1", "Agent 1", "test", "idle", 
                      datetime.now(timezone.utc), datetime.now(timezone.utc))
        agent2 = Agent("agent2", "Agent 2", "test", "idle",
                      datetime.now(timezone.utc), datetime.now(timezone.utc))
        
        server.agents["agent1"] = agent1
        server.agents["agent2"] = agent2
        
        # Mock websockets
        server.websockets["agent1"] = AsyncMock()
        server.websockets["agent2"] = AsyncMock()
        
        # Create requests with different priorities
        low_priority_request = VoiceRequest(
            id="req1", agent_id="agent1", message="Low priority", 
            priority=1, request_time=datetime.now(timezone.utc)
        )
        
        high_priority_request = VoiceRequest(
            id="req2", agent_id="agent2", message="High priority",
            priority=10, request_time=datetime.now(timezone.utc)
        )
        
        # Queue low priority first, then high priority
        await server.queue_voice_request(low_priority_request)
        
        # First request should be granted immediately
        assert server.current_speaker == "agent1"
        
        # Simulate speech completion
        await server.handle_speech_complete("agent1")
        
        # Queue high priority request
        await server.queue_voice_request(high_priority_request)
        
        # High priority should be granted
        assert server.current_speaker == "agent2"
    
    @pytest.mark.asyncio
    async def test_speech_timeout_handling(self, server):
        """Test speech timeout handling"""
        # Create agent
        agent = Agent("agent1", "Agent 1", "test", "speaking",
                     datetime.now(timezone.utc), datetime.now(timezone.utc))
        server.agents["agent1"] = agent
        server.current_speaker = "agent1"
        
        # Mock websocket
        server.websockets["agent1"] = AsyncMock()
        
        # Test timeout
        await server.speech_timeout("req1", "agent1", 0.1)  # Very short timeout
        
        # Should have cleared current speaker
        assert server.current_speaker is None
        assert server.agents["agent1"].status == "idle"
    
    def test_estimate_wait_time(self, server):
        """Test wait time estimation"""
        # Add some requests to queue
        requests = [
            VoiceRequest("req1", "agent1", "msg1", 5, datetime.now(timezone.utc), 10.0),
            VoiceRequest("req2", "agent2", "msg2", 5, datetime.now(timezone.utc), 15.0),
            VoiceRequest("req3", "agent3", "msg3", 5, datetime.now(timezone.utc), 8.0)
        ]
        
        server.voice_queue = requests
        
        # Test wait time for second request
        wait_time = server.estimate_wait_time("req2")
        
        # Should include first request's duration plus current speaker estimate
        assert wait_time >= 10.0  # At least first request duration
    
    @pytest.mark.asyncio
    async def test_agent_disconnection_cleanup(self, server):
        """Test proper cleanup when agent disconnects"""
        # Setup agent with queued request
        agent = Agent("agent1", "Agent 1", "test", "idle",
                     datetime.now(timezone.utc), datetime.now(timezone.utc))
        server.agents["agent1"] = agent
        server.websockets["agent1"] = AsyncMock()
        
        # Add request to queue
        request = VoiceRequest("req1", "agent1", "msg", 5, 
                              datetime.now(timezone.utc), 10.0)
        server.voice_queue = [request]
        
        # Disconnect agent
        await server.disconnect_agent("agent1")
        
        # Verify cleanup
        assert "agent1" not in server.agents
        assert "agent1" not in server.websockets
        assert len(server.voice_queue) == 0  # Request should be removed

class TestIntegrationScenarios:
    """Test complex integration scenarios"""
    
    @pytest.fixture
    def server(self):
        """Create a test server instance"""
        return VoiceCoordinationServer(port=8767)
    
    @pytest.mark.asyncio
    async def test_multiple_agents_conversation_flow(self, server):
        """Test a complete conversation flow with multiple agents"""
        # Setup multiple agents
        agents = {}
        for i in range(3):
            agent_id = f"agent{i+1}"
            agent = Agent(
                id=agent_id,
                name=f"Agent {i+1}",
                type="test",
                status="idle",
                connected_at=datetime.now(timezone.utc),
                last_heartbeat=datetime.now(timezone.utc),
                priority=5
            )
            agents[agent_id] = agent
            server.agents[agent_id] = agent
            server.websockets[agent_id] = AsyncMock()
        
        # Simulate conversation flow
        conversation_order = []
        
        # Agent 1 speaks first
        request1 = VoiceRequest("req1", "agent1", "Hello everyone", 5,
                               datetime.now(timezone.utc), 5.0)
        result1 = await server.queue_voice_request(request1)
        conversation_order.append(("agent1", result1))
        
        # Agent 2 and 3 request to speak while agent 1 is speaking
        request2 = VoiceRequest("req2", "agent2", "Hi there", 5,
                               datetime.now(timezone.utc), 3.0)
        result2 = await server.queue_voice_request(request2)
        conversation_order.append(("agent2", result2))
        
        request3 = VoiceRequest("req3", "agent3", "Good morning", 7,  # Higher priority
                               datetime.now(timezone.utc), 4.0)
        result3 = await server.queue_voice_request(request3)
        conversation_order.append(("agent3", result3))
        
        # Agent 1 finishes speaking
        await server.handle_speech_complete("agent1")
        
        # Agent 3 should speak next (higher priority)
        assert server.current_speaker == "agent3"
        
        # Agent 3 finishes
        await server.handle_speech_complete("agent3")
        
        # Agent 2 should speak last
        assert server.current_speaker == "agent2"
        
        # Verify conversation flow
        assert len(conversation_order) == 3
        assert conversation_order[0][1]["granted"] is True  # First speaker granted immediately
        assert conversation_order[1][1].get("queue_position", 0) > 0  # Others queued
        assert conversation_order[2][1].get("queue_position", 0) > 0
    
    @pytest.mark.asyncio
    async def test_mixed_priority_coordination(self, server):
        """Test coordination with mixed agent types and priorities"""
        # Setup different agent types with different priorities
        agent_configs = [
            ("claude-code", "Claude Code", 5),
            ("autoagent-codex", "AutoAgent Codex", 7),
            ("autoagent-websurfer", "AutoAgent WebSurfer", 6),
            ("autoagent-executor", "AutoAgent Executor", 5)
        ]
        
        for i, (agent_type, name, priority) in enumerate(agent_configs):
            agent_id = f"{agent_type}-{i+1}"
            agent = Agent(
                id=agent_id,
                name=name,
                type=agent_type,
                status="idle",
                connected_at=datetime.now(timezone.utc),
                last_heartbeat=datetime.now(timezone.utc),
                priority=priority
            )
            server.agents[agent_id] = agent
            server.websockets[agent_id] = AsyncMock()
        
        # All agents request to speak simultaneously
        requests = []
        for i, (agent_type, name, priority) in enumerate(agent_configs):
            agent_id = f"{agent_type}-{i+1}"
            request = VoiceRequest(
                id=f"req-{i+1}",
                agent_id=agent_id,
                message=f"Message from {name}",
                priority=priority,
                request_time=datetime.now(timezone.utc),
                estimated_duration=5.0
            )
            result = await server.queue_voice_request(request)
            requests.append((agent_id, result))
        
        # AutoAgent Codex should speak first (highest priority = 7)
        expected_order = [
            "autoagent-codex-2",    # Priority 7
            "autoagent-websurfer-3", # Priority 6  
            "claude-code-1",        # Priority 5
            "autoagent-executor-4"  # Priority 5
        ]
        
        # First agent should be speaking
        assert server.current_speaker == expected_order[0]
        
        # Process the queue by completing each speech
        actual_order = [server.current_speaker]
        for _ in range(len(expected_order) - 1):
            current = server.current_speaker
            await server.handle_speech_complete(current)
            if server.current_speaker:
                actual_order.append(server.current_speaker)
        
        # Verify the speaking order matches priority
        assert actual_order[0] == expected_order[0]  # Highest priority first

if __name__ == "__main__":
    pytest.main([__file__, "-v"])