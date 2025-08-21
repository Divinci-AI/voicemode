# Multi-Agent Voice Coordination System

A comprehensive system for coordinating voice communication between multiple Claude Code agents and AutoAgent teams to prevent overlapping speech and ensure orderly conversation flow.

## 🎯 System Overview

The Voice Coordination System consists of three main components:

1. **Voice Coordination Server** - Central hub managing agent registration and speech queuing
2. **Claude Code Hook Integration** - Intercepts voice tool calls for coordination
3. **AutoAgent Integration** - Coordinates multi-agent team voice communication

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                Voice Coordination Server                │
│  (WebSocket + REST API on port 8765)                  │
├─────────────────────────────────────────────────────────┤
│  📊 Agent Registry                                     │
│    ├── Claude Code Agents                              │
│    ├── AutoAgent Teams                                 │
│    └── Status Tracking                                 │
├─────────────────────────────────────────────────────────┤
│  🎤 Voice Queue Management                             │
│    ├── Priority-based Queuing                          │
│    ├── Speech Duration Estimation                      │
│    └── Conflict Resolution                             │
├─────────────────────────────────────────────────────────┤
│  🔗 Integration Hooks                                  │
│    ├── Claude Code Tool Interception                   │
│    ├── AutoAgent Team Coordination                     │
│    └── Real-time Status Updates                        │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Start the Coordination Server

```bash
# Start the central coordination server
python voice_coordination_server.py
```

The server will start on port 8765 with both WebSocket and REST endpoints.

### 2. Configure Claude Code Hooks

Add the voice coordination hook to your Claude Code settings:

```python
from claude_code_voice_hook import setup_voice_coordination_hook

# Setup the hook (this would integrate with Claude Code's hook system)
hook_config = setup_voice_coordination_hook()
```

### 3. Setup AutoAgent Integration

```python
from autoagent_voice_integration import setup_autoagent_voice_coordination

# Initialize AutoAgent voice coordination
coordinator, team_ids = await setup_autoagent_voice_coordination()
```

### 4. Test the System

```bash
# Run comprehensive system tests
python test_voice_coordination_system.py
```

## 🎛️ Configuration

### Environment Variables

```bash
# Coordination server URL (default: ws://localhost:8765)
VOICE_COORDINATION_SERVER_URL=ws://localhost:8765

# Agent identification
CLAUDE_CODE_SESSION_ID=your-session-id
WORKSPACE_ID=your-workspace-id
USER=your-username

# Debugging
VOICE_COORDINATION_DEBUG=true
```

### Server Configuration

The coordination server can be configured via `VoiceCoordinationServer` parameters:

```python
server = VoiceCoordinationServer(
    port=8765,                    # Server port
    max_queue_size=50,           # Maximum queue size
    default_timeout=30.0,        # Default speech timeout
    heartbeat_interval=30.0      # Agent heartbeat interval
)
```

## 🤖 Agent Types and Priorities

### Default Priorities

| Agent Type | Base Priority | Description |
|------------|---------------|-------------|
| Claude Code | 5 | Standard Claude Code assistant |
| AutoAgent Codex | 7 | Code generation agent |
| AutoAgent WebSurfer | 6 | Research and documentation |
| AutoAgent Executor | 5 | Code execution and testing |
| AutoAgent FileSurfer | 4 | File system operations |

### Priority Modifiers

- **High Priority**: Critical alerts, errors, completions (+3)
- **Normal Priority**: Regular conversation, responses (0)
- **Low Priority**: Status updates, logging (-2)

## 🎤 Speech Coordination Flow

### 1. Speech Request
```python
# Agent requests permission to speak
result = await client.request_speak(
    message="Hello, I need to report something important",
    estimated_duration=10.0,
    priority=7
)
```

### 2. Queue Management
- Requests are queued by priority (higher first)
- Within same priority: first-in, first-out
- Current speaker gets exclusive access
- Queue position and wait time estimates provided

### 3. Permission Granted
```python
if result["granted"]:
    # Agent can speak immediately or wait for permission
    if not result.get("fallback"):
        await client.wait_for_permission()
    
    # Proceed with voice output
    # ... actual TTS/voice generation ...
    
    # Notify completion
    await client.notify_speech_complete()
```

## 🔗 API Reference

### WebSocket Messages

#### Agent Registration
```json
{
  "type": "register",
  "name": "claude-code-session-123",
  "type": "claude-code",
  "priority": 5,
  "workspace_id": "/path/to/workspace",
  "user_id": "username"
}
```

#### Speech Request
```json
{
  "type": "speak_request",
  "message": "Hello, this is my message",
  "estimated_duration": 8.5,
  "priority": 6,
  "voice_settings": {
    "voice": "alloy",
    "model": "tts-1"
  }
}
```

#### Status Update
```json
{
  "type": "status_update",
  "status": "speaking",
  "timestamp": "2025-01-19T12:00:00Z"
}
```

### REST Endpoints

#### Request Speech Permission
```
POST /agents/{agent_id}/speak
Content-Type: application/json

{
  "message": "Speech content",
  "estimated_duration": 10.0,
  "priority": 5,
  "voice_settings": {}
}
```

#### Update Agent Status
```
POST /agents/{agent_id}/status
Content-Type: application/json

{
  "status": "busy",
  "priority": 6
}
```

#### Get Server Status
```
GET /status

Response:
{
  "server_time": "2025-01-19T12:00:00Z",
  "total_agents": 3,
  "current_speaker": "agent-123",
  "queue_length": 2,
  "agents_by_status": {
    "idle": 2,
    "speaking": 1,
    "listening": 0,
    "busy": 0
  }
}
```

## 🧪 Testing

### Run All Tests
```bash
python test_voice_coordination_system.py
```

### Individual Test Components

```bash
# Test basic coordination
python -c "import asyncio; from test_voice_coordination_system import VoiceCoordinationSystemTest; t = VoiceCoordinationSystemTest(); asyncio.run(t.test_basic_coordination())"

# Test AutoAgent integration
python autoagent_voice_integration.py

# Test hook system
python claude_code_voice_hook.py
```

### Expected Test Results

```
🧪 VOICE COORDINATION SYSTEM TEST RESULTS
============================================================
✅ PASS Basic Coordination
✅ PASS Hook Integration  
✅ PASS Priority System
✅ PASS AutoAgent Integration
------------------------------------------------------------
📊 Summary: 4 passed, 0 failed, 0 skipped
============================================================
```

## 🎯 Use Cases

### 1. Multiple Claude Code Sessions
Prevent multiple Claude Code instances from speaking simultaneously when working on the same project or in shared environments.

### 2. AutoAgent Team Coordination
Coordinate speech between different agent types in AutoAgent teams:
- WebSurfer reports research findings
- Codex announces code generation
- Executor reports test results
- FileSurfer confirms file operations

### 3. Multi-User Environments
Manage voice communication in shared workspaces where multiple users have active AI assistants.

### 4. Complex Development Workflows
Orchestrate voice updates during complex workflows:
1. Research phase (WebSurfer speaks)
2. Planning phase (Claude Code speaks)
3. Implementation phase (Codex speaks)
4. Testing phase (Executor speaks)
5. Deployment phase (Multiple agents coordinate)

## 🔧 Advanced Configuration

### Custom Agent Types

```python
# Register custom agent type with specific priority
await coordinator.register_agent(
    agent_id="custom-agent-123",
    agent_data={
        "name": "Custom Development Agent",
        "type": "custom-dev",
        "priority": 8,  # High priority
        "capabilities": ["code_review", "testing", "deployment"]
    }
)
```

### Conversation Flows

```python
# Create coordinated conversation between teams
conv_id = await coordinator.create_coordinated_conversation([
    "research_team",
    "development_team", 
    "qa_team"
])

# Agents automatically follow turn-based speaking order
```

### Priority Policies

```python
# Custom priority calculation
def calculate_priority(agent_type, message_type, urgency):
    base_priorities = {
        "claude-code": 5,
        "autoagent-codex": 7,
        "autoagent-websurfer": 6
    }
    
    urgency_modifiers = {
        "critical": +5,
        "high": +2,
        "normal": 0,
        "low": -2
    }
    
    return base_priorities.get(agent_type, 5) + urgency_modifiers.get(urgency, 0)
```

## 🚨 Troubleshooting

### Common Issues

1. **Server Connection Failed**
   ```bash
   # Check if server is running
   curl http://localhost:8765/status
   
   # Check logs
   python voice_coordination_server.py --verbose
   ```

2. **Agents Not Coordinating**
   ```python
   # Verify agent registration
   from claude_code_voice_hook import VoiceCoordinationClient
   client = VoiceCoordinationClient()
   connected = await client.connect()
   print(f"Connected: {connected}")
   ```

3. **Speech Stuck in Queue**
   ```bash
   # Check queue status
   curl http://localhost:8765/status
   
   # Clear stuck queues (restart server)
   pkill -f voice_coordination_server.py
   python voice_coordination_server.py
   ```

### Debug Mode

```bash
# Enable debug logging
export VOICE_COORDINATION_DEBUG=true
python voice_coordination_server.py --log-level DEBUG
```

## 🔮 Future Enhancements

- **Web Dashboard**: Real-time coordination monitoring
- **Voice Analytics**: Speech pattern analysis and optimization
- **Multi-Language Support**: Coordinate speech in different languages
- **Cloud Deployment**: Distributed coordination across multiple machines
- **Integration APIs**: REST APIs for third-party agent frameworks
- **Voice Biometrics**: Speaker identification and authentication

## 📜 License

This Voice Coordination System is part of the VoiceMode project and follows the same licensing terms.

---

*Built with ❤️ for coordinated AI voice communication*