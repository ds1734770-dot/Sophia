import logging
import os
import sys

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.config.secrets import get_stored_api_key, store_api_key
from app.ui import theme
from app.ui.hotkey import HotkeyFilter, parse_hotkey
from app.ui.main_window import MainWindow, make_icon

log = logging.getLogger("sophia.ui")


class ApiKeyDialog(QDialog):
    """
    First-run setup: ask for the Gemini API key.
    """

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Welcome to Sophia")
        self.setWindowIcon(make_icon())
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "<b>Let's connect Sophia to Gemini.</b><br><br>"
            "Create a free key at <i>aistudio.google.com/apikey</i> "
            "and paste it below. It is stored in Windows Credential "
            "Manager, not in a file."
        ))

        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Paste your API key")

        layout.addWidget(self.key)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def value(self):

        return self.key.text().strip()


def ensure_api_key():
    """
    Make sure a key is available (environment, .env or Credential
    Manager); ask for one if not. Returns False if the user declines.
    """

    if os.getenv("GEMINI_API_KEY") or get_stored_api_key():
        return True

    dialog = ApiKeyDialog()

    if dialog.exec() != QDialog.Accepted or not dialog.value():
        return False

    if not store_api_key(dialog.value()):
        # Could not save it; use it for this session
        os.environ["GEMINI_API_KEY"] = dialog.value()

    return True


def create_sophia():
    """
    Builds the assistant (slow: scans installed apps), off the UI thread.
    """

    from app.sophia import Sophia

    return Sophia()


def run_gui(voice=True, minimized=False, orb_mode=True):

    from app.config.settings import Settings
    from app.logging_setup import setup_logging

    setup_logging()

    # so Windows shows Sophia's own (car) icon in the taskbar, not Python's
    try:

        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sophia.Assistant")

    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Sophia")
    app.setWindowIcon(make_icon())
    app.setStyleSheet(theme.STYLE)
    app.setQuitOnLastWindowClosed(False)

    # One Sophia at a time (two orbs would fight over the microphone)
    from PySide6.QtCore import QLockFile

    from app.settings.paths import DATA_DIR

    lock = QLockFile(str(DATA_DIR / "sophia.lock"))
    lock.setStaleLockTime(5000)

    if not lock.tryLock(200):

        log.info("Sophia is already running")

        return 0

    if not ensure_api_key():
        return 0

    settings = Settings()

    speaker = recorder_factory = transcriber = wake_factory = None

    if voice:

        from app.voice.listener import Recorder, Transcriber
        from app.voice.neural_voice import EdgeBackend
        from app.voice.speaker import SapiBackend, Speaker
        from app.voice.wakeword import WakeWordListener

        if settings.neural_voice:

            def backend():
                return EdgeBackend(settings.tts_voice, fallback=SapiBackend())

            speaker = Speaker(backend_factory=backend)

        else:

            speaker = Speaker()

        recorder_factory = Recorder
        transcriber = Transcriber(settings.whisper_model)

        def wake_factory(on_wake):
            return WakeWordListener(
                on_wake,
                word=settings.wake_word,
                threshold=settings.wake_threshold,
            )

    window = MainWindow(
        create_sophia,
        speaker=speaker,
        recorder_factory=recorder_factory,
        transcriber=transcriber,
        wake_factory=wake_factory,
    )

    car = controller = None

    if orb_mode:

        from app.ui.floating_car import CarController, FloatingCar

        from app.ui.sounds import SoundMixer

        mixer = SoundMixer(enabled=settings.sound_effects, volume=settings.sound_volume)

        car = FloatingCar(settings=window.settings, sounds=mixer, width=settings.car_width)
        controller = CarController(window, car)

        if window.tray is not None:

            window.tray.activated.disconnect()
            window.tray.activated.connect(
                lambda reason: car.toggle_visibility()
                if reason == QSystemTrayIcon.Trigger
                else None
            )

            show_hide = QAction("Show / hide the car", window)
            show_hide.triggered.connect(car.toggle_visibility)

            window._tray_menu.insertAction(window._tray_menu.actions()[0], show_hide)

    # In car mode the first hotkey starts a voice request
    hotkey = HotkeyFilter(controller.hotkey if controller else window.toggle_visibility)

    label = hotkey.register()

    if label:

        app.installNativeEventFilter(hotkey)

        if window.tray is not None:
            window.tray.setToolTip(f"Sophia ({label})")

    else:
        log.info("No free global hotkey; use the car's buttons or the tray icon")

    # Show / hide the car: Alt+S by default
    hide_hotkey = None

    if car is not None:

        parsed = parse_hotkey(settings.hide_hotkey)

        if parsed is not None:

            hide_hotkey = HotkeyFilter(car.toggle_visibility, candidates=[parsed], hotkey_id=0x50F2)

            if hide_hotkey.register():

                app.installNativeEventFilter(hide_hotkey)

                log.info("%s shows and hides the car", parsed[2])

            else:

                log.info("%s is taken by another program; use the tray icon", parsed[2])

                hide_hotkey = None

        else:
            log.warning("HIDE_HOTKEY '%s' is not a valid shortcut", settings.hide_hotkey)

    if orb_mode:

        # only the car appears at first, driving in from the screen edge;
        # the chat opens from its Chat button
        car.enter()

    elif not (minimized and window.tray is not None):

        # classic mode; started by Windows at sign-in it stays in the tray
        window.show()

    code = app.exec()

    hotkey.unregister()

    if hide_hotkey is not None:
        hide_hotkey.unregister()

    lock.unlock()

    return code
