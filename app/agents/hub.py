"""
The agent hub: what Claude, ChatGPT, Gemini and other agents are doing
right now, as tasks with a status. Tools report in (through hooks, the
notify command or the local server); Sophia shows it.

Statuses: running, needs_input, done, failed.
"""

import re
import threading
import time
from dataclasses import dataclass, field

STATUSES = ("running", "needs_input", "done", "failed")

STATUS_WORDS = {
    "running": "running", "start": "running", "started": "running",
    "working": "running", "busy": "running", "thinking": "running",
    "needs_input": "needs_input", "needs-input": "needs_input",
    "needs_info": "needs_input", "input": "needs_input", "waiting": "needs_input",
    "ask": "needs_input", "question": "needs_input", "blocked": "needs_input",
    "permission": "needs_input", "needs_you": "needs_input",
    "done": "done", "finished": "done", "complete": "done", "completed": "done",
    "success": "done", "stop": "done", "ok": "done",
    "failed": "failed", "fail": "failed", "error": "failed",
}

# Brand-like colours for the car and the cards (colours only, no logos)
AGENT_STYLES = {
    "claude": ("Claude", "#d97757"),
    "chatgpt": ("ChatGPT", "#10a37f"),
    "gemini": ("Gemini", "#5b8def"),
    "freebuff": ("Freebuff", "#b45cff"),
}

AGENT_ALIASES = {
    "claude code": "claude", "claude-code": "claude", "claudecode": "claude",
    "claude.ai": "claude", "anthropic": "claude",
    "openai": "chatgpt", "gpt": "chatgpt", "codex": "chatgpt", "chatgpt.com": "chatgpt",
    "google": "gemini", "gemini cli": "gemini", "gemini-cli": "gemini", "bard": "gemini",
    "codebuff": "freebuff",
}

# Other agents get one of these, always the same one for the same name
SPARE_COLORS = ["#ff7eb6", "#4dd0e1", "#ffd54f", "#9ccc65", "#ba68c8", "#ff8a65"]

DEFAULT_COLOR = "#8a93a6"

MAX_TEXT = 400
MAX_TASKS = 60
FINISHED_KEEP_SECONDS = 6 * 3600


def clean(text, limit=MAX_TEXT):

    text = re.sub(r"\s+", " ", str(text or "")).strip()

    return text if len(text) <= limit else text[: limit - 1] + "…"


def normalize_agent(name):
    """
    (id, display name, colour) for whatever the agent calls itself.
    """

    raw = clean(name, 40).lower() or "agent"

    key = AGENT_ALIASES.get(raw, raw)

    if key in AGENT_STYLES:

        display, color = AGENT_STYLES[key]

        # keep what the tool says it is (Claude Code vs claude.ai)
        label = clean(name, 40) if raw in AGENT_ALIASES and key == "claude" else display

        return key, label or display, color

    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "agent"

    color = SPARE_COLORS[sum(map(ord, slug)) % len(SPARE_COLORS)]

    return slug, clean(name, 40) or "Agent", color


def normalize_status(status):

    return STATUS_WORDS.get(str(status or "").strip().lower().replace(" ", "_"))


@dataclass
class Task:
    id: str
    agent: str
    label: str
    color: str
    title: str = ""
    status: str = "running"
    message: str = ""
    question: str = ""
    answer: str = ""
    project: str = ""
    started: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    # how many agents are waiting right now for the user's reply
    waiting: int = 0

    def elapsed(self, now=None):

        return max(0.0, (now or time.time()) - self.started)


class AgentHub:

    def __init__(self, clock=time.time):

        self.clock = clock

        self.tasks = {}
        self.listeners = []

        self._lock = threading.RLock()
        self._answered = threading.Condition(self._lock)

    # ------------------------------------------------
    # Reports from agents
    # ------------------------------------------------

    def update(self, event):
        """
        Apply a report: {agent, status, title?, message?, question?,
        task?, project?}. Returns the task, or None if it is not valid.
        """

        if not isinstance(event, dict):
            return None

        status = normalize_status(event.get("status"))

        if status is None:
            return None

        agent, label, color = normalize_agent(event.get("agent"))

        project = clean(event.get("project"), 60)

        task_id = clean(event.get("task"), 80) or f"{agent}:{project or 'main'}"

        with self._lock:

            task = self.tasks.get(task_id)

            fresh = task is None or (
                status == "running" and task.status in ("done", "failed")
            )

            if fresh:

                task = Task(
                    id=task_id, agent=agent, label=label, color=color,
                    project=project, started=self.clock(),
                )

                self.tasks[task_id] = task

            previous = None if fresh else task.status

            task.status = status
            task.updated = self.clock()

            title = clean(event.get("title"), 120)

            if title:
                task.title = title

            message = clean(event.get("message"))

            if message:
                task.message = message

            if status == "needs_input":

                task.question = clean(event.get("question") or message or task.title)
                task.answer = ""

            elif status in ("done", "failed"):
                task.question = ""

            self._prune()

        kind = "started" if fresh else "updated"

        self._emit(kind, task, previous)

        return task

    def answer(self, task_id, text):
        """
        The user's reply to a question. Returns True if it was recorded.
        """

        text = clean(text, 2000)

        with self._lock:

            task = self.tasks.get(task_id)

            if task is None or not text:
                return False

            task.answer = text
            task.updated = self.clock()

            self._answered.notify_all()

        self._emit("answered", task, task.status)

        return True

    def wait_answer(self, task_id, timeout):
        """
        Wait for the user's reply to a task's question (None on timeout).
        """

        deadline = time.monotonic() + timeout

        with self._answered:

            task = self.tasks.get(task_id)

            if task is not None:
                task.waiting += 1

            try:

                while True:

                    task = self.tasks.get(task_id)

                    if task is not None and task.answer:

                        answer, task.answer = task.answer, ""

                        return answer

                    left = deadline - time.monotonic()

                    if left <= 0:
                        return None

                    self._answered.wait(min(left, 1.0))

            finally:

                task = self.tasks.get(task_id)

                if task is not None:
                    task.waiting = max(0, task.waiting - 1)

    def is_waiting(self, task_id):
        """
        Is an agent waiting right now to receive the user's reply?
        """

        with self._lock:

            task = self.tasks.get(task_id)

            return task is not None and task.waiting > 0

    def dismiss(self, task_id):

        with self._lock:
            task = self.tasks.pop(task_id, None)

        if task is not None:
            self._emit("dismissed", task, task.status)

    # ------------------------------------------------
    # What is going on
    # ------------------------------------------------

    def all(self):
        """
        Newest first.
        """

        with self._lock:
            return sorted(self.tasks.values(), key=lambda t: -t.updated)

    def with_status(self, *statuses):

        return [t for t in self.all() if t.status in statuses]

    def lead(self):
        """
        The task that deserves the car's attention: one that needs the
        user first, then the most recent running one.
        """

        waiting = self.with_status("needs_input")

        if waiting:
            return waiting[0]

        running = self.with_status("running")

        return running[0] if running else None

    def summary(self):
        """
        A sentence per task, for Sophia to read out or answer with.
        """

        tasks = self.all()

        if not tasks:
            return "No agents have reported any tasks."

        names = {
            "running": "working on", "needs_input": "waiting for you on",
            "done": "finished", "failed": "failed on",
        }

        lines = []

        for t in tasks[:10]:

            what = t.title or t.project or "a task"

            line = f"{t.label} is {names[t.status]} {what}"

            if t.status == "needs_input" and t.question:
                line += f": {t.question}"

            elif t.status == "running":
                line += f" ({t.elapsed(self.clock()) / 60:.0f} min)"

            lines.append(line + ".")

        return "\n".join(lines)

    # ------------------------------------------------

    def _prune(self):

        now = self.clock()

        for task_id, task in list(self.tasks.items()):

            if task.status in ("done", "failed") and now - task.updated > FINISHED_KEEP_SECONDS:
                del self.tasks[task_id]

        if len(self.tasks) > MAX_TASKS:

            oldest = sorted(self.tasks.values(), key=lambda t: t.updated)

            for task in oldest[: len(self.tasks) - MAX_TASKS]:
                del self.tasks[task.id]

    def _emit(self, kind, task, previous):

        for listener in list(self.listeners):

            try:
                listener(kind, task, previous)

            except Exception:

                import logging

                logging.getLogger("sophia.agents").debug(
                    "Agent listener failed", exc_info=True
                )
