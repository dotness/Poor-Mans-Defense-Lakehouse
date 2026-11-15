from typing import Optional, Any, Union
from typing_extensions import Self
import logging

logger = logging.getLogger(__name__)


class ResourceDoesNotExist(Exception):
    """Raised when a requested domain entity does not exist."""
    pass


class DomainFacade:
    """Coarse-grained Domain-Driven Design Facade.
    
    Encapsulates all domain business logic, data conversions (Storage -> Contract),
    and cross-domain interactions.
    """
    user: Optional[Any] = None
    _session: Optional[Any] = None

    def __init__(self, user: Optional[Any] = None, session: Optional[Any] = None):
        self.user = user
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    @session.setter
    def session(self, value: Any):
        self._session = value

    @classmethod
    async def create(cls, user: Optional[Any] = None) -> Self:
        """Asynchronously create and initialize a facade bound to the given user context."""
        instance = cls(user=user)
        return instance
