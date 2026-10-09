"""
Tools for the agents Sophia keeps an eye on (Claude, ChatGPT, Gemini...).
"""

from app.tools.registry import Risk, Tool

STRING = {"type": "string"}


def register_agent_tools(registry, hub, data_dir):

    def agent_status(context):

        return True, hub.summary()

    registry.register(Tool(
        name="agent_status",
        description=(
            "What the user's other agents (Claude, ChatGPT, Gemini, "
            "Freebuff...) are doing right now: working, waiting for the "
            "user, finished or failed."
        ),
        handler=agent_status,
    ))

    def reply_to_agent(context, answer, agent=None):

        waiting = hub.with_status("needs_input")

        if agent:
            waiting = [t for t in waiting if agent.lower() in (t.label + " " + t.agent).lower()]

        if not waiting:
            return False, "No agent is waiting for an answer."

        if len(waiting) > 1 and not agent:

            names = ", ".join(t.label for t in waiting)

            return False, f"More than one agent is waiting ({names}). Which one?"

        task = waiting[0]

        delivered = hub.is_waiting(task.id)

        hub.answer(task.id, answer)

        if delivered:
            return True, f"Sent your answer to {task.label}."

        try:

            from app.tools.personal_tools import default_clipboard

            default_clipboard().set(answer)

        except Exception:
            pass

        return True, (
            f"{task.label} is not listening for replies from me, so I copied "
            "your answer: paste it into its window."
        )

    registry.register(Tool(
        name="reply_to_agent",
        description=(
            "Answer a question that one of the user's other agents is "
            "waiting on, using the user's own words."
        ),
        parameters={"answer": STRING, "agent": STRING},
        required=["answer"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to tell {a.get('agent') or 'the waiting agent'}: \"{a['answer'][:120]}\"",
        handler=reply_to_agent,
    ))

    def connect_agents(context):

        from app.agents.setup import instructions

        return True, instructions(data_dir)

    registry.register(Tool(
        name="connect_agents",
        description="Explain how to connect Claude Code, Gemini, Freebuff and other agents so Sophia can show their progress.",
        handler=connect_agents,
    ))
