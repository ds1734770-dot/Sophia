import re

from app.brain.command_parser.action_parser import ActionParser


class EntityParser:
    """
    Extract the thing a command is about ("open my downloads folder"
    -> "downloads"). Works on whole words only.
    """

    NOISE = {"my", "the", "a", "an", "up", "for", "me", "please"}

    SUFFIXES = {"app", "application", "program", "folder", "software"}

    def parse(self, text):

        words = ActionParser.clean(text).split()

        # Drop the action verb
        words = words[1:]

        words = [w for w in words if w not in self.NOISE]

        while words and words[-1] in self.SUFFIXES and len(words) > 1:
            words.pop()

        return " ".join(words).strip()
