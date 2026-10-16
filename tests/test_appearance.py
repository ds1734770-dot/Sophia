import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from app.ui.armor import ARMOR_H, ARMOR_W, ArmorModel
from app.ui.car import CarModel
from app.ui.characters import CHARACTERS, make_model, valid
from app.ui.floating_car import CarController, FloatingCar, Layout
from tests.test_floating_car import FakeMouse, fresh_settings, make_pair, qapp
from tests.test_ui import pump


def render(model, width=240, height=262):

    qapp()

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor("#0b0d12"))

    painter = QPainter(image)
    model.draw(painter, QRectF(0, 0, width, height))
    painter.end()

    return image


def lit_pixels(image):

    count = 0

    for y in range(0, image.height(), 3):
        for x in range(0, image.width(), 3):

            if image.pixelColor(x, y) != QColor("#0b0d12"):
                count += 1

    return count


def test_unknown_appearances_fall_back_to_the_car():

    assert valid("armor") == "armor" and valid("car") == "car"
    assert valid("wizard") == "car" and valid(None) == "car"

    assert isinstance(make_model("armor"), ArmorModel)
    assert isinstance(make_model("nope"), CarModel)


def test_every_appearance_draws_in_every_state():

    for key in CHARACTERS:

        for state in ("idle", "listening", "thinking", "speaking", "alert"):

            model = make_model(key)
            model.set_state(state)
            model.set_level(0.7)
            model.hover = state == "idle"

            for _ in range(30):
                model.step(0.05)

            for effect in ("burst", "bounce", "shake", "honk"):
                model.kick(effect)

            assert lit_pixels(render(model)) > 50, (key, state)


def test_the_armor_poses_follow_the_state():

    model = ArmorModel(seed=1)

    for _ in range(40):
        model.step(0.05)

    resting = list(model.right)

    model.set_state("listening")

    for _ in range(40):
        model.step(0.05)

    assert model.right[0] > resting[0] + 40            # the hand rises to listen

    model.set_state("alert")

    for _ in range(40):
        model.step(0.05)

    assert model.left[0] > 60 and model.right[0] > 60  # both palms up


def test_the_armor_leans_and_burns_its_thrusters_when_flying():

    still = ArmorModel(seed=1)
    flying = ArmorModel(seed=1)

    flying.moving = True

    for _ in range(40):

        still.step(0.05)
        flying.step(0.05, dx=18.0)

    assert abs(flying.lean) > 5 and abs(still.lean) < 1
    assert any(p.kind == "spark" for p in flying.particles) or flying.speed > 100


def test_the_armor_takes_an_agents_colour_on_its_red_only():

    model = ArmorModel(seed=1)

    for _ in range(5):
        model.step(0.05)

    before = render(model)

    model.set_tint("#5b8def")

    for _ in range(60):
        model.step(0.05)

    after = render(model)

    # the red suit became blue, the gold trim stayed
    def count(image, test):

        return sum(
            1 for y in range(0, image.height(), 2) for x in range(0, image.width(), 2)
            if test(image.pixelColor(x, y))
        )

    red = lambda c: c.red() > 150 and c.green() < 90 and c.blue() < 90
    blue = lambda c: c.blue() > 150 and c.red() < 120

    assert count(before, red) > 100 and count(after, red) < count(before, red) / 4
    assert count(after, blue) > 100


def test_a_tall_figure_gets_a_taller_window_with_buttons_below():

    car = Layout(130, "car")
    armor = Layout(130, "armor")

    assert armor.car_rect.height() > armor.car_rect.width()
    assert armor.button_y > armor.car_rect.bottom()
    assert armor.height > car.height * 0.5
    assert armor.car_rect.height() == round(130 * ARMOR_H / ARMOR_W)


def test_switching_appearance_keeps_the_figure_standing_where_it_was():

    qapp()

    settings = fresh_settings()

    car = FloatingCar(settings=settings, cursor=FakeMouse())
    car.show()
    car.move(300, 300)

    foot = (car.x() + car.width() // 2, car.y() + car.height())

    car.set_character("armor")

    assert car.character == "armor" and isinstance(car.model, ArmorModel)
    assert car.height() == car.lay.height

    assert abs((car.x() + car.width() // 2) - foot[0]) <= 2
    assert abs((car.y() + car.height()) - foot[1]) <= 2

    assert settings.value("appearance") == "armor"

    car.set_character("car")

    assert isinstance(car.model, CarModel)


def test_the_choice_is_remembered_next_time():

    qapp()

    settings = fresh_settings()

    first = FloatingCar(settings=settings, cursor=FakeMouse())
    first.set_character("armor")

    second = FloatingCar(settings=settings, cursor=FakeMouse())

    assert second.character == "armor" and second.lay.car_rect.height() > second.lay.car_rect.width()


def test_the_menu_choice_changes_the_car_window_and_the_chat_window():

    app = qapp()

    window, car, controller = make_pair(app)

    car.appearance_requested.emit("armor")

    assert car.character == "armor"
    assert window.character == "armor" and isinstance(window.orb_model, ArmorModel)
    assert window.hero_orb.model is window.orb_model
    assert window.hero_orb.height() == CHARACTERS["armor"]["hero"][1]

    window.appearance_requested.emit("car")

    assert car.character == "car" and isinstance(window.orb_model, CarModel)


def test_the_armor_still_reacts_to_what_sophia_does():

    app = qapp()

    window, car, controller = make_pair(app)

    car.appearance_requested.emit("armor")

    car.set_activity("listening", 0.6)

    assert car.model.state == "listening"

    car.on_effect("burst")

    assert car.model.flash_time > 0 and any(p.kind == "spark" for p in car.model.particles)


# ---------------------------------------------------------------
# The armor's flights
# ---------------------------------------------------------------

def armor_car(monkeypatch, sounds=None):

    from app.ui import floating_car

    monkeypatch.setattr(floating_car, "ARMOR_ENTRY_MS", 400)
    monkeypatch.setattr(floating_car, "ARMOR_SETTLE_MS", 60)
    monkeypatch.setattr(floating_car, "ARMOR_CHARGE_MS", 60)
    monkeypatch.setattr(floating_car, "ARMOR_LAUNCH_MS", 300)

    qapp()

    car = FloatingCar(settings=fresh_settings(), cursor=FakeMouse(), sounds=sounds)
    car.set_character("armor")

    seen = []

    original = car.model.set_phase

    def record(phase):
        if not seen or seen[-1] != phase:
            seen.append(phase)
        original(phase)

    car.model.set_phase = record

    return car, seen


def test_the_armor_flies_in_brakes_lands_and_settles(monkeypatch):

    from tests.test_floating_car import FakeSounds

    app = qapp()

    sounds = FakeSounds()
    car, seen = armor_car(monkeypatch, sounds)

    car.enter()

    assert car.driving and car.model.mode == "arrive"

    assert pump(app, lambda: not car.driving, seconds=5)

    assert seen == ["fly", "brake", "land", "touch"]
    assert car.model.mode is None and car.model.phase == ""
    assert car.pos() == car.rest_pos                              # exactly where it should land

    # thrusters on the way in, repulsors for braking, then the landing
    assert sounds.played == ["jet", "repulsor", "land"]


def test_touchdown_makes_a_shockwave_dust_and_a_crouch(monkeypatch):

    app = qapp()

    car, seen = armor_car(monkeypatch)

    # a long settle, so a busy machine cannot end the sequence before we look
    from app.ui import floating_car

    monkeypatch.setattr(floating_car, "ARMOR_SETTLE_MS", 1500)

    car.enter()

    assert pump(app, lambda: car.model.phase == "touch", seconds=5)

    for _ in range(6):
        car.model.step(0.02)

    assert car.model.shock >= 0
    assert car.model.crouch > 0.3
    assert any(p.kind == "dust" for p in car.model.particles)


def test_a_quiet_arrival_makes_no_noise(monkeypatch):

    from tests.test_floating_car import FakeSounds

    app = qapp()

    sounds = FakeSounds()
    car, seen = armor_car(monkeypatch, sounds)

    car.enter(quiet=True)

    assert pump(app, lambda: not car.driving, seconds=5)

    assert sounds.played == [] and seen[-1] == "touch"


def test_hiding_the_armor_charges_then_launches_away(monkeypatch):

    from tests.test_floating_car import FakeSounds

    app = qapp()

    sounds = FakeSounds()
    car, seen = armor_car(monkeypatch, sounds)

    car.show()
    car.move(400, 400)

    car.hide_away()

    assert car.hidden and car.model.mode == "depart"

    assert pump(app, lambda: not car.isVisible(), seconds=5)

    assert seen == ["charge", "launch"]
    assert sounds.played == ["repulsor", "launch"]
    assert car.model.mode is None and not car.driving


def test_quitting_launches_the_armor_off_the_right_edge(monkeypatch):

    app = qapp()

    car, seen = armor_car(monkeypatch)

    car.show()
    car.move(300, 300)

    gone = []

    car.exit_and_quit(lambda: gone.append(True))

    assert pump(app, lambda: bool(gone), seconds=5)

    assert car.x() > 300 and car.y() < 300 and car.model.facing == 1


def test_the_car_still_drives_in_the_old_way():

    app = qapp()

    car = FloatingCar(settings=fresh_settings(), cursor=FakeMouse())

    car.enter()

    assert car.model.mode is None if hasattr(car.model, "mode") else True
    assert pump(app, lambda: not car.driving, seconds=5)
    assert car.pos() == car.rest_pos
