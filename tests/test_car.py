import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading

import numpy as np
import pytest
from PySide6.QtCore import QRectF, QSettings
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.ui.car import STATES, CarModel, CarWidget, draw_car
from app.ui.main_window import MainWindow, make_icon
from app.ui.widgets import Bubble, ChatView, SuggestionChips
from tests.test_ui import FakeAutostart, FakeRecorder, FakeSophia, FakeSpeaker, pump


def run(model, seconds, dx=0.0, dt=1 / 60):

    for _ in range(int(seconds / dt)):
        model.step(dt, dx)


def qapp():

    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------
# CarModel
# ---------------------------------------------------------------

def test_unknown_state_or_effect_is_rejected():

    car = CarModel()

    with pytest.raises(ValueError):
        car.set_state("flying")

    with pytest.raises(ValueError):
        car.kick("explode")


def test_a_parked_car_is_calm_and_a_hovered_one_revs_with_lights_on():

    parked, hovered = CarModel(), CarModel()

    hovered.hover = True

    run(parked, 2)
    run(hovered, 2)

    assert parked.light < 0.05 and parked.rev < 0.05
    assert hovered.light > 0.7 and hovered.rev > 0.6
    assert hovered.vibration != 0 or hovered.rev > 0.5


def test_driving_turns_the_wheels_by_the_distance_travelled():

    car = CarModel()

    run(car, 1.0, dx=6.0)           # 6 canvas px per frame for 60 frames

    assert car.wheel_angle == pytest.approx(360 / 26, rel=0.05)


def test_the_car_faces_the_way_it_drives():

    car = CarModel()

    run(car, 0.5, dx=8.0)
    assert car.facing == 1

    run(car, 0.5, dx=-8.0)
    assert car.facing == -1

    # and keeps facing that way when it stops
    run(car, 1.0, dx=0.0)
    assert car.facing == -1


def test_accelerating_lifts_the_nose_and_braking_dips_it():

    car = CarModel()

    for _ in range(12):
        car.step(1 / 60, 12.0)

    assert car.pitch > 0.3

    for _ in range(12):
        car.step(1 / 60, 0.0)

    assert car.pitch < 0.1
    assert car.brake > 0.3


def test_listening_headlights_follow_the_voice():

    quiet, loud = CarModel(), CarModel()

    for car, level in ((quiet, 0.0), (loud, 1.0)):

        car.set_state("listening")
        car.set_level(level)
        run(car, 1.5)

    assert loud.light > quiet.light + 0.2


def test_thinking_blinks_the_hazard_lights():

    car = CarModel()

    car.set_state("thinking")

    seen = set()

    for _ in range(120):

        car.step(1 / 60)
        seen.add(car.hazard)

    assert seen == {True, False}


def test_speaking_lights_the_brake_lamps():

    car = CarModel()

    car.set_state("speaking")
    run(car, 1.0)

    assert car.brake > 0.5


def test_honk_flashes_the_headlights_twice():

    car = CarModel()

    car.kick("honk")

    on_off = []

    for _ in range(60):

        car.step(1 / 60)
        on_off.append(car.light > 0.5)

    changes = sum(1 for a, b in zip(on_off, on_off[1:]) if a != b)

    assert changes >= 3


def test_bounce_settles_burst_sparkles_fade_and_shake_stops():

    car = CarModel(seed=2)

    car.kick("bounce")
    run(car, 0.1)

    assert abs(car.bounce) > 0.3

    run(car, 3)

    assert abs(car.bounce) < 0.05

    car.kick("burst")

    assert len([p for p in car.particles if p.kind == "spark"]) == 20

    run(car, 2)

    assert car.particles == []

    car.kick("shake")
    car.step(0.016)

    assert car.shake_time > 0

    run(car, 1)

    assert car.shake_time == 0


def test_revving_leaves_smoke_that_stays_on_the_road_while_the_car_drives_off():

    car = CarModel(seed=1)

    car.hover = True
    run(car, 1.0)

    smoke = [p for p in car.particles if p.kind == "smoke"]

    assert smoke

    start = smoke[0].x

    car.hover = False

    run(car, 0.3, dx=10.0)       # drive away to the right (facing right)

    survivors = [p for p in car.particles if p.kind == "smoke"]

    # the car moved forward, so old smoke is now further behind it
    assert all(p.x < start for p in survivors if p.age > 0.3) or not survivors


def test_huge_time_steps_do_not_break_the_physics():

    car = CarModel()

    car.kick("bounce")
    car.step(5.0, 1e6)

    assert abs(car.bounce) < 100


# ---------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------

def test_every_state_and_situation_paints():

    qapp()

    for state in STATES:

        car = CarModel(seed=1)

        car.set_state(state)
        car.hover = True
        car.kick("burst")

        run(car, 0.4, dx=-5.0)

        image = QImage(480, 170, QImage.Format_ARGB32)
        image.fill(0)

        painter = QPainter(image)
        draw_car(painter, QRectF(0, 0, 480, 170), car)
        painter.end()

        # something yellow was drawn
        assert any(
            image.pixelColor(x, 100).red() > 200 and image.pixelColor(x, 100).blue() < 80
            for x in range(60, 440, 4)
        )


def test_the_car_is_mirrored_when_facing_left():

    qapp()

    def yellow_columns(facing):

        car = CarModel()
        car.facing = facing

        image = QImage(480, 170, QImage.Format_ARGB32)
        image.fill(0)

        painter = QPainter(image)
        draw_car(painter, QRectF(0, 0, 480, 170), car, with_ground=False)
        painter.end()

        return [
            x for x in range(480)
            if image.pixelColor(x, 85).red() > 200 and image.pixelColor(x, 85).blue() < 80
        ]

    right, left = yellow_columns(1), yellow_columns(-1)

    assert right and left
    assert min(left) == pytest.approx(480 - max(right), abs=6)


def test_the_app_icon_is_a_car():

    qapp()

    icon = make_icon()

    assert not icon.pixmap(64, 64).isNull()


def test_car_widget_paints():

    qapp()

    widget = CarWidget(CarModel(), 300, 106)

    assert not widget.grab().isNull()


# ---------------------------------------------------------------
# Motion in the chat window (kept from the welcome screen work)
# ---------------------------------------------------------------

def test_replies_are_revealed_word_by_word_but_text_is_complete():

    app = qapp()

    chat = ChatView()
    chat.resize(600, 400)

    bubble = chat.add("one two three four five six seven eight", "bot", animate=True, typing=True)

    assert bubble.text() == "one two three four five six seven eight"
    assert len(bubble.label.text()) < len(bubble.text())
    assert pump(app, lambda: bubble.label.text() == bubble.text())


def test_thinking_bubble_has_animated_dots_and_goes_away():

    qapp()

    chat = ChatView()

    chat.show_thinking()
    chat.show_thinking()

    assert len([b for b in chat.widget().findChildren(Bubble) if b.dots is not None]) == 1

    chat.hide_thinking()

    assert not chat.widget().findChildren(Bubble)


def test_suggestion_chips_emit_their_text():

    qapp()

    chips = SuggestionChips(["Open YouTube", "Weather today"])
    chosen = []

    chips.chosen.connect(chosen.append)

    chips.buttons[1].click()

    assert chosen == ["Weather today"]


# ---------------------------------------------------------------
# The chat window
# ---------------------------------------------------------------

class LiveSpeaker(FakeSpeaker):

    def __init__(self):
        super().__init__()
        self.speaking = threading.Event()


def make_window(app, sophia=None, **kwargs):

    window = MainWindow(
        lambda: sophia or FakeSophia(),
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=FakeAutostart(),
        **kwargs,
    )

    assert pump(app, lambda: window.sophia is not None)

    return window


def test_new_users_see_the_welcome_and_it_collapses_on_the_first_message():

    app = qapp()

    window = make_window(app)

    assert not window.hero.isHidden() and window.mini_orb.isHidden()

    window.send("hello")

    assert pump(app, lambda: window.hero.isHidden() and not window.mini_orb.isHidden())


def test_returning_users_skip_the_welcome():

    app = qapp()

    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]

    window = make_window(app, FakeSophia(history))

    assert window.hero.isHidden() and not window.mini_orb.isHidden()


def test_tapping_a_suggestion_sends_it():

    app = qapp()

    sophia = FakeSophia()
    window = make_window(app, sophia)

    window.chips.buttons[0].click()

    assert pump(app, lambda: sophia.received and not window.busy)
    assert sophia.received == ["What can you do?"]


def test_the_car_state_follows_what_sophia_is_doing():

    app = qapp()

    recorder = FakeRecorder(np.ones(16000, dtype="float32"))
    recorder.level = 0.8

    speaker = LiveSpeaker()

    window = make_window(app, recorder_factory=lambda: recorder, speaker=speaker)

    now = 100.0

    assert window._orb_state_at(now) == ("idle", 0.0)

    window.busy = True
    assert window._orb_state_at(now) == ("thinking", 0.0)
    window.busy = False

    window.toggle_listening()
    assert window._orb_state_at(now) == ("listening", 0.8)
    window.recorder = None

    speaker.speaking.set()
    state, level = window._orb_state_at(now)
    assert state == "speaking" and 0.15 <= level <= 1.0
    speaker.speaking.clear()

    window._alert_until = now + 1
    assert window._orb_state_at(now)[0] == "alert"


def test_other_cars_are_told_what_is_happening():

    app = qapp()

    window = make_window(app)

    activity, effects = [], []

    window.activity_listeners.append(lambda state, level: activity.append(state))
    window.effect_listeners.append(effects.append)

    window.busy = True

    assert pump(app, lambda: "thinking" in activity)

    window.busy = False
    window._kick("honk")

    assert effects == ["honk"]


def test_the_car_celebrates_actions_and_shakes_on_errors():

    app = qapp()

    class Doing(FakeSophia):

        def respond(self, text):

            if text == "fail":
                raise RuntimeError("boom")

            self.received.append(text)

            return {"response": "Done", "tool_used": True}

    window = make_window(app, Doing())

    effects = []
    window.effect_listeners.append(effects.append)

    window.send("open youtube")
    assert pump(app, lambda: "burst" in effects)

    window.send("fail")
    assert pump(app, lambda: "shake" in effects)


def test_the_car_keeps_animating_in_the_window():

    app = qapp()

    window = make_window(app)
    window.show()

    before = window.orb_model.time

    pump(app, lambda: False, seconds=0.3)

    assert window.orb_model.time > before
    assert not window.hero_orb.grab().isNull()
