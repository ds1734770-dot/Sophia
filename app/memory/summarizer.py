class Summarizer:
    """
    Keeps long conversations affordable: once the history grows past
    `trigger` messages, the older ones are folded into a running summary
    and only the most recent `keep` stay verbatim.

    `summarize` is a callable (previous_summary, messages) -> str that
    may raise; a failure just leaves the history as it is.
    """

    def __init__(self, summarize, trigger=30, keep=10):

        self.summarize = summarize
        self.trigger = trigger
        self.keep = keep

    def maybe_summarize(self, memory, summary):
        """
        Returns True if the history was compacted.
        """

        history = memory.get_history()

        if len(history) <= self.trigger:
            return False

        old = history[:-self.keep]
        recent = history[-self.keep:]

        try:
            text = self.summarize(summary.get(), old)

        except Exception:
            return False

        if not text or not text.strip():
            return False

        summary.set(text.strip())
        memory.load(list(recent))

        return True
