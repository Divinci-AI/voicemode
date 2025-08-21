#!/usr/bin/env python3
"""
End-to-End Tests for Voice Coordination System

Tests the complete system using actual voice coordination server,
real client connections, and macOS say() for audio simulation.
"""

import pytest
import asyncio
import subprocess
import time
import json
import platform
import signal
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import logging

# Import test components
import sys
sys.path.append(str(Path(__file__).parent.parent))

from voice_coordination_server import VoiceCoordinationServer
from claude_code_voice_hook import VoiceCoordinationClient
from autoagent_voice_integration import AutoAgentVoiceCoordinator

logger = logging.getLogger(__name__)

class MacOSSpeechSimulator:
    """Simulate speech using macOS say() command"""
    
    def __init__(self):
        self.is_macos = platform.system() == "Darwin"
        self.active_processes = []
    
    async def speak(self, text: str, voice: str = "Alex", rate: int = 200) -> subprocess.Popen:
        """Speak text using macOS say command"""
        if not self.is_macos:
            # Simulate on non-macOS systems
            logger.info(f"[SIMULATED SPEECH] {voice}: {text}")
            await asyncio.sleep(len(text) * 0.05)  # Simulate speech duration
            return None
        
        try:
            # Use macOS say command
            process = subprocess.Popen([
                "say", 
                "-v", voice,
                "-r", str(rate),
                text
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.active_processes.append(process)
            logger.info(f"[macOS SPEECH] {voice}: {text}")
            return process
            
        except FileNotFoundError:
            # say command not available
            logger.warning("macOS say command not available, simulating...")
            await asyncio.sleep(len(text) * 0.05)
            return None
    
    async def wait_for_speech(self, process: subprocess.Popen, timeout: float = 30.0):
        """Wait for speech to complete"""
        if not process:
            return True
        
        try:
            # Wait for say process to complete
            await asyncio.wait_for(
                asyncio.to_thread(process.wait), 
                timeout=timeout
            )
            
            if process in self.active_processes:
                self.active_processes.remove(process)
            
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Speech process timed out after {timeout}s")
            process.terminate()
            return False
    
    def stop_all_speech(self):
        """Stop all active speech processes"""
        for process in self.active_processes:
            if process.poll() is None:
                process.terminate()
        self.active_processes.clear()

class E2ETestServer:
    """Manage test server lifecycle"""
    
    def __init__(self, port: int = 8768):
        self.port = port
        self.server_process = None
        self.server_task = None
    
    async def start(self) -> bool:
        """Start the coordination server"""
        try:
            # Start server in subprocess for isolation
            self.server_process = subprocess.Popen([
                sys.executable, "-c", f"""
import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from voice_coordination_server import VoiceCoordinationServer

async def main():
    server = VoiceCoordinationServer(port={self.port})
    await server.start_server()

if __name__ == "__main__":
    asyncio.run(main())
"""
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for server to start
            await asyncio.sleep(3)
            
            if self.server_process.poll() is None:
                logger.info(f"E2E test server started on port {self.port}")
                return True
            else:
                logger.error("E2E test server failed to start")
                return False
                
        except Exception as e:
            logger.error(f"Error starting E2E test server: {e}")
            return False
    
    def stop(self):
        """Stop the coordination server"""
        if self.server_process:
            logger.info("Stopping E2E test server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()

@pytest.fixture(scope="session")
def e2e_server():
    """Session-scoped test server"""
    server = E2ETestServer()
    
    async def start_server():
        success = await server.start()
        if not success:
            pytest.skip("Could not start E2E test server")
    
    # Start server
    asyncio.run(start_server())
    
    yield server
    
    # Cleanup
    server.stop()

@pytest.fixture
def speech_simulator():
    """Speech simulator fixture"""
    simulator = MacOSSpeechSimulator()
    yield simulator
    simulator.stop_all_speech()

@pytest.mark.e2e
class TestE2EVoiceCoordination:
    """End-to-end voice coordination tests"""
    
    @pytest.mark.asyncio
    async def test_single_agent_speech_flow(self, e2e_server, speech_simulator):
        """Test single agent complete speech flow"""
        # Create client
        client = VoiceCoordinationClient(
            server_url=f"ws://localhost:{e2e_server.port}",
            agent_name="e2e-test-agent"
        )
        
        # Connect to server
        connected = await client.connect()
        assert connected, "Failed to connect to coordination server"
        
        try:
            # Request to speak
            message = "Hello, this is an end-to-end test of voice coordination."
            result = await client.request_speak(message, estimated_duration=5.0, priority=5)
            
            assert result.get("granted") or result.get("queue_position") >= 0
            
            if not result.get("fallback"):
                # Wait for permission if queued
                permission = await client.wait_for_permission(timeout=10.0)
                assert permission, "Permission denied or timed out"
            
            # Simulate actual speech
            speech_process = await speech_simulator.speak(message, voice="Alex")
            
            # Update status to speaking
            await client.update_status("speaking")
            
            # Wait for speech to complete
            if speech_process:
                speech_completed = await speech_simulator.wait_for_speech(speech_process, timeout=10.0)
                assert speech_completed, "Speech simulation failed"
            
            # Notify completion
            await client.notify_speech_complete()
            await client.update_status("idle")
            
        finally:
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_multi_agent_coordination(self, e2e_server, speech_simulator):
        """Test coordination between multiple agents"""
        # Create multiple clients
        clients = []
        agent_configs = [
            ("Claude-Agent-1", "Alex", 5),
            ("AutoAgent-Codex", "Victoria", 7),  # Higher priority
            ("Claude-Agent-2", "Samantha", 5)
        ]
        
        for name, voice, priority in agent_configs:
            client = VoiceCoordinationClient(
                server_url=f"ws://localhost:{e2e_server.port}",
                agent_name=name
            )
            client.test_voice = voice
            client.test_priority = priority
            clients.append(client)
        
        # Connect all clients
        for client in clients:
            connected = await client.connect()
            assert connected, f"Failed to connect {client.agent_name}"
        
        try:
            # All agents request to speak simultaneously
            messages = [
                "I am Claude Agent 1, reporting my status.",
                "AutoAgent Codex here with code analysis results.",
                "Claude Agent 2 with additional information."
            ]
            
            # Submit all requests concurrently
            tasks = []
            for i, client in enumerate(clients):
                task = asyncio.create_task(
                    client.request_speak(
                        messages[i], 
                        estimated_duration=4.0, 
                        priority=client.test_priority
                    )
                )
                tasks.append((client, task, messages[i]))
            
            # Wait for all requests to be processed
            results = []
            for client, task, message in tasks:
                result = await task
                results.append((client, result, message))
            
            # Process the speech queue
            spoken_order = []
            
            # Process each agent that got permission
            for client, result, message in results:
                if result.get("granted"):
                    if not result.get("fallback"):
                        # Wait for permission
                        permission = await client.wait_for_permission(timeout=15.0)
                        if not permission:
                            continue
                    
                    # Speak
                    await client.update_status("speaking")
                    speech_process = await speech_simulator.speak(
                        message, 
                        voice=client.test_voice
                    )
                    
                    spoken_order.append(client.agent_name)
                    logger.info(f"Speaking order: {spoken_order}")
                    
                    # Wait for speech and notify completion
                    if speech_process:
                        await speech_simulator.wait_for_speech(speech_process, timeout=8.0)
                    
                    await client.notify_speech_complete()
                    await client.update_status("idle")
                    
                    # Brief pause between speakers
                    await asyncio.sleep(0.5)
            
            # Verify coordination worked
            assert len(spoken_order) > 0, "No agents spoke successfully"
            
            # AutoAgent Codex should have higher priority
            if len(spoken_order) > 1:
                codex_position = spoken_order.index("AutoAgent-Codex") if "AutoAgent-Codex" in spoken_order else -1
                if codex_position >= 0:
                    # Codex should speak early (high priority)
                    assert codex_position <= 1, f"High priority agent spoke too late: position {codex_position}"
        
        finally:
            # Cleanup
            for client in clients:
                await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_priority_ordering_with_speech(self, e2e_server, speech_simulator):
        """Test that agents speak in correct priority order"""
        # Create agents with specific priorities
        agent_specs = [
            ("Low-Priority", "Fred", 1, "I have low priority information."),
            ("High-Priority", "Victoria", 10, "This is urgent high priority data!"),
            ("Medium-Priority", "Alex", 5, "Medium priority status update.")
        ]
        
        clients = []
        for name, voice, priority, message in agent_specs:
            client = VoiceCoordinationClient(
                server_url=f"ws://localhost:{e2e_server.port}",
                agent_name=name
            )
            client.test_voice = voice
            client.test_priority = priority
            client.test_message = message
            clients.append(client)
        
        # Connect all clients
        for client in clients:
            connected = await client.connect()
            assert connected, f"Failed to connect {client.agent_name}"
        
        try:
            # Submit requests in reverse priority order (low first)
            speech_order = []
            
            # Submit all requests quickly
            request_tasks = []
            for client in clients:
                task = asyncio.create_task(
                    client.request_speak(
                        client.test_message,
                        estimated_duration=3.0,
                        priority=client.test_priority
                    )
                )
                request_tasks.append((client, task))
            
            # Wait for all requests to be queued
            await asyncio.sleep(1.0)
            
            # Process speaking queue by handling each agent
            active_speakers = []
            for client, task in request_tasks:
                result = await task
                if result.get("granted"):
                    active_speakers.append(client)
            
            # Handle speaking in coordination order
            for client in active_speakers:
                if not client.test_message:
                    continue
                    
                # Wait for permission if needed
                permission = await client.wait_for_permission(timeout=10.0)
                if permission:
                    await client.update_status("speaking")
                    
                    # Actual speech with timing
                    start_time = time.time()
                    speech_process = await speech_simulator.speak(
                        client.test_message,
                        voice=client.test_voice
                    )
                    
                    speech_order.append((client.agent_name, client.test_priority, start_time))
                    logger.info(f"Speech order so far: {[s[0] for s in speech_order]}")
                    
                    # Wait for completion
                    if speech_process:
                        await speech_simulator.wait_for_speech(speech_process, timeout=6.0)
                    
                    await client.notify_speech_complete()
                    await client.update_status("idle")
            
            # Analyze speech order
            assert len(speech_order) >= 2, "Need at least 2 speakers to test ordering"
            
            # Sort by actual speak time to get real order
            actual_order = sorted(speech_order, key=lambda x: x[2])
            
            # High priority should be early in the order
            high_priority_pos = next(
                (i for i, (name, priority, _) in enumerate(actual_order) if priority == 10),
                -1
            )
            low_priority_pos = next(
                (i for i, (name, priority, _) in enumerate(actual_order) if priority == 1),
                -1
            )
            
            if high_priority_pos >= 0 and low_priority_pos >= 0:
                assert high_priority_pos < low_priority_pos, \
                    f"Priority ordering failed: high={high_priority_pos}, low={low_priority_pos}"
        
        finally:
            for client in clients:
                await client.disconnect()

@pytest.mark.e2e
class TestE2EAutoAgentIntegration:
    """Test AutoAgent integration end-to-end"""
    
    @pytest.mark.asyncio
    async def test_autoagent_team_coordination(self, e2e_server, speech_simulator):
        """Test AutoAgent team coordination with real speech"""
        # Skip if AutoAgent not available
        try:
            from autoagent_voice_integration import AutoAgentVoiceCoordinator, AutoAgentVoiceWrapper
        except ImportError:
            pytest.skip("AutoAgent integration not available")
        
        # Create AutoAgent coordinator
        coordinator = AutoAgentVoiceCoordinator(
            coordination_server_url=f"ws://localhost:{e2e_server.port}"
        )
        
        # Register a development team
        team = await coordinator.register_team(
            team_name="development-team-e2e",
            agent_types=["websurfer", "codex", "executor"],
            priority=6
        )
        
        wrapper = AutoAgentVoiceWrapper(coordinator, team.team_id)
        
        # Test coordinated team conversation
        conversation_flow = [
            ("websurfer", "I found relevant documentation for the implementation.", "Victoria"),
            ("codex", "Based on the research, I'll generate the solution code.", "Alex"),
            ("executor", "Running tests on the generated implementation.", "Samantha")
        ]
        
        spoken_agents = []
        
        for agent_type, message, voice in conversation_flow:
            # Override speak method to use our simulator
            async def mock_speak():
                # Request coordination
                result = await coordinator.coordinate_team_speech(
                    team.team_id, agent_type, message, priority=None
                )
                
                if result.get("granted"):
                    # Wait for permission if queued
                    if not result.get("fallback"):
                        if team.coordination_client:
                            permission = await team.coordination_client.wait_for_permission(timeout=10.0)
                            if not permission:
                                return False
                    
                    # Simulate speech
                    full_message = f"[{team.name}:{agent_type}] {message}"
                    speech_process = await speech_simulator.speak(full_message, voice=voice)
                    spoken_agents.append(agent_type)
                    
                    # Wait for completion
                    if speech_process:
                        await speech_simulator.wait_for_speech(speech_process, timeout=8.0)
                    
                    # Notify completion
                    await coordinator.notify_team_speech_complete(team.team_id)
                    return True
                
                return False
            
            success = await mock_speak()
            assert success, f"Failed to speak as {agent_type}"
            
            # Brief pause between team members
            await asyncio.sleep(0.5)
        
        # Verify all agents spoke
        assert len(spoken_agents) == 3, f"Expected 3 agents, got {len(spoken_agents)}"
        assert "websurfer" in spoken_agents
        assert "codex" in spoken_agents  
        assert "executor" in spoken_agents

@pytest.mark.e2e
class TestE2ERealWorldScenarios:
    """Test real-world usage scenarios"""
    
    @pytest.mark.asyncio
    async def test_development_workflow_simulation(self, e2e_server, speech_simulator):
        """Simulate a real development workflow with voice coordination"""
        # Simulate a development team workflow
        workflow_agents = [
            ("research-agent", "I've analyzed the requirements and found best practices.", "Victoria", 6),
            ("planning-agent", "Based on research, here's the implementation plan.", "Alex", 7),
            ("coding-agent", "I'm implementing the solution according to the plan.", "Daniel", 8),
            ("testing-agent", "Running comprehensive tests on the implementation.", "Samantha", 6),
            ("review-agent", "Code review complete, everything looks good!", "Fred", 5)
        ]
        
        # Create all agents
        clients = []
        for name, message, voice, priority in workflow_agents:
            client = VoiceCoordinationClient(
                server_url=f"ws://localhost:{e2e_server.port}",
                agent_name=name
            )
            client.test_voice = voice
            client.test_message = message
            client.test_priority = priority
            clients.append(client)
        
        # Connect all agents
        for client in clients:
            connected = await client.connect()
            assert connected, f"Failed to connect {client.agent_name}"
        
        try:
            # Simulate workflow: agents speak in logical order but with coordination
            workflow_results = []
            
            for client in clients:
                # Request to speak
                result = await client.request_speak(
                    client.test_message,
                    estimated_duration=4.0,
                    priority=client.test_priority
                )
                
                # Handle coordination
                if result.get("granted"):
                    if not result.get("fallback"):
                        permission = await client.wait_for_permission(timeout=15.0)
                        if not permission:
                            workflow_results.append((client.agent_name, False))
                            continue
                    
                    # Execute speech
                    await client.update_status("speaking")
                    speech_process = await speech_simulator.speak(
                        f"[{client.agent_name}] {client.test_message}",
                        voice=client.test_voice
                    )
                    
                    workflow_results.append((client.agent_name, True))
                    
                    # Wait for completion
                    if speech_process:
                        await speech_simulator.wait_for_speech(speech_process, timeout=8.0)
                    
                    await client.notify_speech_complete()
                    await client.update_status("idle")
                    
                    # Realistic pause between workflow steps
                    await asyncio.sleep(1.0)
            
            # Verify workflow completion
            successful_agents = [name for name, success in workflow_results if success]
            assert len(successful_agents) >= 3, f"Expected at least 3 successful speakers, got {len(successful_agents)}"
            
            # Verify high priority agents (coding-agent) spoke
            assert "coding-agent" in successful_agents, "Critical coding agent didn't speak"
        
        finally:
            for client in clients:
                await client.disconnect()

if __name__ == "__main__":
    # Run E2E tests
    pytest.main([__file__, "-v", "-m", "e2e", "--tb=short"])