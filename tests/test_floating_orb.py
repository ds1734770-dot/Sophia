import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading

import numpy as np
from PySide6.QtCore import QPoint, QSettings, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.floating_orb import (
    FloatingOrb,
    GestureDetector,
    OrbController,
    SpeechBubble,
    clamp_to_screens,
    screen_rects,
)
from app.ui.main_window import MainWindow
from app.ui.orb import OrbModel
from tests.test_ui import (
    FakeAutostart,
    FakeRecorder,
    FakeSophia,
    FakeSpeaker,
    FakeTranscriber,
    pump,
)


def qapp():

    return QApplication.instance() or QApplication([])


def fresh_settings():

    return QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)


# ---------------------------------------------------------------
# Gesture detection
# ---------------------------------------------------------------

def collect(detector):

    seen = []
    detector.gesture.connect(seen.append)

    return seen


def test_one_click_is_reported_after_the_pause():

    app = qapp()

    detector = GestureDetector(interval_ms=40)
    seen = collect(detector)

    detector.register_click()

    assert seen == []                        # still waiting for a second click
    assert pump(app, lambda: seen == [1])


def test_two_clicks_make_a_double():

    app = qapp()

    detector = GestureDetector(interval_ms=60)
    seen = collect(detector)

    detector.register_click()
    detector.register_click()

    assert pump(app, lambda: seen == [2])


def test_three_clicks_fire_at_once_and_more_still_count_as_three():

    detector = GestureDetector(interval_ms=5000)
    seen = collect(detector)

    for _ in range(3):
        detector.register_click()

    assert seen == [3]

    for _ in range(5):
        detector.register_click()

    assert seen == [3, 3]


def test_cancel_forgets_pending_clicks():

    app = qapp()

    detector = GestureDetector(interval_ms=30)
    seen = collect(detector)

    detector.register_click()
    detector.cancel()

    pump(app, lambda: False, seconds=0.2)

    assert seen == []


# ---------------------------------------------------------------
# Keeping the orb on screen
# ---------------------------------------------------------------

def test_the_orb_is_pulled_back_onto_the_screen():

    qapp()

    area = screen_rects()[0]
    size = QSize(130, 130)

    far = clamp_to_screens(QPoint(area.right() + 5000, area.bottom() + 5000), size)

    assert area.contains(far) and area.contains(far + QPoint(size.width(), size.height()))

    negative = clamp_to_screens(QPoint(-9000, -9000), size)

    assert negative.x() >= area.left() and negative.y() >= area.top()


def test_a_position_that_is_already_fine_is_unchanged():

    qapp()

    area = screen_rects()[0]
    point = QPoint(area.left() + 50, area.top() + 60)

    assert clamp_to_screens(point, QSize(130, 130)) == point


# ---------------------------------------------------------------
# The floating orb
# ---------------------------------------------------------------

class FakeMouse:

    def __init__(self, x=100, y=100):
        self.pos = QPoint(x, y)

    def __call__(self):
        return self.pos


def make_orb(mouse=None, gesture_ms=40, settings=None):

    qapp()

    return FloatingOrb(
        OrbModel(),
        settings=settings or fresh_settings(),
        gesture_ms=gesture_ms,
        cursor=mouse or FakeMouse(),
    )


def test_it_is_a_small_always_on_top_window_that_does_not_steal_focus():

    orb = make_orb()

    flags = orb.windowFlags()

    assert flags & Qt.WindowStaysOnTopHint
    assert flags & Qt.FramelessWindowHint
    assert flags & Qt.WindowDoesNotAcceptFocus
    assert orb.size() == QSize(130, 130)


def test_click_gestures_become_requests():

    app = qapp()

    orb = make_orb()

    seen = []
    orb.listen_requested.connect(lambda: seen.append("listen"))
    orb.chat_requested.connect(lambda: seen.append("chat"))

    orb._on_click()

    assert pump(app, lambda: seen == ["listen"])

    for _ in range(3):
        orb._on_click()

    assert seen == ["listen", "chat"]


def test_double_click_starts_move_mode_and_the_orb_follows_the_pointer():

    app = qapp()

    mouse = FakeMouse(300, 300)
    orb = make_orb(mouse)

    orb._on_click()
    orb._on_click()

    assert pump(app, lambda: orb.moving)
    assert orb.model.moving

    area = screen_rects()[0]

    mouse.pos = QPoint(area.left() + 400, area.top() + 250)

    assert pump(app, lambda: orb.frameGeometry().center().x() in range(mouse.pos.x() - 3, mouse.pos.x() + 4))


def test_the_next_click_drops_the_orb_and_remembers_where():

    app = qapp()

    settings = fresh_settings()
    mouse = FakeMouse(200, 200)

    orb = make_orb(mouse, settings=settings)

    orb.start_move_mode()
    mouse.pos = QPoint(333, 222)
    pump(app, lambda: False, seconds=0.1)

    orb._on_click()                      # drops

    assert not orb.moving and not orb.model.moving

    saved = settings.value("orb_pos")

    assert [int(saved[0]), int(saved[1])] == [orb.x(), orb.y()]

    # a new orb starts where the old one was left
    again = make_orb(settings=settings)

    assert (again.x(), again.y()) == (orb.x(), orb.y())


def test_moving_does_not_trigger_voice_or_chat():

    app = qapp()

    orb = make_orb()

    seen = []
    orb.listen_requested.connect(lambda: seen.append("listen"))
    orb.chat_requested.connect(lambda: seen.append("chat"))

    orb.start_move_mode()
    orb._on_click()

    pump(app, lambda: False, seconds=0.2)

    assert seen == []


def test_reset_position_goes_back_to_the_corner():

    orb = make_orb()

    orb.move(10, 10)
    orb.reset_position()

    area = screen_rects()[0]

    assert orb.x() > area.center().x() - 200


# ---------------------------------------------------------------
# Speech bubble
# ---------------------------------------------------------------

def test_the_bubble_shows_text_beside_the_orb_and_fades_away():

    app = qapp()

    orb = make_orb()
    orb.show()

    bubble = orb.bubble

    orb.say("Opened YouTube.")

    assert bubble.isVisible()
    assert bubble.label.text() == "Opened YouTube."
    assert not bubble.buttons.isVisible()

    # beside the orb, not on top of it
    assert not bubble.frameGeometry().intersects(orb.frameGeometry())

    bubble.fade_out()

    assert pump(app, lambda: not bubble.isVisible(), seconds=2)


def test_a_question_keeps_the_bubble_and_its_buttons_until_answered():

    app = qapp()

    bubble = SpeechBubble()
    answers = []
    bubble.answered.connect(answers.append)

    orb = make_orb()
    orb.show()

    bubble.show_message("Close Notepad?", orb.frameGeometry(), confirm=True, allow_always=True)

    pump(app, lambda: False, seconds=0.3)

    assert bubble.isVisible()
    assert not bubble._hide_timer.isActive()
    assert not bubble._always.isHidden()

    bubble.buttons.findChildren(type(bubble._always))[0].click()      # Yes

    assert answers == ["yes"]
    assert not bubble.isVisible()


def test_always_is_only_offered_when_allowed():

    qapp()

    bubble = SpeechBubble()
    orb = make_orb()

    bubble.show_message("Delete it?", orb.frameGeometry(), confirm=True, allow_always=False)

    assert bubble._always.isHidden()


def test_clicking_the_orb_hides_the_bubble():

    orb = make_orb()
    orb.show()

    orb.say("Hello")
    orb._on_click()

    assert not orb.bubble.isVisible()


def test_no_bubble_pops_up_while_the_orb_is_being_moved():

    orb = make_orb()
    orb.show()

    orb.start_move_mode()
    orb.say("Hello")

    assert not orb.bubble.isVisible()


# ---------------------------------------------------------------
# The orb and the chat window together
# ---------------------------------------------------------------

def make_pair(app, sophia=None, recorder=None, speaker=None):

    window = MainWindow(
        lambda: sophia or FakeSophia(replies={"open notepad": "Opening Notepad."}),
        speaker=speaker or FakeSpeaker(),
        recorder_factory=(lambda: recorder) if recorder else None,
        transcriber=FakeTranscriber("open notepad"),
        settings=fresh_settings(),
        use_tray=False,
        autostart=FakeAutostart(),
    )

    assert pump(app, lambda: window.sophia is not None)

    orb = FloatingOrb(window.orb_model, settings=fresh_settings(), gesture_ms=30, cursor=FakeMouse())
    controller = OrbController(window, orb)

    orb.show()

    return window, orb, controller


def test_only_the_orb_is_visible_at_first():

    app = qapp()

    window, orb, _ = make_pair(app)

    assert orb.isVisible() and not window.isVisible()


def test_a_click_listens_and_the_reply_appears_in_the_bubble_and_is_spoken():

    app = qapp()

    recorder = FakeRecorder(np.ones(16000, dtype="float32"))

    class Speaker(FakeSpeaker):
        speaking = threading.Event()

    speaker = Speaker()

    window, orb, _ = make_pair(app, recorder=recorder, speaker=speaker)

    orb._on_click()

    assert pump(app, lambda: recorder.started)
    assert window._orb_state_at(0.0)[0] == "listening"

    recorder.finished.set()

    assert pump(app, lambda: orb.bubble.isVisible() and orb.bubble.label.text() == "Opening Notepad.")

    # spoken even though "spoken replies" is off, because it was a voice request
    assert pump(app, lambda: speaker.said == ["Opening Notepad."])
    assert not window.isVisible()


def test_a_second_click_while_listening_stops_early():

    app = qapp()

    recorder = FakeRecorder(np.ones(16000, dtype="float32"))

    window, orb, _ = make_pair(app, recorder=recorder)

    window.start_voice_turn()
    assert pump(app, lambda: recorder.started)

    window.start_voice_turn()

    assert window.recorder is None


def test_confirmations_appear_in_the_bubble_with_buttons_that_answer():

    app = qapp()

    sophia = FakeSophia()
    window, orb, _ = make_pair(app, sophia)

    window.send("close notepad")

    assert pump(app, lambda: orb.bubble.isVisible() and not orb.bubble.buttons.isHidden())

    window.chat.hide_thinking()

    pump(app, lambda: not window.busy)

    orb.bubble._answer("yes")

    assert pump(app, lambda: "yes" in sophia.received)


def test_hints_show_when_voice_cannot_start():

    app = qapp()

    window, orb, _ = make_pair(app)       # no recorder

    window.start_voice_turn()

    assert orb.bubble.isVisible()
    assert "Voice isn't available" in orb.bubble.label.text()


def test_triple_click_opens_the_chat_beside_the_orb_and_hides_the_bubble():

    app = qapp()

    window, orb, _ = make_pair(app)

    orb.say("something")

    for _ in range(3):
        orb._on_click()

    assert pump(app, lambda: window.isVisible())
    assert not orb.bubble.isVisible()

    assert not window.frameGeometry().intersects(orb.frameGeometry()) or window.width() > 400


def test_with_the_chat_open_replies_are_not_duplicated_in_the_bubble():

    app = qapp()

    window, orb, controller = make_pair(app)

    controller.open_chat()
    assert pump(app, lambda: window.isVisible())

    window.send("open notepad")
    assert pump(app, lambda: not window.busy)

    assert not orb.bubble.isVisible()


def test_closing_the_chat_keeps_the_orb():

    app = qapp()

    window, orb, controller = make_pair(app)

    controller.open_chat()
    pump(app, lambda: window.isVisible())

    window.close()

    assert not window.isVisible()
    assert orb.isVisible()


def test_the_orb_menu_shares_the_voice_and_hands_free_settings():

    app = qapp()

    window, orb, _ = make_pair(app)

    assert orb.voice_replies_action is window.voice_toggle_action()
    assert orb.hands_free_action is window.hands_free_action

    orb.voice_replies_action.setChecked(True)

    assert window.voice_toggle.isChecked()

    window.voice_toggle.setChecked(False)

    assert not orb.voice_replies_action.isChecked()


def test_the_orb_is_animated_with_the_window_even_when_the_chat_is_hidden():

    app = qapp()

    window, orb, _ = make_pair(app)

    before = window.orb_model.time

    pump(app, lambda: False, seconds=0.3)

    assert window.orb_model.time > before
    assert not orb.orb.grab().isNull()


def test_clicking_the_bubble_opens_the_chat():

    app = qapp()

    window, orb, _ = make_pair(app)

    orb.say("Open me")
    QTest.mouseClick(orb.bubble, Qt.LeftButton)

    assert pump(app, lambda: window.isVisible())
