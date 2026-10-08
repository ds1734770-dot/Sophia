import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.orb import PALETTES, OrbModel, OrbWidget
from app.ui.widgets import Bubble, ChatView, SuggestionChips
from tests.test_ui import (
    FakeAutostart,
    FakeRecorder,
    FakeSophia,
    FakeSpeaker,
    pump,
)


def run(model, seconds, dt=1 / 60):

    for _ in range(int(seconds / dt)):
        model.step(dt)


# ---------------------------------------------------------------
# OrbModel
# ---------------------------------------------------------------

def test_colours_ease_toward_the_state_palette():

    model = OrbModel(seed=1)

    model.set_state("listening")
    run(model, 2)

    target = tuple(int(PALETTES["listening"][0][i:i + 2], 16) for i in (1, 3, 5))

    assert all(abs(a - b) < 3 for a, b in zip(model.rgb(1), target))


def test_unknown_state_or_effect_is_rejected():

    model = OrbModel()

    with pytest.raises(ValueError):
        model.set_state("dancing")

    with pytest.raises(ValueError):
        model.kick("explode")


def test_energy_is_higher_when_active_than_idle():

    calm, busy = OrbModel(), OrbModel()

    busy.set_state("thinking")

    run(calm, 2)
    run(busy, 2)

    assert busy.energy > calm.energy + 0.4


def test_voice_level_grows_the_orb_and_spawns_rings():

    quiet, loud = OrbModel(), OrbModel()

    for model, level in ((quiet, 0.0), (loud, 1.0)):

        model.set_state("listening")
        model.set_level(level)
        run(model, 1.5)

    assert loud.radius_scale > quiet.radius_scale + 0.05
    assert loud.rings and not quiet.rings


def test_speaking_pulses_rings_without_any_input_level():

    model = OrbModel()

    model.set_state("speaking")
    run(model, 1.5)

    assert model.rings


def test_bounce_returns_to_rest():

    model = OrbModel()

    model.kick("bounce")
    run(model, 0.15)

    assert abs(model.bounce) > 0.02          # it moved

    run(model, 3)

    assert abs(model.bounce) < 0.01          # and settled


def test_burst_spawns_sparkles_that_fade_away():

    model = OrbModel(seed=3)

    model.kick("burst")

    assert len(model.particles) == 22

    run(model, 2)

    assert model.particles == []


def test_shake_offsets_then_stops():

    model = OrbModel()

    model.kick("shake")
    model.step(0.016)

    assert model.shake_time > 0

    run(model, 1)

    assert model.shake_offset == 0.0


def test_gaze_follows_a_target_and_is_clamped():

    model = OrbModel()

    model.look_at(5, -5)
    run(model, 1)

    assert model.gaze[0] == pytest.approx(1.0, abs=0.02)
    assert model.gaze[1] == pytest.approx(-1.0, abs=0.02)


def test_huge_time_steps_do_not_break_the_physics():

    model = OrbModel()

    model.kick("bounce")
    model.step(5.0)

    assert abs(model.bounce) < 5


# ---------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------

def qapp():

    return QApplication.instance() or QApplication([])


def test_orb_widget_paints_every_state_and_effect():

    qapp()

    model = OrbModel(seed=2)
    orb = OrbWidget(model, 190)

    for state in PALETTES:

        model.set_state(state)
        model.kick("burst")
        run(model, 0.3)

        image = orb.grab()

        assert not image.isNull()


def test_orb_clicks_emit_signals():

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    qapp()

    orb = OrbWidget(OrbModel(), 120)
    seen = []

    orb.clicked.connect(lambda: seen.append("click"))
    orb.double_clicked.connect(lambda: seen.append("double"))

    QTest.mouseClick(orb, Qt.LeftButton, pos=QPoint(60, 60))
    QTest.mouseDClick(orb, Qt.LeftButton, pos=QPoint(60, 60))

    assert "click" in seen and "double" in seen


def test_replies_are_revealed_word_by_word_but_text_is_complete():

    app = qapp()

    chat = ChatView()
    chat.resize(600, 400)

    bubble = chat.add("one two three four five six seven eight", "bot", animate=True, typing=True)

    assert bubble.text() == "one two three four five six seven eight"

    # not all shown at once...
    assert len(bubble.label.text()) < len(bubble.text())

    # ...but it finishes
    assert pump(app, lambda: bubble.label.text() == bubble.text())


def test_short_text_is_shown_immediately():

    qapp()

    bubble = Bubble("", "bot")

    bubble.reveal("hi")

    assert bubble.label.text() == "hi"


def test_thinking_bubble_has_animated_dots_and_goes_away():

    qapp()

    chat = ChatView()

    chat.show_thinking()

    thinking = [b for b in chat.widget().findChildren(Bubble) if b.dots is not None]

    assert len(thinking) == 1

    chat.show_thinking()      # no duplicate

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
# The window
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

    assert not window.hero.isHidden()
    assert window.mini_orb.isHidden()

    window.send("hello")

    assert pump(app, lambda: window.hero.isHidden() and not window.mini_orb.isHidden())


def test_returning_users_skip_the_welcome():

    app = qapp()

    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]

    window = make_window(app, FakeSophia(history))

    assert window.hero.isHidden()
    assert not window.mini_orb.isHidden()


def test_tapping_a_suggestion_sends_it():

    app = qapp()

    sophia = FakeSophia()
    window = make_window(app, sophia)

    window.chips.buttons[0].click()

    assert pump(app, lambda: sophia.received and not window.busy)
    assert sophia.received == ["What can you do?"]


def test_orb_state_follows_what_sophia_is_doing():

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


def test_the_orb_celebrates_actions_and_shakes_on_errors():

    app = qapp()

    class Doing(FakeSophia):

        def respond(self, text):

            if text == "fail":
                raise RuntimeError("boom")

            self.received.append(text)

            return {"response": "Done", "tool_used": True}

    window = make_window(app, Doing())

    window.send("open youtube")
    assert pump(app, lambda: window.orb_model.particles)

    window.send("fail")
    assert pump(app, lambda: window.orb_model.shake_time > 0)


def test_double_clicking_the_orb_stops_speech():

    app = qapp()

    speaker = LiveSpeaker()
    window = make_window(app, speaker=speaker)

    window._on_orb_double_clicked()

    assert speaker.stopped >= 1


def test_the_orb_keeps_animating_and_can_be_painted_in_every_window_state():

    app = qapp()

    window = make_window(app)
    window.show()

    before = window.orb_model.time

    pump(app, lambda: False, seconds=0.3)

    assert window.orb_model.time > before
    assert not window.hero_orb.grab().isNull()
