import logging
import os
import sys

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.config.secrets import get_stored_api_key, store_api_key
from app.ui import theme
from app.ui.hotkey import HotkeyFilter
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


def run_gui(voice=True):

    from app.config.settings import Settings
    from app.logging_setup import setup_logging

    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Sophia")
    app.setWindowIcon(make_icon())
    app.setStyleSheet(theme.STYLE)
    app.setQuitOnLastWindowClosed(False)

    if not ensure_api_key():
        return 0

    settings = Settings()

    speaker = recorder_factory = transcriber = None

    if voice:

        from app.voice.listener import Recorder, Transcriber
        from app.voice.speaker import Speaker

        speaker = Speaker()
        recorder_factory = Recorder
        transcriber = Transcriber(settings.whisper_model)

    window = MainWindow(
        create_sophia,
        speaker=speaker,
        recorder_factory=recorder_factory,
        transcriber=transcriber,
    )

    hotkey = HotkeyFilter(window.toggle_visibility)

    label = hotkey.register()

    if label:

        app.installNativeEventFilter(hotkey)

        if window.tray is not None:
            window.tray.setToolTip(f"Sophia ({label})")

    else:
        log.info("No free global hotkey; use the tray icon instead")

    window.show()

    code = app.exec()

    hotkey.unregister()

    return code
