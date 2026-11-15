import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from app.ui.floating_car import (
    DEFAULT_WIDTH,
    SIZES,
    CarController,
    Layout,
    FloatingCar,
    SpeechCard,
    clamp_to_screens,
    screen_rects,
)
LAY = Layout(DEFAULT_WIDTH)

from app.ui.hotkey import MOD_ALT, MOD_CONTROL, parse_hotkey
from app.ui.main_window import MainWindow
from tests.test_ui import (

    FakeAutostart,
    FakeRecorder,
    FakeSophia,
    FakeSpeaker,
    FakeTranscriber,
    pump,
)

import sys

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows behaviour")
mac_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS behaviour")


def qapp():

    return QApplication.instance() or QApplication([])


def fresh_settings():

    return QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)


class FakeMouse:

    def __init__(self, x=-5000, y=-5000):
        self.pos = QPoint(x, y)

    def __call__(self):
        return self.pos


def make_car(mouse=None, settings=None):

    qapp()

    car = FloatingCar(settings=settings or fresh_settings(), cursor=mouse or FakeMouse())

    car.show()

    return car


def mouse_event(kind, point, car, button=Qt.LeftButton):

    local = QPointF(point)

    return QMouseEvent(
        kind, local, QPointF(car.mapToGlobal(point)), button, button, Qt.NoModifier
    )


def press_release(car, point):

    car.mousePressEvent(mouse_event(QEvent.MouseButtonPress, point, car))
    car.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, point, car))


def hover(app, car, mouse):

    mouse.pos = car.mapToGlobal(LAY.car_hit.center())

    assert pump(app, lambda: car.interact > 0.9)


# ---------------------------------------------------------------
# Shortcut parsing
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("alt+s", (MOD_ALT, ord("S"), "Alt+S")),
        ("Ctrl+Alt+O", (MOD_ALT | MOD_CONTROL, ord("O"), "Ctrl+Alt+O")),
        ("alt+space", (MOD_ALT, 0x20, "Alt+SPACE")),
        ("alt+f9", (MOD_ALT, 0x78, "Alt+F9")),
        ("alt+7", (MOD_ALT, ord("7"), "Alt+7")),
    ],
)
@windows_only
def test_shortcuts_are_parsed(text, expected):

    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["s", "alt", "alt+", "banana+s", "alt+ab", "alt+f13", ""])
def test_bad_shortcuts_are_rejected(text):

    assert parse_hotkey(text) is None


# ---------------------------------------------------------------
# Window basics
# ---------------------------------------------------------------

def test_it_is_a_small_always_on_top_window_that_does_not_steal_focus():

    car = make_car()

    flags = car.windowFlags()

    assert flags & Qt.WindowStaysOnTopHint
    assert flags & Qt.FramelessWindowHint
    assert flags & Qt.WindowDoesNotAcceptFocus
    assert car.size() == QSize(LAY.width, LAY.height)


def test_the_car_is_kept_on_screen():

    qapp()

    area = screen_rects()[0]
    size = QSize(LAY.width, LAY.height)

    far = clamp_to_screens(QPoint(area.right() + 9000, area.bottom() + 9000), size)

    assert area.contains(far) and area.contains(far + QPoint(LAY.width, LAY.height))
    assert clamp_to_screens(QPoint(-9000, -9000), size).x() >= area.left()


def test_the_position_is_remembered_between_runs():

    qapp()

    settings = fresh_settings()

    car = make_car(settings=settings)

    area = screen_rects()[0]

    car.move(area.left() + 40, area.top() + 30)
    car.save_position()

    again = FloatingCar(settings=settings, cursor=FakeMouse())

    assert (again.x(), again.y()) == (car.x(), car.y())


def test_reset_position_goes_back_to_the_corner():

    car = make_car()

    car.move(10, 10)
    car.reset_position()

    area = screen_rects()[0]

    assert car.x() > area.center().x() - 300


# ---------------------------------------------------------------
# Dragging like a normal element
# ---------------------------------------------------------------

def test_dragging_moves_the_car_and_the_car_drives_while_moving():

    app = qapp()

    car = make_car()

    car.move(100, 100)

    start = LAY.car_hit.center()

    car.mousePressEvent(mouse_event(QEvent.MouseButtonPress, start, car))

    assert car.dragging

    car.mouseMoveEvent(mouse_event(QEvent.MouseMove, start, car))

    # pull it 200 px to the left
    moved = QMouseEvent(
        QEvent.MouseMove, QPointF(start), QPointF(car.mapToGlobal(start) + QPoint(-200, 30)),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )

    car.mouseMoveEvent(moved)

    assert car.x() == 100 - 200 or car.x() == clamp_to_screens(QPoint(-100, 130), car.size()).x()

    assert pump(app, lambda: car.model.moving)

    pump(app, lambda: False, seconds=0.15)

    assert car.model.facing == -1


def test_dropping_remembers_where_and_parks_facing_the_middle():

    qapp()

    settings = fresh_settings()
    car = make_car(settings=settings)

    area = screen_rects()[0]

    car.move(area.left() + 30, area.top() + 40)

    point = LAY.car_hit.center()

    car.mousePressEvent(mouse_event(QEvent.MouseButtonPress, point, car))
    car.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, point, car))

    assert not car.dragging

    saved = settings.value("car_pos")

    assert [int(saved[0]), int(saved[1])] == [car.x(), car.y()]

    # on the left half of the screen it faces right, toward the middle
    assert car.model.facing == 1


def test_clicking_the_car_itself_does_nothing_else():

    car = make_car()

    seen = []

    for signal in (car.voice_requested, car.chat_requested, car.hide_requested):
        signal.connect(lambda: seen.append(1))

    press_release(car, LAY.car_hit.center())

    assert seen == []


# ---------------------------------------------------------------
# Hover buttons
# ---------------------------------------------------------------

def test_no_buttons_until_the_mouse_is_on_the_car():

    app = qapp()

    mouse = FakeMouse()
    car = make_car(mouse)

    pump(app, lambda: False, seconds=0.2)

    assert car.interact < 0.05
    assert not car.model.hover


def test_hovering_lights_the_car_and_brings_out_the_buttons():

    app = qapp()

    mouse = FakeMouse()
    car = make_car(mouse)

    hover(app, car, mouse)

    assert car.model.hover
    assert pump(app, lambda: car.model.light > 0.6, seconds=2)


def test_the_buttons_fade_after_the_mouse_leaves_with_a_short_linger():

    app = qapp()

    mouse = FakeMouse()
    car = make_car(mouse)

    hover(app, car, mouse)

    mouse.pos = QPoint(-5000, -5000)

    pump(app, lambda: False, seconds=0.25)

    assert car.interact > 0.5          # still lingering

    assert pump(app, lambda: car.interact < 0.05, seconds=3)


def test_the_three_buttons_send_voice_chat_and_hide():

    app = qapp()

    mouse = FakeMouse()
    car = make_car(mouse)

    seen = []
    car.voice_requested.connect(lambda: seen.append("voice"))
    car.chat_requested.connect(lambda: seen.append("chat"))
    car.hide_requested.connect(lambda: seen.append("hide"))

    hover(app, car, mouse)

    for index in range(3):
        press_release(car, car.button_rect(index).center())

    assert seen == ["voice", "chat", "hide"]


def test_buttons_do_not_react_before_they_are_out():

    qapp()

    car = make_car(FakeMouse())

    seen = []
    car.voice_requested.connect(lambda: seen.append(1))

    press_release(car, car.button_rect(0).center())

    assert seen == []


def test_the_voice_button_shows_when_listening():

    qapp()

    car = make_car()

    car.set_activity("listening", 0.5)

    assert car.listening

    car.set_activity("idle", 0.0)

    assert not car.listening

    car.set_activity("flying", 0.0)         # unknown states are ignored

    assert car.model.state == "idle"


def test_the_buttons_area_paints():

    app = qapp()

    mouse = FakeMouse()
    car = make_car(mouse)

    hover(app, car, mouse)

    assert not car.grab().isNull()
    assert LAY.button_y > LAY.car_hit.bottom() - 40


# ---------------------------------------------------------------
# Entry, hide and exit animations
# ---------------------------------------------------------------

def test_entering_drives_in_from_the_edge_and_parks_with_a_honk():

    app = qapp()

    car = make_car()

    rest = car.rest_pos

    car.enter()

    # starts off screen
    area = screen_rects()[0]

    assert car.x() < area.left() or car.x() > area.right() - 5
    assert car.driving

    assert pump(app, lambda: not car.driving, seconds=4)
    assert (car.x(), car.y()) == (rest.x(), rest.y())
    assert car.model.flash_time > 0 or car.model.light > 0

    assert not car.hidden


def test_the_wheels_turn_and_the_car_faces_forward_while_driving_in():

    app = qapp()

    car = make_car()

    car.enter()

    angle = car.model.wheel_angle

    pump(app, lambda: False, seconds=0.4)

    assert abs(car.model.wheel_angle - angle) > 1.0
    assert car.model.facing in (1, -1)


def test_hiding_drives_off_screen_and_showing_brings_it_back():

    app = qapp()

    car = make_car()

    rest = car.rest_pos

    car.hide_away()

    assert car.hidden

    assert pump(app, lambda: not car.isVisible(), seconds=4)

    car.toggle_visibility()

    assert pump(app, lambda: car.isVisible() and not car.driving, seconds=4)
    assert (car.x(), car.y()) == (rest.x(), rest.y())
    assert not car.hidden


def test_toggle_hides_a_visible_car_and_ignores_double_hide():

    app = qapp()

    car = make_car()

    car.toggle_visibility()

    assert car.hidden

    car.hide_away()           # already on its way: nothing breaks

    assert pump(app, lambda: not car.isVisible(), seconds=4)


def test_exit_revs_then_drives_away_and_calls_done():

    app = qapp()

    car = make_car()

    done = []

    car.exit_and_quit(lambda: done.append(1))

    assert car.model.hover
    assert car.model.flash_time > 0

    assert pump(app, lambda: done == [1], seconds=5)

    area = screen_rects()[0]

    assert car.x() > area.right() - 5


def test_dragging_is_ignored_while_the_car_is_driving():

    qapp()

    car = make_car()

    car.enter()

    car.mousePressEvent(mouse_event(QEvent.MouseButtonPress, LAY.car_hit.center(), car))

    assert not car.dragging


# ---------------------------------------------------------------
# Text card
# ---------------------------------------------------------------

def test_the_card_shows_above_the_car_and_fades_away():

    app = qapp()

    car = make_car()

    car.move(*(screen_rects()[0].center().toTuple()))
    car.say("Opened YouTube.")

    card = car.card

    assert card.isVisible() and card.label.text() == "Opened YouTube."
    assert not card.buttons.isVisible()
    assert card.y() < car.y() + LAY.car_hit.top()

    card.fade_out()

    assert pump(app, lambda: not card.isVisible(), seconds=2)


def test_a_question_keeps_the_card_with_buttons_until_answered():

    app = qapp()

    card = SpeechCard()
    car = make_car()

    answers = []
    card.answered.connect(answers.append)

    anchor = car.frameGeometry()

    card.show_message("Close Notepad?", anchor, confirm=True, allow_always=True)

    pump(app, lambda: False, seconds=0.3)

    assert card.isVisible()
    assert not card._hide_timer.isActive()
    assert not card._always.isHidden()

    card._answer("yes")

    assert answers == ["yes"] and not card.isVisible()


def test_always_is_only_offered_when_allowed():

    qapp()

    card = SpeechCard()
    car = make_car()

    card.show_message("Delete it?", car.frameGeometry(), confirm=True, allow_always=False)

    assert card._always.isHidden()


def test_no_card_pops_up_while_dragging_or_driving():

    car = make_car()

    car.dragging = True
    car.say("Hello")

    assert not car.card.isVisible()

    car.dragging = False
    car.driving = True
    car.say("Hello")

    assert not car.card.isVisible()


# ---------------------------------------------------------------
# With the chat window
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

    car = FloatingCar(settings=fresh_settings(), cursor=FakeMouse())
    controller = CarController(window, car)

    car.show()

    return window, car, controller


def test_only_the_car_is_visible_at_first():

    app = qapp()

    window, car, _ = make_pair(app)

    assert car.isVisible() and not window.isVisible()


def test_the_car_mirrors_what_sophia_is_doing():

    app = qapp()

    window, car, _ = make_pair(app)

    window.busy = True

    assert pump(app, lambda: car.model.state == "thinking")

    window.busy = False

    assert pump(app, lambda: car.model.state == "idle")

    window._kick("honk")

    assert car.model.flash_time > 0


def test_the_voice_button_listens_and_the_reply_is_shown_and_spoken():

    app = qapp()

    recorder = FakeRecorder(np.ones(16000, dtype="float32"))
    speaker = FakeSpeaker()

    window, car, _ = make_pair(app, recorder=recorder, speaker=speaker)

    car.voice_requested.emit()

    assert pump(app, lambda: recorder.started)
    assert pump(app, lambda: car.model.state == "listening")

    recorder.finished.set()

    assert pump(app, lambda: car.card.isVisible() and car.card.label.text() == "Opening Notepad.")
    assert pump(app, lambda: speaker.said == ["Opening Notepad."])
    assert not window.isVisible()


def test_confirmations_appear_on_the_card_with_buttons_that_answer():

    app = qapp()

    sophia = FakeSophia()
    window, car, _ = make_pair(app, sophia)

    window.send("close notepad")

    assert pump(app, lambda: car.card.isVisible() and not car.card.buttons.isHidden())

    pump(app, lambda: not window.busy)

    car.card._answer("yes")

    assert pump(app, lambda: "yes" in sophia.received)


def test_hints_show_when_voice_cannot_start():

    app = qapp()

    window, car, _ = make_pair(app)

    window.start_voice_turn()

    assert car.card.isVisible() and "Voice isn't available" in car.card.label.text()


def test_the_chat_button_opens_the_chat_beside_the_car():

    app = qapp()

    window, car, _ = make_pair(app)

    car.card.show_message("something", car.frameGeometry())

    car.chat_requested.emit()

    assert pump(app, lambda: window.isVisible())
    assert not car.card.isVisible()


def test_with_the_chat_open_replies_are_not_duplicated_on_the_card():

    app = qapp()

    window, car, controller = make_pair(app)

    controller.open_chat()

    assert pump(app, lambda: window.isVisible())

    window.send("open notepad")

    assert pump(app, lambda: not window.busy)
    assert not car.card.isVisible()


def test_closing_the_chat_keeps_the_car():

    app = qapp()

    window, car, controller = make_pair(app)

    controller.open_chat()
    pump(app, lambda: window.isVisible())

    window.close()

    assert not window.isVisible() and car.isVisible()


def test_the_hide_button_hides_the_car_and_the_menu_settings_are_shared():

    app = qapp()

    window, car, _ = make_pair(app)

    assert car.voice_replies_action is window.voice_toggle_action()
    assert car.hands_free_action is window.hands_free_action

    car.hide_requested.emit()

    assert car.hidden


def test_quitting_from_the_menu_drives_away_then_quits(monkeypatch):

    app = qapp()

    window, car, controller = make_pair(app)

    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: None))

    car.quit_requested.emit()

    assert car.driving or car.model.hover

    assert pump(app, lambda: window._quitting, seconds=5)


# ---------------------------------------------------------------
# Size
# ---------------------------------------------------------------

def test_the_default_car_is_small_and_the_buttons_are_tiny():

    car = make_car()

    assert car.lay.width == DEFAULT_WIDTH == 130
    assert car.size() == QSize(car.lay.width, car.lay.height)
    assert car.lay.height < 120
    assert 15 <= car.lay.button <= 22


def test_layout_scales_everything_from_the_width():

    small, big = Layout(100), Layout(250)

    assert small.height < big.height
    assert small.button < big.button
    assert small.car_rect.width() == 100 and big.car_rect.width() == 250
    assert Layout(5).width == 70 and Layout(5000).width == 300      # limits


def test_buttons_fit_inside_the_window_at_every_size():

    for width in list(SIZES.values()) + [70, 300]:

        lay = Layout(width)

        car_window = QRect(0, 0, lay.width, lay.height)

        for i in range(3):

            total = 3 * lay.button + 2 * lay.gap
            x = (lay.width - total) // 2 + i * (lay.button + lay.gap)

            assert car_window.contains(QRect(x, lay.button_y, lay.button, lay.button))


def test_resizing_keeps_the_centre_remembers_and_updates_the_layout():

    qapp()

    settings = fresh_settings()
    car = make_car(settings=settings)

    area = screen_rects()[0]
    car.move(area.center().x() - 100, area.center().y() - 60)

    before = car.frameGeometry().center()

    car.set_width(SIZES["Large"])

    assert car.lay.width == 250 and car.width() == 250
    assert abs(car.frameGeometry().center().x() - before.x()) <= 2
    assert int(settings.value("car_width")) == 250

    again = FloatingCar(settings=settings, cursor=FakeMouse())

    assert again.lay.width == 250


def test_buttons_still_work_after_resizing():

    app = qapp()

    mouse = FakeMouse()
    car = make_car(mouse)

    car.set_width(SIZES["Medium"])

    seen = []
    car.chat_requested.connect(lambda: seen.append("chat"))

    mouse.pos = car.mapToGlobal(QPoint(car.lay.width // 2, 60))

    assert pump(app, lambda: car.interact > 0.9)

    press_release(car, car.button_rect(1).center())

    assert seen == ["chat"]


# ---------------------------------------------------------------
# Sounds
# ---------------------------------------------------------------

class FakeSounds:

    def __init__(self):
        self.played = []
        self.enabled = True

    def play(self, name):
        self.played.append(name)

    def set_enabled(self, on):
        self.enabled = on


def make_car_with_sounds(mouse=None):

    qapp()

    sounds = FakeSounds()

    car = FloatingCar(settings=fresh_settings(), cursor=mouse or FakeMouse(), sounds=sounds)
    car.show()

    return car, sounds


def test_entering_plays_the_engine_then_a_honk_on_arrival():

    app = qapp()

    car, sounds = make_car_with_sounds()

    car.enter()

    assert sounds.played[0] == "entry"

    assert pump(app, lambda: "honk" in sounds.played, seconds=4)


def test_hovering_is_silent_but_still_wipes():

    app = qapp()

    mouse = FakeMouse()
    car, sounds = make_car_with_sounds(mouse)

    mouse.pos = car.mapToGlobal(QPoint(car.lay.width // 2, 50))

    assert pump(app, lambda: car.interact > 0.9)

    pump(app, lambda: False, seconds=0.3)

    assert sounds.played == []
    assert car.model.wipe_time > 0 or car.model.wiper > 0


def test_buttons_click_and_hiding_and_exiting_have_sounds():

    app = qapp()

    mouse = FakeMouse()
    car, sounds = make_car_with_sounds(mouse)

    mouse.pos = car.mapToGlobal(QPoint(car.lay.width // 2, 50))
    assert pump(app, lambda: car.interact > 0.9)

    press_release(car, car.button_rect(2).center())

    assert "click" in sounds.played

    car.hide_away()

    assert "hide" in sounds.played

    other, other_sounds = make_car_with_sounds()

    other.exit_and_quit(lambda: None)

    assert "exit" in other_sounds.played


def test_listening_and_thinking_and_success_have_sounds():

    qapp()

    car, sounds = make_car_with_sounds()

    car.set_activity("listening", 0.2)
    car.set_activity("listening", 0.4)           # only the start chimes

    car.set_activity("thinking", 0.0)

    car.on_effect("burst")

    assert sounds.played == ["listen", "wiper", "success"]


def test_the_sound_switch_in_the_menu_mutes_and_is_remembered():

    qapp()

    settings = fresh_settings()
    sounds = FakeSounds()

    car = FloatingCar(settings=settings, cursor=FakeMouse(), sounds=sounds)

    assert car.sound_action.isChecked() and sounds.enabled

    car.sound_action.setChecked(False)

    assert not sounds.enabled
    assert settings.value("sounds", True, type=bool) is False

    again = FloatingCar(settings=settings, cursor=FakeMouse(), sounds=FakeSounds())

    assert not again.sound_action.isChecked()


def test_a_broken_sound_device_never_breaks_the_car():

    app = qapp()

    class Broken:

        def play(self, name):
            raise OSError("no audio device")

        def set_enabled(self, on):
            pass

    car = FloatingCar(settings=fresh_settings(), cursor=FakeMouse(), sounds=Broken())
    car.show()

    car.enter()

    assert pump(app, lambda: not car.driving, seconds=4)


@mac_only
def test_mac_shortcuts_are_parsed():

    from app.ui import mac_hotkey

    assert parse_hotkey("ctrl+alt+h") == (
        mac_hotkey.CONTROL_KEY | mac_hotkey.OPTION_KEY, mac_hotkey.KEY_CODES["h"], "Ctrl+Option+H"
    )
    assert parse_hotkey("cmd+shift+space")[2] == "Cmd+Shift+SPACE"
    assert parse_hotkey("alt+f13") is None
