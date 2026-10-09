import re

WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "half an": 0.5,
}

NUMBER = r"(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|half an)"

# minutes in each unit
UNIT_MINUTES = {"second": 1 / 60, "sec": 1 / 60, "minute": 1, "min": 1, "hour": 60, "hr": 60}


def number(text):

    text = text.strip()

    if text in WORD_NUMBERS:
        return WORD_NUMBERS[text]

    return float(text)


class QuickEngine:
    """
    Exact, unambiguous requests answered at once by running the matching
    tool directly, with no AI request (a Gemini round trip takes several
    seconds and uses quota). The tool still goes through the registry,
    so the safety tiers apply exactly as when Gemini asks for it.

    Only whole sentences match, so anything open-ended goes to Gemini.
    """

    def __init__(self):

        self.rules = [
            (re.compile(r"^(?:set |change |turn )?(?:the )?(?:volume|sound) (?:to |at )?(\d{1,3})(?: ?%| percent)?$"),
             lambda m: ("set_volume", {"level": min(100, int(m[1]))})),
            (re.compile(r"^(?:turn |set )?(?:the )?(?:volume|sound) (up|down)$|^(louder|quieter|softer)$"),
             lambda m: ("set_volume", {"change": {"louder": "up", "quieter": "down", "softer": "down"}.get(m[2]) or m[1]})),
            (re.compile(r"^(?:un)?mute(?: the)?(?: sound| volume| audio| speakers?)?$"),
             lambda m: ("set_volume", {"change": "mute"})),
            (re.compile(r"^(?:pause|resume|play|stop)(?: the)?(?: music| song| video| media| playback| track)?$"),
             lambda m: ("media_control", {"action": "stop" if m.string.startswith("stop") else "play_pause"})),
            (re.compile(r"^(?:next|skip)(?: the)?(?: song| track| video)?$"),
             lambda m: ("media_control", {"action": "next"})),
            (re.compile(r"^(?:previous|last|go back a)(?: song| track)$|^previous$"),
             lambda m: ("media_control", {"action": "previous"})),
            (re.compile(rf"^(?:set |start )?(?:a |an )?timer (?:for |of )?{NUMBER} ?(second|sec|minute|min|hour|hr)s?$"),
             lambda m: ("set_timer", {"minutes": number(m[1]) * UNIT_MINUTES[m[2]]})),
            (re.compile(rf"^(?:set |start )?(?:a |an )?{NUMBER} ?(second|sec|minute|min|hour|hr)s? timer$"),
             lambda m: ("set_timer", {"minutes": number(m[1]) * UNIT_MINUTES[m[2]]})),
            (re.compile(r"^(?:take |grab )?(?:a )?screenshot$"),
             lambda m: ("take_screenshot", {})),
            (re.compile(r"^(?:system|pc|computer) (?:status|health|stats)$|^how (?:is|'s) my (?:pc|computer)(?: doing)?$|^(?:battery|battery level|how much battery(?: do i have| is left| left)?)$|^(?:cpu|memory|ram) usage$"),
             lambda m: ("system_status", {})),
            (re.compile(r"^(?:am i online|is (?:the )?internet (?:working|down|connected)|network status|(?:check )?(?:my )?(?:internet|wifi|wi-fi)(?: connection| status)?)$"),
             lambda m: ("network_status", {})),
            (re.compile(r"^(?:what(?:'s| is) )?(?:the )?weather(?: like)?(?: today| now| right now)?(?: (?:in|at|for) (.+))?$"),
             lambda m: ("get_weather", {"city": m[1]} if m[1] else {})),
            (re.compile(r"^(?:what(?:'s| is) )?(?:the )?(?:latest )?(?:news|headlines)(?: today)?(?: (?:about|on) (.+))?$|^what(?:'s| is) in the news$"),
             lambda m: ("news_headlines", {"topic": m[1]} if m[1] else {})),
            (re.compile(r"^(?:define|definition of|meaning of) ([a-z'-]{2,30})$|^what does ([a-z'-]{2,30}) mean$"),
             lambda m: ("define_word", {"word": m[1] or m[2]})),
            (re.compile(r"^(?:generate|make|create|give me)(?: me)? a (?:strong |random |secure )?password$"),
             lambda m: ("generate_password", {})),
            (re.compile(r"^(?:switch to |turn on |enable |go )?(dark|light) (?:mode|theme)$"),
             lambda m: ("set_windows_theme", {"mode": m[1]})),
            (re.compile(r"^(?:what(?:'s| is) )?(?:my )?(?:recent files|recently opened(?: files)?)$|^what did i (?:open|work on) (?:last|recently)$"),
             lambda m: ("recent_files", {})),
            (re.compile(r"^(?:show |list )?(?:my )?(?:to-?dos?|to do list|todo list|tasks)$|^what(?:'s| is) on my (?:to-?do|to do) list$"),
             lambda m: ("list_todos", {})),
            (re.compile(r"^(?:what(?:'s| is| are) )?(?:my )?agents?(?: status| doing| up to| tasks?| updates?)?(?: doing| up to)?$|^(?:what(?:'s| is) )?(?:claude|chatgpt|gemini|freebuff) (?:status|doing|up to|working on|tasks?|updates?)$|^(?:any )?(?:updates?|news) (?:from|on) (?:my )?(?:agents?|claude|chatgpt|gemini|freebuff)$"),
             lambda m: ("agent_status", {})),
            (re.compile(r"^(?:connect|set ?up|link) (?:my )?(?:agents?|claude|claude code|chatgpt|gemini|freebuff)(?: to sophia)?$"),
             lambda m: ("connect_agents", {})),
            (re.compile(r"^(?:show |list )?(?:my )?notes$"),
             lambda m: ("list_notes", {})),
            (re.compile(r"^(?:show |list )?(?:my )?timers$|^how much time is left$"),
             lambda m: ("list_timers", {})),
        ]

        self.convert = re.compile(
            r"^(?:convert |how much is |what is |what's )?(-?\d+(?:\.\d+)?) ?([a-z/°]+?) (?:to|in|into) ([a-z/°]+)$"
        )

    @staticmethod
    def _text(command):

        text = command.lower().strip()
        text = re.sub(r"^(?:hey |hi |ok |okay )?(?:sophia[ ,]+)?(?:please |can you |could you )?", "", text)
        text = re.sub(r"[?!.,]+$", "", text)
        text = re.sub(r"\s+(?:please|for me|now)$", "", text)

        return re.sub(r"\s+", " ", text).strip()

    def match(self, command):
        """
        (tool name, arguments) if the whole sentence is a quick command.
        """

        text = self._text(command)

        if not text or len(text) > 80:
            return None

        for pattern, build in self.rules:

            found = pattern.match(text)

            if found:

                try:
                    return build(found)

                except (KeyError, ValueError, TypeError):
                    return None

        found = self.convert.match(text)

        if found:

            value, source, target = float(found[1]), found[2], found[3]

            if re.fullmatch(r"[a-z]{3}", source) and re.fullmatch(r"[a-z]{3}", target) and source != target:

                from app.tools.utility_tools import convert_units_value

                # "5 min to hr" is a unit; "100 usd to inr" is money
                if not convert_units_value(1, source, target)[0]:
                    return ("convert_currency", {"amount": value, "from_currency": source, "to_currency": target})

            return ("convert_units", {"value": value, "from_unit": source, "to_unit": target})

        return None

    def execute(self, command, context, offline=False):

        registry = getattr(context, "registry", None)

        if registry is None:
            return {"handled": False, "response": None}

        quick = self.match(command)

        if quick is None:
            return {"handled": False, "response": None}

        name, args = quick

        if name not in registry.tools:
            return {"handled": False, "response": None}

        result = registry.execute(name, args, context)

        # a lookup that did not apply (for example "5 apples to pears")
        # is left for Gemini to make sense of
        if not result.ok and name in ("convert_units", "convert_currency", "define_word"):
            return {"handled": False, "response": None}

        return {"handled": True, "response": result.message}
