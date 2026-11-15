import abc
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseStep(abc.ABC):
    """Abstract unit of work or activity in an operation workflow."""

    def __init__(self, name: Optional[str] = None):
        self.name = name or self.__class__.__name__

    @abc.abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Executes the step logic, reading from and writing to context."""
        pass


class BaseOperation(abc.ABC):
    """Abstract orchestrator for multi-step domain workflows."""

    def __init__(self, name: Optional[str] = None):
        self.name = name or self.__class__.__name__
        self.steps: list[BaseStep] = []

    def add_step(self, step: BaseStep) -> "BaseOperation":
        self.steps.append(step)
        return self

    @abc.abstractmethod
    async def run(self, **kwargs) -> Dict[str, Any]:
        """Runs the operation workflow."""
        pass
