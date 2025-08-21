#!/usr/bin/env python3
"""
Voice Coordination Server for Multi-Agent Systems

Prevents voice overlap between multiple Claude Code agents and AutoAgent teams
by managing a central queue and coordination system.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from pathlib import Path
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.websockets import WebSocketDisconnect
import uvicorn
import logging

logger = logging.getLogger(__name__)

@dataclass
class Agent:
    """Represents a connected agent"""
    id: str
    name: str
    type: str  # "claude-code", "autoagent", "websurfer", "filesurfer", etc.
    status: str  # "idle", "speaking", "listening", "busy"
    connected_at: datetime
    last_heartbeat: datetime
    priority: int = 5  # 1-10, higher = more priority
    workspace_id: Optional[str] = None
    user_id: Optional[str] = None

@dataclass
class VoiceRequest:
    """Represents a voice request from an agent"""
    id: str
    agent_id: str
    message: str
    priority: int
    request_time: datetime
    estimated_duration: float = 10.0  # seconds
    voice_settings: Dict[str, Any] = None
    
class VoiceCoordinationServer:
    def __init__(self, port: int = 8765):
        self.port = port
        self.agents: Dict[str, Agent] = {}
        self.voice_queue: List[VoiceRequest] = []
        self.current_speaker: Optional[str] = None  # agent_id
        self.speaking_start_time: Optional[float] = None
        self.websockets: Dict[str, WebSocket] = {}
        self.app = FastAPI(title="Voice Coordination Server")
        
        # Setup FastAPI routes
        self.setup_routes()
        
    def setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.websocket("/ws/{agent_id}")
        async def websocket_endpoint(websocket: WebSocket, agent_id: str):
            await self.handle_websocket(websocket, agent_id)
            
        @self.app.post("/agents/{agent_id}/speak")
        async def request_speak(agent_id: str, request: dict):
            return await self.request_speak(agent_id, request)
            
        @self.app.post("/agents/{agent_id}/status")
        async def update_status(agent_id: str, status: dict):
            return await self.update_agent_status(agent_id, status)
            
        @self.app.get("/status")
        async def get_server_status():
            return self.get_coordination_status()
            
        @self.app.get("/agents")
        async def list_agents():
            return {
                "agents": [asdict(agent) for agent in self.agents.values()],
                "total": len(self.agents)
            }
    
    async def handle_websocket(self, websocket: WebSocket, agent_id: str):
        """Handle WebSocket connections from agents"""
        await websocket.accept()
        self.websockets[agent_id] = websocket
        
        try:
            while True:
                data = await websocket.receive_json()
                await self.process_agent_message(agent_id, data)
        except WebSocketDisconnect:
            await self.disconnect_agent(agent_id)
        except Exception as e:
            logger.error(f"WebSocket error for agent {agent_id}: {e}")
            await self.disconnect_agent(agent_id)
    
    async def process_agent_message(self, agent_id: str, data: dict):
        """Process messages from agents"""
        message_type = data.get("type")
        
        if message_type == "register":
            await self.register_agent(agent_id, data)
        elif message_type == "heartbeat":
            await self.update_heartbeat(agent_id)
        elif message_type == "speak_request":
            await self.handle_speak_request(agent_id, data)
        elif message_type == "status_update":
            await self.update_agent_status(agent_id, data)
        elif message_type == "speech_complete":
            await self.handle_speech_complete(agent_id)
        else:
            logger.warning(f"Unknown message type from {agent_id}: {message_type}")
    
    async def register_agent(self, agent_id: str, data: dict):
        """Register a new agent"""
        agent = Agent(
            id=agent_id,
            name=data.get("name", f"Agent-{agent_id[:8]}"),
            type=data.get("type", "unknown"),
            status="idle",
            connected_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            priority=data.get("priority", 5),
            workspace_id=data.get("workspace_id"),
            user_id=data.get("user_id")
        )
        
        self.agents[agent_id] = agent
        logger.info(f"Registered agent: {agent.name} ({agent.type})")
        
        # Send registration confirmation
        await self.send_to_agent(agent_id, {
            "type": "registration_confirmed",
            "agent_id": agent_id,
            "server_status": self.get_coordination_status()
        })
        
        # Notify other agents
        await self.broadcast_except(agent_id, {
            "type": "agent_joined",
            "agent": asdict(agent)
        })
    
    async def request_speak(self, agent_id: str, request: dict):
        """Handle speak request via REST API"""
        if agent_id not in self.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        voice_request = VoiceRequest(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            message=request.get("message", ""),
            priority=request.get("priority", self.agents[agent_id].priority),
            request_time=datetime.now(timezone.utc),
            estimated_duration=request.get("estimated_duration", 10.0),
            voice_settings=request.get("voice_settings", {})
        )
        
        return await self.queue_voice_request(voice_request)
    
    async def queue_voice_request(self, voice_request: VoiceRequest):
        """Add voice request to queue and process"""
        # Insert by priority (higher priority first, then FIFO)
        inserted = False
        for i, existing in enumerate(self.voice_queue):
            if voice_request.priority > existing.priority:
                self.voice_queue.insert(i, voice_request)
                inserted = True
                break
        
        if not inserted:
            self.voice_queue.append(voice_request)
        
        logger.info(f"Queued voice request from {voice_request.agent_id}: {voice_request.message[:50]}...")
        
        # Try to process the queue
        await self.process_voice_queue()
        
        return {
            "request_id": voice_request.id,
            "queued_at": voice_request.request_time.isoformat(),
            "queue_position": self.voice_queue.index(voice_request) + 1 if voice_request in self.voice_queue else 0,
            "estimated_wait": self.estimate_wait_time(voice_request.id)
        }
    
    async def process_voice_queue(self):
        """Process the voice queue"""
        if self.current_speaker or not self.voice_queue:
            return
        
        # Get next request
        next_request = self.voice_queue.pop(0)
        agent_id = next_request.agent_id
        
        if agent_id not in self.agents or agent_id not in self.websockets:
            logger.warning(f"Agent {agent_id} not available for speaking")
            return
        
        # Grant speaking permission
        self.current_speaker = agent_id
        self.speaking_start_time = time.time()
        
        # Update agent status
        self.agents[agent_id].status = "speaking"
        
        # Send permission to agent
        await self.send_to_agent(agent_id, {
            "type": "speak_granted",
            "request_id": next_request.id,
            "message": next_request.message,
            "voice_settings": next_request.voice_settings or {},
            "estimated_duration": next_request.estimated_duration
        })
        
        # Notify other agents
        await self.broadcast_except(agent_id, {
            "type": "agent_speaking",
            "speaker_id": agent_id,
            "speaker_name": self.agents[agent_id].name,
            "estimated_duration": next_request.estimated_duration
        })
        
        logger.info(f"Granted speaking permission to {agent_id}")
        
        # Set timeout to prevent stuck speakers
        asyncio.create_task(self.speech_timeout(next_request.id, agent_id, next_request.estimated_duration))
    
    async def speech_timeout(self, request_id: str, agent_id: str, timeout: float):
        """Handle speech timeout"""
        await asyncio.sleep(timeout + 10)  # Grace period
        
        if self.current_speaker == agent_id:
            logger.warning(f"Speech timeout for agent {agent_id}")
            await self.handle_speech_complete(agent_id, timeout=True)
    
    async def handle_speech_complete(self, agent_id: str, timeout: bool = False):
        """Handle when an agent finishes speaking"""
        if self.current_speaker != agent_id:
            return
        
        self.current_speaker = None
        self.speaking_start_time = None
        
        if agent_id in self.agents:
            self.agents[agent_id].status = "idle"
        
        logger.info(f"Agent {agent_id} finished speaking{'(timeout)' if timeout else ''}")
        
        # Notify all agents
        await self.broadcast({
            "type": "speech_complete",
            "agent_id": agent_id,
            "timeout": timeout
        })
        
        # Process next in queue
        await self.process_voice_queue()
    
    async def update_agent_status(self, agent_id: str, status_data: dict):
        """Update agent status"""
        if agent_id not in self.agents:
            return {"error": "Agent not found"}
        
        agent = self.agents[agent_id]
        
        if "status" in status_data:
            agent.status = status_data["status"]
        if "priority" in status_data:
            agent.priority = status_data["priority"]
        
        agent.last_heartbeat = datetime.now(timezone.utc)
        
        # Broadcast status update
        await self.broadcast({
            "type": "agent_status_update",
            "agent_id": agent_id,
            "status": agent.status,
            "priority": agent.priority
        })
        
        return {"success": True}
    
    async def update_heartbeat(self, agent_id: str):
        """Update agent heartbeat"""
        if agent_id in self.agents:
            self.agents[agent_id].last_heartbeat = datetime.now(timezone.utc)
    
    async def disconnect_agent(self, agent_id: str):
        """Handle agent disconnection"""
        if agent_id in self.websockets:
            del self.websockets[agent_id]
        
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            logger.info(f"Agent disconnected: {agent.name}")
            
            # If this agent was speaking, mark as complete
            if self.current_speaker == agent_id:
                await self.handle_speech_complete(agent_id)
            
            # Remove from queue
            self.voice_queue = [req for req in self.voice_queue if req.agent_id != agent_id]
            
            # Remove agent
            del self.agents[agent_id]
            
            # Notify other agents
            await self.broadcast({
                "type": "agent_disconnected",
                "agent_id": agent_id,
                "agent_name": agent.name
            })
    
    def estimate_wait_time(self, request_id: str) -> float:
        """Estimate wait time for a request"""
        total_wait = 0.0
        
        # Add current speaker's remaining time
        if self.current_speaker and self.speaking_start_time:
            # Assume 5 seconds remaining on average
            total_wait += 5.0
        
        # Add estimated duration for requests ahead in queue
        for request in self.voice_queue:
            if request.id == request_id:
                break
            total_wait += request.estimated_duration
        
        return total_wait
    
    def get_coordination_status(self):
        """Get server coordination status"""
        return {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "total_agents": len(self.agents),
            "current_speaker": self.current_speaker,
            "queue_length": len(self.voice_queue),
            "agents_by_status": {
                status: len([a for a in self.agents.values() if a.status == status])
                for status in ["idle", "speaking", "listening", "busy"]
            }
        }
    
    async def send_to_agent(self, agent_id: str, message: dict):
        """Send message to specific agent"""
        if agent_id in self.websockets:
            try:
                await self.websockets[agent_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending to agent {agent_id}: {e}")
                await self.disconnect_agent(agent_id)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all agents"""
        for agent_id in list(self.websockets.keys()):
            await self.send_to_agent(agent_id, message)
    
    async def broadcast_except(self, except_agent_id: str, message: dict):
        """Broadcast message to all agents except one"""
        for agent_id in list(self.websockets.keys()):
            if agent_id != except_agent_id:
                await self.send_to_agent(agent_id, message)
    
    async def cleanup_stale_agents(self):
        """Cleanup stale agents"""
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            now = datetime.now(timezone.utc)
            stale_agents = []
            
            for agent_id, agent in self.agents.items():
                if (now - agent.last_heartbeat).total_seconds() > 120:  # 2 minutes
                    stale_agents.append(agent_id)
            
            for agent_id in stale_agents:
                logger.info(f"Cleaning up stale agent: {agent_id}")
                await self.disconnect_agent(agent_id)
    
    async def start_server(self):
        """Start the coordination server"""
        logger.info(f"Starting Voice Coordination Server on port {self.port}")
        
        # Start cleanup task
        asyncio.create_task(self.cleanup_stale_agents())
        
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0", 
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

async def main():
    """Main entry point"""
    logging.basicConfig(level=logging.INFO)
    
    server = VoiceCoordinationServer(port=8765)
    await server.start_server()

if __name__ == "__main__":
    asyncio.run(main())