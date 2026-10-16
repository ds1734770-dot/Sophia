"""
Skills: common screen tasks done directly, step by step, through the
accessibility tree, with no AI request. They are quicker and more reliable
than asking Gemini at every step, and they work when the Gemini quota is
used up. If a skill cannot finish (the app looks different from what it
expects) it says so, and the general screen agent can take over.

WhatsApp (the desktop app or WhatsApp Web):
    call a contact (voice or video), or send a message
"""

import logging
import re
import time

log = logging.getLogger("sophia.screen")

NOT_SIGNED_IN = re.compile(
    r"qr code|scan (?:the |this )?(?:qr|code)|link a device|use whatsapp on your (?:computer|phone)|"
    r"log in|get started|download whatsapp|link with phone",
    re.IGNORECASE,
)
SEARCH_BOX = re.compile(r"search or start|search chats|^search$|^search\b", re.IGNORECASE)
VOICE_CALL = re.compile(r"voice call|audio call|^call$|^phone call", re.IGNORECASE)
VIDEO_CALL = re.compile(r"video call", re.IGNORECASE)
MESSAGE_BOX = re.compile(r"type a message|^message$", re.IGNORECASE)
CALL_STARTED = re.compile(r"end call|hang up|cancel call|calling|ringing|mute", re.IGNORECASE)

# what a chat in the list can be
CHAT_KINDS = ("ListItem", "Button", "Hyperlink", "TabItem", "TreeItem")


class Stopped(Exception):
    """
    The user pressed stop, a limit was reached, or a forbidden place came up.
    """


def primary_name(name):
    """
    A chat row is read as 'Srino | 10:42 | see you': the name comes first.
    """

    return name.split("|")[0].strip()


class WhatsAppSkill:

    def __init__(
        self,
        observer,
        elements,
        control,
        guard,
        open_app,
        sleep=time.sleep,
        clock=time.monotonic,
        open_wait=15.0,
        ui_wait=6.0,
    ):

        self.observer = observer
        self.elements = elements
        self.control = control
        self.guard = guard
        self.open_app = open_app
        self.sleep = sleep
        self.clock = clock
        self.open_wait = open_wait
        self.ui_wait = ui_wait

    # ------------------------------------------------
    # Public tasks
    # ------------------------------------------------

    def call(self, contact, video=False, dry_run=False):
        """
        (ok, message). dry_run stops just before pressing the call button.
        """

        kind = "video call" if video else "voice call"

        return self._run(f"{kind} {contact} on WhatsApp", lambda: self._call(contact, video, dry_run))

    def message(self, contact, text):

        return self._run(f"message {contact} on WhatsApp", lambda: self._message(contact, text))

    # ------------------------------------------------
    # The steps
    # ------------------------------------------------

    def _run(self, goal, steps):

        self.control.begin(goal)

        try:
            return steps()

        except Stopped as e:

            return False, str(e)

        except Exception as e:

            log.exception("WhatsApp skill failed")

            return False, f"That did not work out ({e})."

        finally:
            self.control.end()

    def _check(self, action=False):
        """
        Before every step: the stop switch, the limits, the forbidden
        places. Only real actions (a click, typing) count toward the limit,
        not each look while waiting for a page.
        """

        reason = self.control.check()

        if reason:
            raise Stopped(reason)

        if action:
            self.control.count_step()

        title, process = self.elements.current_window()

        allowed, why = self.guard.check_window(title, process)

        if not allowed:
            raise Stopped(f"I stopped: {why}")

    def _look(self):

        self._check()

        return self.observer.observe()

    def _wait_for(self, finder, timeout=None):
        """
        Look until finder(observation) finds something (or time runs out).
        """

        deadline = self.clock() + (timeout if timeout is not None else self.ui_wait)

        while True:

            observation = self._look()

            found = finder(observation)

            if found is not None:
                return observation, found

            if self.clock() >= deadline:
                return observation, None

            self.sleep(0.5)

    @staticmethod
    def _first(observation, pattern, kinds=None):

        for element in observation.elements:

            if kinds and element.kind not in kinds:
                continue

            if element.enabled and pattern.search(element.name or ""):
                return element

        return None

    def _open_whatsapp(self):
        """
        WhatsApp in front, signed in, with its chat list showing.
        """

        title, _ = self.elements.current_window()

        if "whatsapp" not in (title or "").lower():

            self._check(action=True)

            ok, message = self.open_app("WhatsApp")

            if not ok:
                raise Stopped(f"I couldn't open WhatsApp ({message}).")

            deadline = self.clock() + self.open_wait

            while self.clock() < deadline:

                title, _ = self.elements.current_window()

                if "whatsapp" in (title or "").lower():
                    break

                self.sleep(0.5)

            else:
                raise Stopped("WhatsApp did not open in time.")

        def ready(observation):

            if self._first(observation, SEARCH_BOX, ("Edit", "ComboBox")):
                return "ready"

            if any(NOT_SIGNED_IN.search(e.name or "") for e in observation.elements):
                return "signed_out"

            return None

        observation, state = self._wait_for(ready, timeout=self.open_wait)

        if state == "signed_out":
            raise Stopped("WhatsApp is not signed in. Scan its QR code with your phone first, then ask me again.")

        if state is None:

            raise Stopped(
                "I couldn't find WhatsApp's search box (it may be showing a call or a chat "
                "full screen). Open the chat list and try again."
            )

        return observation

    def _open_chat(self, contact):

        observation = self._open_whatsapp()

        search = self._first(observation, SEARCH_BOX, ("Edit", "ComboBox"))

        self._check(action=True)

        ok, message = self.elements.type_to(search, contact)

        if not ok:
            raise Stopped(f"I couldn't type in WhatsApp's search ({message}).")

        self.sleep(1.4)

        wanted = contact.strip().lower()

        def matches(observation):

            found = []

            for e in observation.elements:

                if e is search or e.kind not in CHAT_KINDS or not e.enabled:
                    continue

                name = e.name or ""

                if wanted in name.lower() and not (VOICE_CALL.search(name) or VIDEO_CALL.search(name)):
                    found.append(e)

            return found or None

        observation, found = self._wait_for(matches)

        if not found:
            raise Stopped(f"I couldn't find '{contact}' in WhatsApp.")

        # the same chat can show up more than once; different people cannot
        people = {}

        for e in found:
            people.setdefault(primary_name(e.name).lower(), e)

        if len(people) > 1 and wanted not in people:

            names = ", ".join(sorted({primary_name(e.name) for e in found})[:4])

            raise Stopped(f"I found more than one match for '{contact}' ({names}). Which one do you mean?")

        chat = people.get(wanted) or next(iter(people.values()))

        self._check(action=True)

        ok, message = self.elements.press_element(chat)

        if not ok:
            raise Stopped(f"I couldn't open that chat ({message}).")

        self.sleep(1.0)

        return primary_name(chat.name) or contact

    def _call(self, contact, video, dry_run):

        who = self._open_chat(contact)

        pattern = VIDEO_CALL if video else VOICE_CALL

        observation, button = self._wait_for(lambda o: self._first(o, pattern, ("Button", "MenuItem", "Hyperlink")))

        if button is None:

            raise Stopped(
                f"I opened the chat with {who} but couldn't find the "
                f"{'video' if video else 'voice'} call button."
            )

        if dry_run:
            return True, f"Ready to call {who}: found the call button."

        self._check(action=True)

        ok, message = self.elements.press_element(button)

        if not ok:
            raise Stopped(f"I couldn't press the call button ({message}).")

        self.sleep(1.5)

        observation, started = self._wait_for(lambda o: self._first(o, CALL_STARTED), timeout=4.0)

        word = "Video calling" if video else "Calling"

        if started is None:
            return True, f"{word} {who} on WhatsApp: I pressed the call button, but I can't see the call screen to confirm."

        return True, f"{word} {who} on WhatsApp."

    def _message(self, contact, text):

        who = self._open_chat(contact)

        observation, box = self._wait_for(lambda o: self._first(o, MESSAGE_BOX, ("Edit", "ComboBox", "Document")))

        if box is None:
            raise Stopped(f"I opened the chat with {who} but couldn't find the message box.")

        self._check(action=True)

        ok, message = self.elements.type_to(box, text, press_enter=True)

        if not ok:
            raise Stopped(f"I couldn't type the message ({message}).")

        self.sleep(0.8)

        return True, f"Sent {who} a WhatsApp message: {text[:80]}"
