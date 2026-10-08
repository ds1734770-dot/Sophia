import contextlib


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

    def maybe_summarize(self, memory, summary, lock=None):
        """
        Returns True if the history was compacted.

        The (slow) summary request runs without `lock`, so a new message
        can arrive meanwhile; it is kept when the history is swapped.
        """

        lock = lock or contextlib.nullcontext()

        with lock:

            history = memory.get_history()

            if len(history) <= self.trigger:
                return False

            old = history[:-self.keep]
            summary_so_far = summary.get()

        try:
            text = self.summarize(summary_so_far, old)

        except Exception:
            return False

        if not text or not text.strip():
            return False

        with lock:

            current = memory.get_history()

            # messages added while the summary was being written
            if current[:len(history)] != history:
                return False

            summary.set(text.strip())
            memory.load(list(history[-self.keep:]) + list(current[len(history):]))

        return True
