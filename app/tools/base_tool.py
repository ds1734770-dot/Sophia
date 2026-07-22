from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    Base class for all Sophia tools.
    """

    name = "base"

    description = ""

    @abstractmethod
    def run(self, **kwargs):
        """
        Execute the tool.

        Returns:
            Any
        """
        pass