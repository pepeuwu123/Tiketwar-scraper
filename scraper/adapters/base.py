from abc import ABC, abstractmethod
from ..site_state import SiteState

class Adapter(ABC):
    """One file per ticket site. Nothing else in the codebase knows site details."""

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    def poll(self) -> SiteState:
        """Read-only. Must never buy, reserve, or log in."""

    @abstractmethod
    def add_to_cart(self) -> tuple[bool, str]:
        """Best-effort add-to-cart on the operator's OWN account.

        Returns (ok, detail). MUST NOT contain a checkout or payment step.
        """
