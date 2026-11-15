"""
Volume, brightness, power and screenshots (Windows and macOS).
"""

import ctypes
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREVIOUS = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

MEDIA_KEYS = {
    "next": VK_MEDIA_NEXT,
    "previous": VK_MEDIA_PREVIOUS,
    "stop": VK_MEDIA_STOP,
    "play_pause": VK_MEDIA_PLAY_PAUSE,
}
KEYEVENTF_KEYUP = 0x0002

# Each volume key press moves the volume by 2 percent
VOLUME_STEP_PERCENT = 2

POWER_DELAY_SECONDS = 30


class SystemControls:

    def __init__(self, press_key=None, run=None, grab=None, pictures_dir=None, mac=None):

        # macOS uses AppleScript and system keys unless a test injects
        # Windows-style key presses
        self.mac = (sys.platform == "darwin" and press_key is None and run is None) if mac is None else mac

        self._press_key = press_key or self._windows_press_key
        self._run = run or subprocess.run
        self._grab = grab
        self.pictures_dir = Path(
            pictures_dir or Path.home() / "Pictures" / "Sophia"
        )

    @staticmethod
    def _windows_press_key(code):

        user32 = ctypes.windll.user32

        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)

    # ------------------------------------------------
    # Volume
    # ------------------------------------------------

    def change_volume(self, direction, steps=5):
        """
        Raise or lower the volume by `steps` presses (2 percent each).
        """

        if direction not in ("up", "down"):
            return False, "Direction must be 'up' or 'down'."

        steps = max(1, min(int(steps), 50))

        if self.mac:

            from app.computer import macos

            if not macos.change_volume(direction, steps * VOLUME_STEP_PERCENT):
                return False, "I couldn't change the volume."

            return True, (
                f"Volume {direction} by about {steps * VOLUME_STEP_PERCENT}%."
            )

        code = VK_VOLUME_UP if direction == "up" else VK_VOLUME_DOWN

        for _ in range(steps):
            self._press_key(code)

        return True, (
            f"Volume {direction} by about {steps * VOLUME_STEP_PERCENT}%."
        )

    def set_volume(self, level):
        """
        Set the volume to roughly `level` percent (0-100): go to zero,
        then step up.
        """

        level = max(0, min(int(level), 100))

        if self.mac:

            from app.computer import macos

            if not macos.set_volume(level):
                return False, "I couldn't change the volume."

            return True, f"Volume set to {level}%."

        for _ in range(50):
            self._press_key(VK_VOLUME_DOWN)

        for _ in range(round(level / VOLUME_STEP_PERCENT)):
            self._press_key(VK_VOLUME_UP)

        return True, f"Volume set to about {level}%."

    def toggle_mute(self):

        if self.mac:

            from app.computer import macos

            macos.toggle_mute()

            return True, "Toggled mute."

        self._press_key(VK_VOLUME_MUTE)

        return True, "Toggled mute."

    def media(self, action):

        code = MEDIA_KEYS.get(action)

        if code is None:
            return False, f"Unknown media action '{action}'."

        if self.mac:

            from app.computer import macos

            try:
                macos.press_system_key(macos.MEDIA_KEYS[action])

            except Exception as e:
                return False, f"I couldn't send the media key: {e}"

            return True, f"Sent {action.replace('_', '/')} to the media player."

        self._press_key(code)

        return True, f"Sent {action.replace('_', '/')} to the media player."

    # ------------------------------------------------
    # Brightness (laptop screens)
    # ------------------------------------------------

    def set_brightness(self, level):

        level = max(0, min(int(level), 100))

        if self.mac:

            from app.computer import macos

            try:
                macos.set_brightness(level)

            except Exception:
                return False, "I couldn't change the brightness."

            return True, f"Brightness set to about {level}%."

        script = (
            "(Get-WmiObject -Namespace root/WMI "
            "-Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{level})"
        )

        result = self._run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            return False, (
                "I couldn't change the brightness. This only works on "
                "built-in laptop screens."
            )

        return True, f"Brightness set to {level}%."

    # ------------------------------------------------
    # Power
    # ------------------------------------------------

    def power(self, action):
        """
        shutdown / restart start a countdown that can be cancelled;
        sleep happens at once.
        """

        if self.mac:
            return self._mac_power(action)

        if action == "cancel":

            self._run(["shutdown", "/a"], capture_output=True, text=True)

            return True, "Cancelled the pending shutdown or restart."

        if action in ("shutdown", "restart"):

            flag = "/s" if action == "shutdown" else "/r"

            self._run(
                ["shutdown", flag, "/t", str(POWER_DELAY_SECONDS)],
                capture_output=True,
                text=True,
            )

            return True, (
                f"Your computer will {action} in {POWER_DELAY_SECONDS} "
                "seconds. Say 'cancel shutdown' to stop it."
            )

        if action == "sleep":

            self._run(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                capture_output=True,
                text=True,
            )

            return True, "Going to sleep..."

        return False, f"Unknown power action '{action}'."

    @staticmethod
    def _mac_power(action):

        from app.computer import macos

        if action == "cancel":

            if macos.POWER.cancel():
                return True, "Cancelled the pending shutdown or restart."

            return True, "There was no shutdown or restart waiting."

        if action in ("shutdown", "restart"):

            macos.POWER.schedule(action, POWER_DELAY_SECONDS)

            return True, (
                f"Your Mac will {action} in {POWER_DELAY_SECONDS} "
                "seconds. Say 'cancel shutdown' to stop it."
            )

        if action == "sleep":

            macos.sleep_now()

            return True, "Going to sleep..."

        return False, f"Unknown power action '{action}'."

    # ------------------------------------------------
    # Screenshot
    # ------------------------------------------------

    def capture_png(self, max_width=1600):
        """
        The screen as PNG bytes (downscaled), kept in memory only.
        """

        import io

        grab = self._grab

        if grab is None:
            from PIL import ImageGrab
            grab = ImageGrab.grab

        image = grab()

        if image.width > max_width:

            height = round(image.height * max_width / image.width)

            image = image.resize((max_width, height))

        buffer = io.BytesIO()

        image.save(buffer, format="PNG")

        return buffer.getvalue()

    def screenshot(self):
        """
        Save a screenshot to Pictures/Sophia. Returns (success, path or
        error).
        """

        try:

            grab = self._grab

            if grab is None:
                from PIL import ImageGrab
                grab = ImageGrab.grab

            image = grab()

            self.pictures_dir.mkdir(parents=True, exist_ok=True)

            path = self.pictures_dir / (
                f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
            )

            image.save(path)

            return True, str(path)

        except Exception as e:

            return False, f"I couldn't take a screenshot: {e}"
