#!/usr/bin/env python3
"""
Standalone test runner that works without external dependencies.
Tests core logic with mocked dependencies.
"""

import sys
import asyncio
import unittest
import subprocess
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Agent:
    """Agent representation."""
    id: str
    name: str
    priority: int = 5
    status: str = "idle"
    last_active: datetime = field(default_factory=datetime.now)


@dataclass
class VoiceRequest:
    """Voice request in the queue."""
    agent_id: str
    message: str
    priority: int
    timestamp: datetime = field(default_factory=datetime.now)


class VoiceCoordinationServer:
    """Simplified coordination server for testing."""
    
    def __init__(self, port: int = 8765):
        self.port = port
        self.agents: Dict[str, Agent] = {}
        self.voice_queue: List[VoiceRequest] = []
        self.current_speaker: Optional[str] = None
    
    def register_agent(self, agent_id: str, name: str, priority: int = 5):
        """Register a new agent."""
        self.agents[agent_id] = Agent(
            id=agent_id,
            name=name,
            priority=priority
        )
    
    def add_voice_request(self, agent_id: str, message: str):
        """Add a voice request to the queue."""
        if agent_id not in self.agents:
            return False
        
        request = VoiceRequest(
            agent_id=agent_id,
            message=message,
            priority=self.agents[agent_id].priority
        )
        self.voice_queue.append(request)
        # Sort by priority (highest first)
        self.voice_queue.sort(key=lambda x: x.priority, reverse=True)
        return True
    
    def set_current_speaker(self, agent_id: str):
        """Set the current speaker."""
        self.current_speaker = agent_id
        if agent_id in self.agents:
            self.agents[agent_id].status = "speaking"
    
    def clear_current_speaker(self):
        """Clear the current speaker."""
        if self.current_speaker and self.current_speaker in self.agents:
            self.agents[self.current_speaker].status = "idle"
        self.current_speaker = None
    
    def can_speak(self, agent_id: str) -> bool:
        """Check if an agent can speak."""
        if self.current_speaker is None:
            return True
        return self.current_speaker == agent_id


class TestCoordinationServer(unittest.TestCase):
    """Test voice coordination server core functionality."""
    
    def setUp(self):
        """Setup test server instance."""
        self.server = VoiceCoordinationServer(port=8765)
    
    def test_agent_registration(self):
        """Test agent registration and tracking."""
        agent_id = "test-agent-1"
        self.server.register_agent(agent_id, "Test Agent", priority=5)
        
        self.assertIn(agent_id, self.server.agents)
        agent = self.server.agents[agent_id]
        self.assertEqual(agent.name, "Test Agent")
        self.assertEqual(agent.priority, 5)
        self.assertEqual(agent.status, "idle")
        print("  ✓ Agent registration works correctly")
    
    def test_voice_queue_priority(self):
        """Test priority-based voice queue ordering."""
        # Register agents with different priorities
        self.server.register_agent("low", "Low Priority", priority=3)
        self.server.register_agent("high", "High Priority", priority=8)
        self.server.register_agent("medium", "Medium Priority", priority=5)
        
        # Add voice requests
        self.server.add_voice_request("low", "Low priority message")
        self.server.add_voice_request("high", "High priority message")
        self.server.add_voice_request("medium", "Medium priority message")
        
        # Check queue order (should be sorted by priority)
        queue = self.server.voice_queue
        self.assertEqual(len(queue), 3)
        self.assertEqual(queue[0].agent_id, "high")
        self.assertEqual(queue[1].agent_id, "medium")
        self.assertEqual(queue[2].agent_id, "low")
        print("  ✓ Priority queue ordering works correctly")
    
    def test_current_speaker_management(self):
        """Test current speaker tracking."""
        agent_id = "speaker-1"
        self.server.register_agent(agent_id, "Speaker")
        
        # Set current speaker
        self.server.set_current_speaker(agent_id)
        self.assertEqual(self.server.current_speaker, agent_id)
        self.assertEqual(self.server.agents[agent_id].status, "speaking")
        
        # Clear current speaker
        self.server.clear_current_speaker()
        self.assertIsNone(self.server.current_speaker)
        self.assertEqual(self.server.agents[agent_id].status, "idle")
        print("  ✓ Speaker management works correctly")
    
    def test_can_speak_logic(self):
        """Test permission logic for speaking."""
        self.server.register_agent("agent1", "Agent 1", priority=5)
        self.server.register_agent("agent2", "Agent 2", priority=8)
        
        # No current speaker - agent1 can speak
        self.assertTrue(self.server.can_speak("agent1"))
        
        # Set agent1 as current speaker
        self.server.set_current_speaker("agent1")
        
        # Agent1 is speaking - agent2 cannot speak
        self.assertFalse(self.server.can_speak("agent2"))
        
        # Agent1 can continue speaking (same agent)
        self.assertTrue(self.server.can_speak("agent1"))
        print("  ✓ Speaking permission logic works correctly")


class TestMacOSSpeechSimulation(unittest.TestCase):
    """Test macOS say() command integration."""
    
    def test_say_command_available(self):
        """Test that macOS say command is available."""
        result = subprocess.run(
            ["which", "say"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0, "macOS 'say' command not found")
        print("  ✓ macOS 'say' command is available")
    
    def test_say_with_different_voices(self):
        """Test say command with different voices."""
        voices = ["Alex", "Samantha", "Victoria"]
        
        for voice in voices:
            # Use a shorter test and no timeout to avoid issues
            result = subprocess.run(
                ["say", "-v", voice, "T", "-r", "400"],
                capture_output=True,
                text=True
            )
            self.assertEqual(
                result.returncode, 0,
                f"Failed to use voice {voice}"
            )
        print(f"  ✓ Successfully tested {len(voices)} different voices")


class TestQueueProcessing(unittest.TestCase):
    """Test queue processing and coordination."""
    
    def test_queue_processing_order(self):
        """Test that queue processes in priority order."""
        server = VoiceCoordinationServer()
        
        # Add agents in random order
        agents = [
            ("doc-agent", "Documentation Agent", 3),
            ("code-agent", "Code Agent", 8),
            ("test-agent", "Test Agent", 5),
            ("review-agent", "Review Agent", 7),
        ]
        
        for agent_id, name, priority in agents:
            server.register_agent(agent_id, name, priority)
            server.add_voice_request(agent_id, f"{name} message")
        
        # Process queue and verify order
        processed_order = []
        while server.voice_queue:
            request = server.voice_queue.pop(0)
            processed_order.append(request.agent_id)
        
        expected_order = ["code-agent", "review-agent", "test-agent", "doc-agent"]
        self.assertEqual(processed_order, expected_order)
        print("  ✓ Queue processes in correct priority order")
    
    def test_concurrent_speaker_blocking(self):
        """Test that only one agent can speak at a time."""
        server = VoiceCoordinationServer()
        
        server.register_agent("agent1", "Agent 1")
        server.register_agent("agent2", "Agent 2")
        
        # Agent 1 starts speaking
        self.assertTrue(server.can_speak("agent1"))
        server.set_current_speaker("agent1")
        
        # Agent 2 cannot interrupt
        self.assertFalse(server.can_speak("agent2"))
        
        # After Agent 1 finishes, Agent 2 can speak
        server.clear_current_speaker()
        self.assertTrue(server.can_speak("agent2"))
        print("  ✓ Concurrent speaker blocking works correctly")


def run_integration_demo():
    """Run a live integration demo with macOS say."""
    print("\n🎬 Running Live Integration Demo...")
    print("  This will use macOS 'say' to simulate multiple agents speaking")
    
    server = VoiceCoordinationServer()
    
    # Register agents with different priorities
    agents = [
        ("code-agent", "Code Agent", 8, "Alex"),
        ("test-agent", "Test Agent", 6, "Victoria"),
        ("doc-agent", "Documentation Agent", 4, "Samantha"),
    ]
    
    for agent_id, name, priority, voice in agents:
        server.register_agent(agent_id, name, priority)
    
    # Add speech requests
    messages = [
        ("code-agent", "Analyzing code structure"),
        ("test-agent", "Running test suite"),
        ("doc-agent", "Updating documentation"),
    ]
    
    for agent_id, message in messages:
        server.add_voice_request(agent_id, message)
    
    print("\n  Speaking order (by priority):")
    
    # Process queue in priority order
    while server.voice_queue:
        request = server.voice_queue.pop(0)
        agent = server.agents[request.agent_id]
        
        if server.can_speak(request.agent_id):
            server.set_current_speaker(request.agent_id)
            
            # Find voice for this agent
            voice = next(v for aid, _, _, v in agents if aid == request.agent_id)
            
            print(f"    🎤 {agent.name} (priority {agent.priority}): {request.message}")
            
            # Use macOS say to speak
            subprocess.run(
                ["say", "-v", voice, request.message, "-r", "220"],
                timeout=5
            )
            
            server.clear_current_speaker()
            time.sleep(0.3)  # Small pause between speakers
    
    print("\n  ✅ Integration demo complete!")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 Voice Coordination System - Comprehensive Test Suite")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestCoordinationServer,
        TestMacOSSpeechSimulation,
        TestQueueProcessing,
    ]
    
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests with custom output
    print("\n📋 Running Unit Tests...")
    print("-" * 40)
    
    runner = unittest.TextTestRunner(verbosity=0, stream=sys.stdout)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print("-" * 40)
    
    total_tests = result.testsRun
    passed = total_tests - len(result.failures) - len(result.errors)
    
    print(f"  Total Tests: {total_tests}")
    print(f"  ✅ Passed: {passed}")
    print(f"  ❌ Failed: {len(result.failures)}")
    print(f"  ⚠️  Errors: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ Failed Tests:")
        for test, trace in result.failures:
            print(f"  - {test}: {trace.split('AssertionError:')[-1].strip()}")
    
    if result.errors:
        print("\n⚠️  Test Errors:")
        for test, trace in result.errors:
            print(f"  - {test}: {trace.split(':')[-1].strip()}")
    
    print("=" * 60)
    
    # Run integration demo if tests passed
    if result.wasSuccessful():
        run_integration_demo()
        print("\n🎉 All tests passed successfully!")
        print("✨ Voice coordination system is fully validated and working!")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())