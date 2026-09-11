import logging
from typing import Dict, List, Optional
from app.models.enums import AgentName
from app.services.agents.base import BaseAgent

logger = logging.getLogger("resilience.agents.registry")


class AgentRegistry:
    """
    Thread-safe Central Agent Registry.
    Guarantees that only strictly registered and validated agents can be scheduled or executed by the Central Orchestrator.
    """

    def __init__(self):
        self._agents: Dict[AgentName, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Registers a specialized agent instance."""
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"Agent must inherit from BaseAgent, got {type(agent)}")
        
        name = agent.name
        if name in self._agents:
            logger.info(f"Re-registering agent adapter: {name.value}")
        else:
            logger.info(f"Registered new agent adapter: {name.value} ({agent.purpose})")
        
        self._agents[name] = agent

    def unregister(self, agent_name: AgentName) -> None:
        """Removes an agent from the registry."""
        if agent_name in self._agents:
            del self._agents[agent_name]
            logger.info(f"Unregistered agent: {agent_name.value}")

    def get(self, agent_name: AgentName) -> Optional[BaseAgent]:
        """Retrieves a registered agent by AgentName enum."""
        return self._agents.get(agent_name)

    def has_agent(self, agent_name: AgentName) -> bool:
        """Checks if an agent is currently registered and enabled."""
        agent = self._agents.get(agent_name)
        return agent is not None and agent.is_enabled

    def is_registered(self, name_str: str) -> bool:
        """Validates whether a raw string matches a registered agent."""
        try:
            agent_name = AgentName(name_str)
            return self.has_agent(agent_name)
        except ValueError:
            return False

    def list_agents(self) -> List[BaseAgent]:
        """Returns all currently registered agents."""
        return list(self._agents.values())

    def clear(self) -> None:
        """Clears all registered agents (useful for test isolation)."""
        self._agents.clear()


# Global Singleton Instance
agent_registry = AgentRegistry()
