#!/usr/bin/env python3
"""
Claude Code Voice Coordination Hook

This hook integrates with the Voice Coordination Server to prevent
multiple Claude Code agents from speaking simultaneously.
"""

import asyncio
import json
import os
import uuid
import websockets
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import sys
import logging

logger = logging.getLogger(__name__)

class VoiceCoordinationClient:
    """Client to connect to Voice Coordination Server"""
    
    def __init__(self, server_url: str = "ws://localhost:8765", agent_name: str = None):
        self.server_url = server_url
        self.rest_url = server_url.replace("ws://", "http://").replace("wss://", "https://")
        self.agent_id = str(uuid.uuid4())
        self.agent_name = agent_name or f"claude-code-{self.agent_id[:8]}"
        self.websocket = None
        self.connected = False
        self.workspace_id = os.environ.get("WORKSPACE_ID") or os.getcwd()
        self.user_id = os.environ.get("USER") or "unknown"
        
    async def connect(self):
        """Connect to coordination server"""
        try:
            uri = f"{self.server_url}/ws/{self.agent_id}"
            self.websocket = await websockets.connect(uri, timeout=5)
            self.connected = True
            
            # Register agent
            await self.websocket.send(json.dumps({
                "type": "register",
                "name": self.agent_name,
                "type": "claude-code",
                "priority": 5,
                "workspace_id": self.workspace_id,
                "user_id": self.user_id
            }))
            
            # Wait for registration confirmation
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5)
            data = json.loads(response)
            
            if data.get("type") == "registration_confirmed":
                logger.info(f"Connected to voice coordination server as {self.agent_name}")
                return True
            else:
                logger.error(f"Registration failed: {data}")
                return False
                
        except Exception as e:
            logger.warning(f"Could not connect to voice coordination server: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from coordination server"""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        self.connected = False
    
    async def request_speak(self, message: str, estimated_duration: float = 10.0, 
                          priority: int = None, voice_settings: Dict = None) -> Dict:
        """Request permission to speak"""
        if not self.connected:
            # Fallback - allow speaking if not connected to coordinator
            return {"granted": True, "fallback": True}
        
        try:
            # Try REST API first (faster)
            response = requests.post(
                f"{self.rest_url}/agents/{self.agent_id}/speak",
                json={
                    "message": message,
                    "estimated_duration": estimated_duration,
                    "priority": priority or 5,
                    "voice_settings": voice_settings or {}
                },
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Speak request failed: {response.text}")
                return {"granted": False, "error": response.text}
                
        except Exception as e:
            logger.warning(f"Error requesting speak permission: {e}")
            # Fallback - allow speaking if coordinator is unreachable
            return {"granted": True, "fallback": True}
    
    async def wait_for_permission(self, timeout: float = 30.0) -> bool:
        """Wait for speaking permission"""
        if not self.connected:
            return True
        
        try:
            while True:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
                data = json.loads(message)
                
                if data.get("type") == "speak_granted":
                    return True
                elif data.get("type") == "speak_denied":
                    return False
                    
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for speak permission")
            return True  # Fallback
        except Exception as e:
            logger.warning(f"Error waiting for permission: {e}")
            return True  # Fallback
    
    async def notify_speech_complete(self):
        """Notify that speech is complete"""
        if not self.connected:
            return
        
        try:
            await self.websocket.send(json.dumps({
                "type": "speech_complete",
                "timestamp": datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.warning(f"Error notifying speech complete: {e}")
    
    async def update_status(self, status: str):
        """Update agent status"""
        if not self.connected:
            return
        
        try:
            await self.websocket.send(json.dumps({
                "type": "status_update",
                "status": status,
                "timestamp": datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.warning(f"Error updating status: {e}")

# Global client instance
_coordination_client: Optional[VoiceCoordinationClient] = None

async def get_coordination_client() -> VoiceCoordinationClient:
    """Get or create coordination client"""
    global _coordination_client
    
    if _coordination_client is None:
        # Determine agent name from environment or process
        agent_name = None
        if "CLAUDE_CODE_SESSION_ID" in os.environ:
            agent_name = f"claude-code-{os.environ['CLAUDE_CODE_SESSION_ID'][:8]}"
        elif "WORKSPACE_NAME" in os.environ:
            agent_name = f"claude-code-{os.environ['WORKSPACE_NAME']}"
        
        _coordination_client = VoiceCoordinationClient(agent_name=agent_name)
        await _coordination_client.connect()
    
    return _coordination_client

def extract_voice_params(tool_call: str) -> Dict[str, Any]:
    """Extract voice parameters from tool call"""
    voice_params = {
        "message": "",
        "estimated_duration": 10.0,
        "priority": 5
    }
    
    try:
        # Parse the tool call to extract parameters
        if "converse(" in tool_call:
            # Extract message
            if 'message="' in tool_call:
                start = tool_call.find('message="') + 9
                end = tool_call.find('"', start)
                if end > start:
                    voice_params["message"] = tool_call[start:end]
            
            # Extract estimated duration from listen_duration
            if "listen_duration=" in tool_call:
                start = tool_call.find("listen_duration=") + 16
                end = tool_call.find(",", start)
                if end == -1:
                    end = tool_call.find(")", start)
                if end > start:
                    try:
                        duration = float(tool_call[start:end].strip())
                        # Estimate speech duration as 1/3 of total duration
                        voice_params["estimated_duration"] = max(5.0, duration / 3)
                    except:
                        pass
        
    except Exception as e:
        logger.warning(f"Error parsing voice parameters: {e}")
    
    return voice_params

async def voice_coordination_hook(hook_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Claude Code hook for voice coordination
    
    This hook:
    1. Intercepts voice tool calls before execution
    2. Requests permission from coordination server
    3. Queues the request if other agents are speaking
    4. Notifies server when speech is complete
    """
    
    # Only handle tool calls
    if hook_type != "tool_call":
        return data
    
    tool_name = data.get("tool_name", "")
    
    # Only coordinate voice tools
    if "converse" not in tool_name and "voice" not in tool_name:
        return data
    
    try:
        client = await get_coordination_client()
        
        # Extract voice parameters from tool call
        tool_call_str = str(data.get("tool_call", ""))
        voice_params = extract_voice_params(tool_call_str)
        
        # Update status to speaking intent
        await client.update_status("requesting_speech")
        
        # Request permission to speak
        request_result = await client.request_speak(
            message=voice_params["message"],
            estimated_duration=voice_params["estimated_duration"],
            priority=voice_params["priority"]
        )
        
        if request_result.get("granted"):
            logger.info(f"Voice permission granted for: {voice_params['message'][:50]}...")
            
            # If not immediate grant, wait for permission
            if not request_result.get("fallback"):
                permission_granted = await client.wait_for_permission()
                if not permission_granted:
                    # Speech was denied or timed out
                    await client.update_status("idle")
                    logger.warning("Voice permission denied or timed out")
                    return {
                        **data,
                        "skip_execution": True,
                        "result": "Speech request denied - another agent is speaking"
                    }
            
            # Update status to speaking
            await client.update_status("speaking")
            
            # Add completion hook to the tool call
            original_result = data.get("result")
            
            # Execute the tool call normally
            result = data
            
            # Schedule completion notification
            async def notify_completion():
                await asyncio.sleep(0.1)  # Small delay to ensure speech starts
                await client.notify_speech_complete()
                await client.update_status("idle")
            
            asyncio.create_task(notify_completion())
            
            return result
            
        else:
            # Permission denied
            await client.update_status("idle")
            logger.info("Voice permission denied - queued or rejected")
            
            queue_info = request_result.get("queue_position", "unknown")
            estimated_wait = request_result.get("estimated_wait", 0)
            
            return {
                **data,
                "skip_execution": True,
                "result": f"Speech queued (position {queue_info}, wait ~{estimated_wait:.1f}s)"
            }
            
    except Exception as e:
        logger.error(f"Voice coordination hook error: {e}")
        # Fallback - allow speech if coordination fails
        return data

def setup_voice_coordination_hook():
    """Setup the voice coordination hook"""
    # This would integrate with Claude Code's hook system
    # For now, we'll show how it would be configured
    hook_config = {
        "name": "voice_coordination",
        "description": "Coordinates voice between multiple agents",
        "hook_function": voice_coordination_hook,
        "triggers": ["tool_call"],
        "priority": 10  # High priority to run before voice tools
    }
    
    return hook_config

if __name__ == "__main__":
    # Test the coordination client
    async def test():
        client = VoiceCoordinationClient(agent_name="test-agent")
        if await client.connect():
            print("Connected successfully")
            
            result = await client.request_speak("Testing voice coordination", 5.0)
            print(f"Speak request result: {result}")
            
            if result.get("granted"):
                print("Permission granted, simulating speech...")
                await asyncio.sleep(3)
                await client.notify_speech_complete()
                print("Speech complete")
            
            await client.disconnect()
        else:
            print("Failed to connect")
    
    asyncio.run(test())