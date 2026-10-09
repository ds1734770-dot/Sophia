"""
Connecting Sophia to other agents (Claude, ChatGPT, Gemini, ...).
"""

_hub = None


def get_hub():
    """
    The one hub for this process, shared by the tools, the server and
    the interface.
    """

    global _hub

    if _hub is None:

        from app.agents.hub import AgentHub

        _hub = AgentHub()

    return _hub
