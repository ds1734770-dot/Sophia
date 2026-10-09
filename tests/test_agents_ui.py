import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor

from app.agents.hub import AgentHub
from app.tools.registry import Risk, ToolRegistry
from app.tools.agent_tools import register_agent_tools
from app.ui.agents_panel import AgentsPanel, is_yes_no
from app.ui.car import CarModel, tc
from app.ui.floating_car import CarController, FloatingCar
from app.ui.main_window import MainWindow
from tests.test_floating_car import FakeMouse, FakeSounds, fresh_settings, qapp
from tests.test_ui import FakeAutostart, FakeSophia, FakeSpeaker, pump


def make_all(sounds=None):

    app = qapp()

    hub = AgentHub()

    window = MainWindow(
        lambda: FakeSophia(),
        speaker=FakeSpeaker(),
        settings=fresh_settings(),
        use_tray=False,
        autostart=FakeAutostart(),
        agent_hub=hub,
    )

    assert pump(app, lambda: window.sophia is not None)

    car = FloatingCar(settings=fresh_settings(), cursor=FakeMouse(), sounds=sounds)
    controller = CarController(window, car)

    car.show()

    return app, hub, window, car, controller


def report(app, hub, **event):

    hub.update(event)

    app.processEvents()


# ---------------------------------------------------------------
# The car's paint
# ---------------------------------------------------------------

def step(model, seconds):

    for _ in range(int(seconds / 0.05)):
        model.step(0.05)


def test_the_car_fades_to_an_agents_colour_and_back():

    model = CarModel(seed=1)

    assert tc(model, QColor("#ffcf10")).name() == "#ffcf10"      # untouched yellow

    model.set_tint("#10a37f")
    step(model, 2)

    green = tc(model, QColor("#ffcf10"))

    assert green.green() > green.red()                            # now green

    model.set_tint(None)
    step(model, 3)

    assert tc(model, QColor("#ffcf10")).name() == "#ffcf10"       # back to yellow


def test_shading_is_kept_when_the_car_changes_colour():

    model = CarModel(seed=1)
    model.set_tint("#5b8def")
    step(model, 2)

    light = tc(model, QColor("#ffe86a"))
    dark = tc(model, QColor("#c98800"))

    assert light.lightnessF() > dark.lightnessF()


def test_hazards_blink_while_an_agent_waits():

    model = CarModel(seed=1)

    assert not any((setattr(model, "time", t / 10) or model.hazard) for t in range(0, 40))

    model.attention = True

    assert any((setattr(model, "time", t / 10) or model.hazard) for t in range(0, 40))


# ---------------------------------------------------------------
# Car + agents
# ---------------------------------------------------------------

def test_the_car_takes_the_colour_of_the_working_agent():

    app, hub, window, car, controller = make_all()

    report(app, hub, agent="claude", status="running", title="Fix login", task="a")

    assert car.model._tint_goal.name() == "#d97757"
    assert window.orb_model._tint_goal.name() == "#d97757"

    report(app, hub, agent="claude", status="done", task="a")

    assert car.model._tint_goal is None


def test_other_working_agents_show_as_dots():

    app, hub, window, car, controller = make_all()

    report(app, hub, agent="chatgpt", status="running", task="a")
    report(app, hub, agent="gemini", status="running", task="b")
    report(app, hub, agent="claude", status="running", task="c")

    lead = hub.lead()

    assert len(car.model.pips) == 2 and lead.color not in car.model.pips


def test_a_question_comes_first_with_hazards_a_honk_and_a_card():

    sounds = FakeSounds()

    app, hub, window, car, controller = make_all(sounds)

    report(app, hub, agent="chatgpt", status="running", task="a")
    report(app, hub, agent="claude", status="needs_input", task="b", question="Should I delete the old files?")

    assert car.model._tint_goal.name() == "#d97757"                # claude outranks the running one
    assert car.model.attention
    assert "honk" in sounds.played
    assert car.card.isVisible() and "Claude" in car.card.label.text()
    assert not car.card.buttons.isHidden()                         # a yes / no question


def test_a_hidden_car_comes_out_for_a_question():

    app, hub, window, car, controller = make_all()

    car.hidden = True
    car.hide()

    report(app, hub, agent="gemini", status="needs_input", task="g", question="Which file?")

    assert not car.hidden


def test_yes_on_the_card_answers_the_agent_not_sophia():

    app, hub, window, car, controller = make_all()

    report(app, hub, agent="claude", status="needs_input", task="b", question="Shall I continue?")

    car.card._answer("yes")

    assert hub.tasks["b"].answer == "yes"
    assert window.sophia.received == []                            # nothing went to Sophia's chat


def test_finishing_celebrates_and_failing_shudders():

    sounds = FakeSounds()

    app, hub, window, car, controller = make_all(sounds)

    report(app, hub, agent="gemini", status="running", task="g", title="Report")
    report(app, hub, agent="gemini", status="done", task="g")

    assert "success" in sounds.played and "finished" in car.card.label.text()

    report(app, hub, agent="freebuff", status="failed", task="f", title="Build")

    assert car.model.shake_time > 0 and "problem" in car.card.label.text()


# ---------------------------------------------------------------
# The panel in the chat window
# ---------------------------------------------------------------

def test_yes_no_detection():

    assert is_yes_no("Should I also update the docs?")
    assert is_yes_no("I found two copies. Do you want me to remove one?")
    assert not is_yes_no("Which database should I use?")
    assert not is_yes_no("Do you want A or B?")
    assert not is_yes_no("")


def test_the_panel_lists_tasks_by_urgency_and_hides_when_empty():

    app = qapp()

    hub = AgentHub()
    panel = AgentsPanel(hub)

    panel.refresh()

    assert panel.isHidden()

    hub.update({"agent": "chatgpt", "status": "done", "task": "d"})
    hub.update({"agent": "gemini", "status": "running", "task": "r", "title": "Report"})
    hub.update({"agent": "claude", "status": "needs_input", "task": "n", "question": "Which one?"})

    panel.refresh()

    order = list(panel.rows)

    assert not panel.isHidden()
    assert panel.rows["n"].ask.isHidden() is False
    assert panel.rows["r"].ask.isHidden()
    assert [t.id for t in panel.visible_tasks()] == ["n", "r", "d"]


def test_at_most_four_cards_with_a_more_count():

    app = qapp()

    hub = AgentHub()
    panel = AgentsPanel(hub)

    for i in range(6):
        hub.update({"agent": f"tool{i}", "status": "running", "task": f"t{i}"})

    panel.refresh()

    assert len(panel.rows) == 4 and panel.more.text() == "+2 more"


def test_replying_in_the_panel_reaches_a_listening_agent():

    app, hub, window, car, controller = make_all()

    report(app, hub, agent="claude", status="needs_input", task="b", question="Which database?")

    row = window.agents_panel.rows["b"]

    # nobody is listening: the answer is copied for pasting
    row._send("postgres")

    assert hub.tasks["b"].answer == "postgres"
    assert "Copied" in row.note.text()

    from PySide6.QtWidgets import QApplication

    assert QApplication.clipboard().text() == "postgres"


def test_a_listening_hook_receives_the_reply():

    import threading

    app, hub, window, car, controller = make_all()

    report(app, hub, agent="claude", status="needs_input", task="b", question="Which database?")

    got = []
    waiter = threading.Thread(target=lambda: got.append(hub.wait_answer("b", 5)))
    waiter.start()

    pump(app, lambda: hub.is_waiting("b"))

    assert window.reply_to_agent("b", "postgres") is True

    waiter.join(2)

    assert got == ["postgres"]
    assert "Sent" in window.agents_panel.rows["b"].note.text()


def test_dismissing_a_finished_card():

    app, hub, window, car, controller = make_all()

    report(app, hub, agent="claude", status="done", task="b")

    window.agents_panel.rows["b"].dismissed.emit("b")

    assert "b" not in hub.tasks and "b" not in window.agents_panel.rows


# ---------------------------------------------------------------
# Sophia's own tools
# ---------------------------------------------------------------

def tools(tmp_path):

    hub = AgentHub()
    registry = ToolRegistry()

    register_agent_tools(registry, hub, tmp_path)

    return hub, registry


def test_asking_sophia_what_the_agents_are_doing(tmp_path):

    hub, registry = tools(tmp_path)

    hub.update({"agent": "claude", "status": "running", "title": "the login fix"})

    result = registry.execute("agent_status", {}, None)

    assert result.ok and "Claude is working on the login fix" in result.message


def test_replying_through_sophia_asks_first_and_picks_the_waiting_agent(tmp_path):

    hub, registry = tools(tmp_path)

    assert registry.tools["reply_to_agent"].risk is Risk.CONFIRM

    assert not registry.execute("reply_to_agent", {"answer": "yes"}, None, confirmed=True).ok

    hub.update({"agent": "claude", "status": "needs_input", "task": "a", "question": "ok?"})

    result = registry.execute("reply_to_agent", {"answer": "yes"}, None, confirmed=True)

    assert result.ok and hub.tasks["a"].answer == "yes"


def test_two_waiting_agents_need_a_choice(tmp_path):

    hub, registry = tools(tmp_path)

    hub.update({"agent": "claude", "status": "needs_input", "task": "a", "question": "ok?"})
    hub.update({"agent": "gemini", "status": "needs_input", "task": "b", "question": "ok?"})

    result = registry.execute("reply_to_agent", {"answer": "yes"}, None, confirmed=True)

    assert not result.ok and "Which one" in result.message

    picked = registry.execute("reply_to_agent", {"answer": "yes", "agent": "gemini"}, None, confirmed=True)

    assert picked.ok and hub.tasks["b"].answer == "yes" and hub.tasks["a"].answer == ""


def test_connect_instructions_name_the_commands(tmp_path):

    hub, registry = tools(tmp_path)

    text = registry.execute("connect_agents", {}, None).message

    assert "app.agents.setup claude --apply" in text and "wrap --agent" in text
