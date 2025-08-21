#!/usr/bin/env python3
"""
Pytest configuration and fixtures for Voice Coordination System tests.

This file provides shared fixtures, configuration, and utilities for all tests.
"""

import pytest
import asyncio
import tempfile
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock
import platform

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
TEST_SERVER_PORT = 8768
TEST_TIMEOUT = 30.0


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def is_macos():
    """Check if running on macOS."""
    return platform.system() == "Darwin"


@pytest.fixture(scope="session")
def has_say_command(is_macos):
    """Check if macOS say command is available."""
    if not is_macos:
        return False
    
    try:
        subprocess.run(["say", "--version"], 
                      capture_output=True, 
                      timeout=5)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_server_port():
    """Get test server port."""
    return TEST_SERVER_PORT


@pytest.fixture
def mock_websocket():
    """Create a mock websocket for testing."""
    mock_ws = AsyncMock()
    mock_ws.send.return_value = None
    mock_ws.recv.return_value = '{"type": "test", "data": "mock"}'
    mock_ws.close.return_value = None
    mock_ws.closed = False
    return mock_ws


@pytest.fixture
def sample_agent_data():
    """Sample agent data for tests."""
    return {
        "id": "test-agent-123",
        "name": "Test Agent",
        "type": "claude-code",
        "priority": 5,
        "workspace_id": "/tmp/test-workspace",
        "user_id": "test-user"
    }


@pytest.fixture
def sample_voice_request():
    """Sample voice request for tests."""
    return {
        "message": "This is a test message for voice coordination",
        "estimated_duration": 5.0,
        "priority": 5,
        "voice_settings": {
            "voice": "Alex",
            "rate": 200
        }
    }


@pytest.fixture
def mock_coordination_client():
    """Create a mock coordination client."""
    client = Mock()
    client.agent_id = "mock-agent-123"
    client.agent_name = "Mock Agent"
    client.connected = True
    client.server_url = f"ws://localhost:{TEST_SERVER_PORT}"
    
    # Async methods
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.request_speak = AsyncMock(return_value={"granted": True})
    client.wait_for_permission = AsyncMock(return_value=True)
    client.notify_speech_complete = AsyncMock()
    client.update_status = AsyncMock()
    
    return client


@pytest.fixture
async def test_coordination_server():
    """Start a test coordination server."""
    # Import here to avoid circular imports
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    
    from voice_coordination_server import VoiceCoordinationServer
    
    server = VoiceCoordinationServer(port=TEST_SERVER_PORT)
    
    # Start server in background task
    server_task = asyncio.create_task(server.start_server())
    
    # Give server time to start
    await asyncio.sleep(1.0)
    
    yield server
    
    # Cleanup
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


@pytest.fixture
def voice_tool_call_data():
    """Sample voice tool call data for hook tests."""
    return {
        "tool_name": "mcp__voice-mode__converse",
        "tool_call": 'converse(message="Test voice coordination", listen_duration=15.0, priority=5)',
        "parameters": {
            "message": "Test voice coordination",
            "listen_duration": 15.0,
            "priority": 5
        },
        "result": None
    }


@pytest.fixture
def multi_agent_scenario():
    """Configuration for multi-agent test scenarios."""
    return [
        {
            "name": "Research Agent",
            "type": "autoagent-websurfer", 
            "priority": 6,
            "message": "I found relevant documentation for the task.",
            "voice": "Victoria"
        },
        {
            "name": "Code Agent",
            "type": "autoagent-codex",
            "priority": 8,
            "message": "Generating implementation based on requirements.",
            "voice": "Alex"
        },
        {
            "name": "Test Agent",
            "type": "autoagent-executor",
            "priority": 5,
            "message": "Running tests on the generated code.",
            "voice": "Samantha"
        }
    ]


@pytest.fixture
def speech_simulator(has_say_command):
    """Speech simulator that uses real say() on macOS or simulation elsewhere."""
    class SpeechSimulator:
        def __init__(self, has_say):
            self.has_say = has_say
            self.processes = []
        
        async def speak(self, text, voice="Alex", rate=200):
            """Simulate speaking text."""
            if self.has_say:
                try:
                    process = subprocess.Popen([
                        "say", "-v", voice, "-r", str(rate), text
                    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    self.processes.append(process)
                    logger.info(f"[macOS SPEECH] {voice}: {text[:50]}...")
                    return process
                except Exception as e:
                    logger.warning(f"say command failed: {e}")
            
            # Fallback: simulate speech timing
            duration = max(1.0, len(text) * 0.05)  # ~20 characters per second
            logger.info(f"[SIMULATED SPEECH] {voice}: {text[:50]}... ({duration:.1f}s)")
            await asyncio.sleep(min(duration, 3.0))  # Cap at 3 seconds for tests
            return None
        
        async def wait_for_completion(self, process, timeout=10.0):
            """Wait for speech process to complete."""
            if not process:
                return True
            
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(process.wait),
                    timeout=timeout
                )
                return True
            except asyncio.TimeoutError:
                process.terminate()
                return False
        
        def cleanup(self):
            """Clean up any running processes."""
            for process in self.processes:
                if process.poll() is None:
                    process.terminate()
            self.processes.clear()
    
    simulator = SpeechSimulator(has_say_command)
    yield simulator
    simulator.cleanup()


# Test collection hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers and ordering."""
    for item in items:
        # Add markers based on test names and file paths
        if "e2e" in item.name or "test_e2e" in item.nodeid:
            item.add_marker(pytest.mark.e2e)
        
        if "unit" in item.name or "test_coordination_server" in item.nodeid or "test_client_hook" in item.nodeid:
            item.add_marker(pytest.mark.unit)
        
        if "voice" in item.name or "speech" in item.name:
            item.add_marker(pytest.mark.voice)
        
        if "server" in item.name:
            item.add_marker(pytest.mark.server)
        
        if "client" in item.name or "hook" in item.name:
            item.add_marker(pytest.mark.client)
        
        if "autoagent" in item.name:
            item.add_marker(pytest.mark.autoagent)
        
        if "priority" in item.name or "coordination" in item.name:
            item.add_marker(pytest.mark.integration)


def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Create test-reports directory
    reports_dir = Path("test-reports")
    reports_dir.mkdir(exist_ok=True)
    
    # Set environment variables for tests
    os.environ["VOICE_COORDINATION_TEST_MODE"] = "true"
    os.environ["VOICE_COORDINATION_TEST_PORT"] = str(TEST_SERVER_PORT)


def pytest_sessionstart(session):
    """Called before test collection starts."""
    logger.info("🧪 Starting Voice Coordination System test session")
    logger.info(f"Test server port: {TEST_SERVER_PORT}")
    logger.info(f"Platform: {platform.system()} {platform.release()}")
    
    # Check if we can use macOS features
    if platform.system() == "Darwin":
        try:
            subprocess.run(["say", "--version"], capture_output=True, timeout=2)
            logger.info("🔊 macOS say() command available for speech tests")
        except Exception:
            logger.info("🔇 macOS say() command not available - speech will be simulated")


def pytest_sessionfinish(session, exitstatus):
    """Called after test session finishes."""
    logger.info(f"🏁 Voice Coordination System test session finished (exit code: {exitstatus})")


# Skip markers for different environments
pytestmark = [
    pytest.mark.skipif(
        os.getenv("CI") == "true" and platform.system() != "Darwin",
        reason="E2E voice tests require macOS in CI"
    )
]