#!/usr/bin/env python3
"""
AutoAgent Voice Integration

Integrates AutoAgent multi-agent teams with the Voice Coordination Server
to enable coordinated voice communication across all agent types.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import uuid
from pathlib import Path
import sys

# Add AutoAgent to path if available
autoagent_path = Path("/Users/mikeumus/Documents/AutoAgent")
if autoagent_path.exists():
    sys.path.insert(0, str(autoagent_path))

try:
    from claude_code_voice_hook import VoiceCoordinationClient
except ImportError:
    # Fallback if voice hook not available
    class VoiceCoordinationClient:
        def __init__(self, **kwargs): pass
        async def connect(self): return False
        async def request_speak(self, *args, **kwargs): return {"granted": True, "fallback": True}
        async def notify_speech_complete(self): pass

logger = logging.getLogger(__name__)

@dataclass
class AutoAgentTeam:
    """Represents an AutoAgent team"""
    team_id: str
    name: str
    agents: List[str]  # Agent types: websurfer, filesurfer, codex, executor
    priority: int
    current_speaker: Optional[str] = None
    coordination_client: Optional[VoiceCoordinationClient] = None

class AutoAgentVoiceCoordinator:
    """Coordinates voice communication for AutoAgent teams"""
    
    def __init__(self, coordination_server_url: str = "ws://localhost:8765"):
        self.server_url = coordination_server_url
        self.teams: Dict[str, AutoAgentTeam] = {}
        self.active_conversations: Dict[str, Dict] = {}
        
    async def register_team(self, team_name: str, agent_types: List[str], 
                          priority: int = 5) -> AutoAgentTeam:
        """Register a new AutoAgent team"""
        team_id = str(uuid.uuid4())
        
        # Create coordination client for the team
        client = VoiceCoordinationClient(
            server_url=self.server_url,
            agent_name=f"autoagent-{team_name}"
        )
        
        # Connect to coordination server
        connected = await client.connect()
        if not connected:
            logger.warning(f"Could not connect team {team_name} to coordination server")
        
        team = AutoAgentTeam(
            team_id=team_id,
            name=team_name,
            agents=agent_types,
            priority=priority,
            coordination_client=client
        )
        
        self.teams[team_id] = team
        logger.info(f"Registered AutoAgent team: {team_name} with agents {agent_types}")
        
        return team
    
    async def coordinate_team_speech(self, team_id: str, agent_type: str, 
                                   message: str, priority: int = None) -> Dict[str, Any]:
        """Coordinate speech for a specific agent in a team"""
        if team_id not in self.teams:
            return {"error": "Team not found"}
        
        team = self.teams[team_id]
        client = team.coordination_client
        
        if not client or not client.connected:
            # Fallback - allow speech if not coordinated
            return {"granted": True, "fallback": True}
        
        # Determine priority (team priority + agent-specific adjustments)
        effective_priority = priority or team.priority
        
        # Agent-specific priority adjustments
        priority_adjustments = {
            "websurfer": +1,    # Research is important
            "codex": +2,        # Code generation is high priority
            "executor": 0,      # Standard priority
            "filesurfer": -1    # File operations less urgent for voice
        }
        
        if agent_type in priority_adjustments:
            effective_priority += priority_adjustments[agent_type]
        
        # Request speech coordination
        try:
            result = await client.request_speak(
                message=f"[{agent_type}] {message}",
                estimated_duration=self.estimate_speech_duration(message, agent_type),
                priority=effective_priority
            )
            
            if result.get("granted"):
                team.current_speaker = agent_type
                logger.info(f"Team {team.name} agent {agent_type} granted speech permission")
            
            return result
            
        except Exception as e:
            logger.error(f"Error coordinating speech for team {team_id}: {e}")
            return {"granted": True, "fallback": True}
    
    async def notify_team_speech_complete(self, team_id: str):
        """Notify that team speech is complete"""
        if team_id not in self.teams:
            return
        
        team = self.teams[team_id]
        team.current_speaker = None
        
        if team.coordination_client:
            await team.coordination_client.notify_speech_complete()
    
    def estimate_speech_duration(self, message: str, agent_type: str) -> float:
        """Estimate speech duration based on message and agent type"""
        # Base duration on message length
        words = len(message.split())
        base_duration = max(3.0, words * 0.5)  # ~0.5 seconds per word, minimum 3s
        
        # Agent-specific adjustments
        adjustments = {
            "websurfer": 1.2,   # Research findings tend to be longer
            "codex": 0.8,       # Code explanations can be concise
            "executor": 0.9,    # Execution results often brief
            "filesurfer": 0.7   # File operations very brief
        }
        
        multiplier = adjustments.get(agent_type, 1.0)
        return min(30.0, base_duration * multiplier)  # Cap at 30 seconds
    
    async def create_coordinated_conversation(self, teams: List[str], 
                                            conversation_id: str = None) -> str:
        """Create a coordinated conversation between multiple teams"""
        conv_id = conversation_id or str(uuid.uuid4())
        
        # Validate teams exist
        valid_teams = [tid for tid in teams if tid in self.teams]
        if not valid_teams:
            raise ValueError("No valid teams specified")
        
        conversation = {
            "id": conv_id,
            "teams": valid_teams,
            "created_at": asyncio.get_event_loop().time(),
            "active": True,
            "turn_order": valid_teams.copy(),
            "current_turn": 0
        }
        
        self.active_conversations[conv_id] = conversation
        logger.info(f"Created coordinated conversation {conv_id} with teams: {valid_teams}")
        
        return conv_id
    
    async def get_next_speaker_in_conversation(self, conversation_id: str) -> Optional[str]:
        """Get the next team that should speak in a coordinated conversation"""
        if conversation_id not in self.active_conversations:
            return None
        
        conv = self.active_conversations[conversation_id]
        if not conv["active"]:
            return None
        
        turn_order = conv["turn_order"]
        current_turn = conv["current_turn"]
        
        next_team_id = turn_order[current_turn % len(turn_order)]
        
        # Advance turn
        conv["current_turn"] = (current_turn + 1) % len(turn_order)
        
        return next_team_id
    
    async def end_conversation(self, conversation_id: str):
        """End a coordinated conversation"""
        if conversation_id in self.active_conversations:
            self.active_conversations[conversation_id]["active"] = False
            logger.info(f"Ended coordinated conversation {conversation_id}")

class AutoAgentVoiceWrapper:
    """Wrapper to add voice coordination to AutoAgent teams"""
    
    def __init__(self, coordinator: AutoAgentVoiceCoordinator, team_id: str):
        self.coordinator = coordinator
        self.team_id = team_id
    
    async def speak_as_agent(self, agent_type: str, message: str, 
                           priority: int = None, wait_for_permission: bool = True) -> bool:
        """Speak as a specific agent type in the team"""
        # Request coordination
        result = await self.coordinator.coordinate_team_speech(
            self.team_id, agent_type, message, priority
        )
        
        if not result.get("granted"):
            logger.warning(f"Speech denied for {agent_type}: {result.get('error', 'Unknown')}")
            return False
        
        if wait_for_permission and not result.get("fallback"):
            # Wait for permission if queued
            team = self.coordinator.teams[self.team_id]
            if team.coordination_client:
                permission = await team.coordination_client.wait_for_permission()
                if not permission:
                    return False
        
        # Here you would integrate with actual AutoAgent voice output
        # For now, we'll simulate with print
        print(f"🤖 [{team.name}:{agent_type}] {message}")
        
        # Simulate speech duration
        estimated_duration = self.coordinator.estimate_speech_duration(message, agent_type)
        await asyncio.sleep(min(2.0, estimated_duration))  # Simulate shorter for demo
        
        # Notify completion
        await self.coordinator.notify_team_speech_complete(self.team_id)
        
        return True

# Integration functions for AutoAgent
async def setup_autoagent_voice_coordination():
    """Setup voice coordination for AutoAgent"""
    coordinator = AutoAgentVoiceCoordinator()
    
    # Example: Register common AutoAgent team configurations
    teams = {
        "research_team": ["websurfer", "filesurfer"],
        "development_team": ["codex", "executor", "filesurfer"], 
        "qa_team": ["executor", "filesurfer", "websurfer"],
        "full_team": ["websurfer", "filesurfer", "codex", "executor"]
    }
    
    registered_teams = {}
    for team_name, agents in teams.items():
        team = await coordinator.register_team(team_name, agents)
        registered_teams[team_name] = team.team_id
    
    return coordinator, registered_teams

async def demo_coordinated_conversation():
    """Demo of coordinated conversation between teams"""
    print("🚀 Starting AutoAgent Voice Coordination Demo")
    
    # Setup coordination
    coordinator, team_ids = await setup_autoagent_voice_coordination()
    
    # Create conversation between research and development teams
    research_team_id = team_ids["research_team"]
    dev_team_id = team_ids["development_team"]
    
    conv_id = await coordinator.create_coordinated_conversation([research_team_id, dev_team_id])
    
    # Create wrappers for easy interaction
    research_wrapper = AutoAgentVoiceWrapper(coordinator, research_team_id)
    dev_wrapper = AutoAgentVoiceWrapper(coordinator, dev_team_id)
    
    print(f"\n📞 Starting coordinated conversation {conv_id}")
    
    # Simulate conversation
    tasks = [
        # Research team starts
        research_wrapper.speak_as_agent("websurfer", "I found some interesting API documentation for the task"),
        research_wrapper.speak_as_agent("filesurfer", "I've located the relevant configuration files"),
        
        # Development team responds
        dev_wrapper.speak_as_agent("codex", "Based on the research, I'll generate the implementation code"),
        dev_wrapper.speak_as_agent("executor", "Running initial tests on the generated code"),
        
        # Back to research
        research_wrapper.speak_as_agent("websurfer", "Found some additional examples that might help"),
        
        # Final development
        dev_wrapper.speak_as_agent("codex", "Incorporating the new examples into the solution"),
        dev_wrapper.speak_as_agent("executor", "All tests passing! Implementation complete")
    ]
    
    # Execute conversation with coordination
    for i, task in enumerate(tasks):
        print(f"\n--- Turn {i+1} ---")
        success = await task
        if not success:
            print("❌ Speech was blocked or failed")
        await asyncio.sleep(0.5)  # Brief pause between turns
    
    # End conversation
    await coordinator.end_conversation(conv_id)
    print(f"\n✅ Coordinated conversation {conv_id} completed")

if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo_coordinated_conversation())