from abc import ABC, abstractmethod
from typing import List
from app.models.enums import AgentName
from app.models.agent import AgentContext, AgentResult


class BaseAgent(ABC):
    """
    Abstract contract that every specialized agent in Phase 5 must implement.
    Guarantees strict input/output boundaries, dependency declarations, and deterministic execution interfaces.
    """

    @property
    @abstractmethod
    def name(self) -> AgentName:
        """Unique identifying name for the agent in the registry."""
        pass

    @property
    @abstractmethod
    def purpose(self) -> str:
        """Human-readable description of agent responsibility and capabilities."""
        pass

    @property
    @abstractmethod
    def required_inputs(self) -> List[str]:
        """List of essential context fields required for execution."""
        pass

    @property
    def dependencies(self) -> List[AgentName]:
        """List of preceding agent dependencies required before this agent executes."""
        return []

    @property
    def is_enabled(self) -> bool:
        """Whether the agent is currently active and eligible for execution."""
        return True

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Executes the agent's specific domain logic.
        Must catch internal errors, produce structured outputs, and never raise unhandled exceptions.
        """
        pass
