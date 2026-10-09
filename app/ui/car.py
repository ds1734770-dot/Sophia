"""
Sophia's character: a yellow sports coupe drawn entirely in code.

CarModel holds the animation state and physics (no Qt, so it is easy to
test); draw_car paints it; CarWidget is a plain widget that shows it.

States (what Sophia is doing): idle, listening, thinking, speaking, alert.
Extras: hover (headlights on, engine revving), moving (being dragged or
driving), plus one-off effects: bounce, shake, burst (sparkles) and honk
(headlights flash twice).

The car is a generic coupe: no manufacturer badge or logo.
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

STATES = ("idle", "listening", "thinking", "speaking", "alert")

# The drawing lives in a 480 x 170 canvas; the car is 400 wide inside it
# so that headlight beams and smoke have room on both sides.
CANVAS_W = 480
CANVAS_H = 170
CAR_X = 40

WHEEL_RADIUS = 26

# one wipe there and back
WIPER_SWEEP_SECONDS = 0.9
FRONT_WHEEL = (298, 114)
REAR_WHEEL = (102, 114)
GROUND_Y = 143

# the round head lamp sits high on the front wing
LAMP = (354, 91)


def approach(current, target, rate, dt):
    """
    Move `current` toward `target`, smoothly (exponential easing).
    """

    return current + (target - current) * (1 - math.exp(-rate * dt))


class Particle:

    __slots__ = ("x", "y", "vx", "vy", "life", "age", "size", "kind")

    def __init__(self, x, y, vx, vy, life, size, kind):

        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life, self.age, self.size, self.kind = life, 0.0, size, kind


class CarModel:

    def __init__(self, seed=None):

        self.rng = random.Random(seed)

        self.state = "idle"
        self.hover = False
        self.moving = False        # being dragged (also set while driving)

        self.facing = 1            # 1 faces right, -1 faces left

        self.time = 0.0
        self.level = 0.0
        self._level_target = 0.0

        # eased values (0..1 unless noted)
        self.light = 0.0           # headlight brightness
        self.rev = 0.0             # engine revving
        self.energy = 0.0

        self.wheel_angle = 0.0     # radians
        self.speed = 0.0           # logical px per second (signed)
        self._last_speed = 0.0
        self.pitch = 0.0           # degrees, nose up positive
        self.bounce = 0.0          # logical px (positive is down)
        self._bounce_velocity = 0.0

        self.shake_time = 0.0
        self.flash_time = 0.0      # honk: headlights flash twice
        self.brake = 0.0           # brake lights

        # windscreen wiper: 0 is parked, 1 is fully swept
        self.wiper = 0.0
        self.wipe_time = 0.0
        self._wipe_clock = 0.0

        self.particles = []
        self._smoke_timer = 0.0

        # an agent's colour: the paint fades to it (and back to yellow)
        self.tint = QColor("#ffcf10")
        self.tint_mix = 0.0
        self._tint_goal = None

        # an agent is waiting for the user: hazard lights keep blinking
        self.attention = False

        # colours of the other agents that are working (small dots)
        self.pips = []

    # ------------------------------------------------

    def set_tint(self, color):
        """
        Paint the car in an agent's colour (a hex string or QColor), or
        back to yellow with None. The change fades in.
        """

        self._tint_goal = QColor(color) if color else None

    def set_state(self, state):

        if state not in STATES:
            raise ValueError(f"unknown car state '{state}'")

        self.state = state

    def set_level(self, level):

        self._level_target = max(0.0, min(1.0, float(level)))

    def look_at(self, x, y):
        """
        Kept for compatibility with the old orb; the car does not look.
        """

    def kick(self, kind):
        """
        A short effect: "bounce", "shake", "burst" (sparkles) or "honk".
        """

        if kind == "bounce":

            self._bounce_velocity = -90.0

        elif kind == "shake":

            self.shake_time = 0.5

        elif kind == "honk":

            self.flash_time = 0.9

        elif kind == "wipe":

            # two sweeps
            self.wipe_time = max(self.wipe_time, 2 * WIPER_SWEEP_SECONDS)

        elif kind == "burst":

            self._bounce_velocity = -45.0
            self.flash_time = 0.9

            for _ in range(20):

                angle = self.rng.uniform(math.pi * 1.1, math.pi * 1.9)
                speed = self.rng.uniform(40, 120)

                self.particles.append(Particle(
                    200 + self.rng.uniform(-80, 80), 50,
                    math.cos(angle) * speed, math.sin(angle) * speed,
                    self.rng.uniform(0.6, 1.1), self.rng.uniform(1.5, 3.2), "spark",
                ))

        else:

            raise ValueError(f"unknown effect '{kind}'")

    # ------------------------------------------------

    def step(self, dt, dx=0.0):
        """
        Advance by dt seconds. dx is how far the car moved horizontally
        this frame, in logical pixels (positive is to the right).
        """

        dt = max(0.0, min(dt, 0.1))

        self.time += dt

        # paint fade
        if self._tint_goal is not None:

            self.tint = QColor(
                int(approach(self.tint.red(), self._tint_goal.red(), 5, dt)),
                int(approach(self.tint.green(), self._tint_goal.green(), 5, dt)),
                int(approach(self.tint.blue(), self._tint_goal.blue(), 5, dt)),
            )

        self.tint_mix = approach(
            self.tint_mix, 1.0 if self._tint_goal is not None else 0.0, 4, dt
        )

        # driving: wheels turn with the ground, the car faces its heading
        velocity = dx / dt if dt > 0 else 0.0

        self.speed = approach(self.speed, velocity, 14, dt)

        if abs(self.speed) > 30:
            self.facing = 1 if self.speed > 0 else -1

        self.wheel_angle = (self.wheel_angle + dx / WHEEL_RADIUS) % (math.tau * 100)

        accel = (self.speed - self._last_speed) / dt if dt > 0 else 0.0

        self._last_speed = self.speed

        # nose lifts when accelerating, dips when braking
        pitch_target = max(-4.0, min(4.0, accel * 0.0014 * self.facing))

        self.pitch = approach(self.pitch, pitch_target + 0.6 * self.rev, 9, dt)

        # brake lights when slowing down
        braking = 1.0 if (accel * self.speed < -400 and abs(self.speed) > 20) else 0.0

        self.brake = approach(self.brake, max(braking, 0.9 if self.state == "speaking" else 0.0), 12, dt)

        # light and engine targets per situation
        light_target = {
            "idle": 0.0, "listening": 0.85, "thinking": 0.25,
            "speaking": 0.55, "alert": 0.6,
        }[self.state]

        rev_target = {
            "idle": 0.0, "listening": 0.35, "thinking": 0.5,
            "speaking": 0.45, "alert": 0.8,
        }[self.state]

        if self.hover:

            light_target = max(light_target, 0.8)
            rev_target = max(rev_target, 0.7)

        if abs(self.speed) > 20:

            light_target = max(light_target, 0.7)
            rev_target = max(rev_target, 0.6)

        self.level = approach(self.level, self._level_target, 14, dt)

        if self.state == "listening":
            light_target = min(1.0, 0.6 + 0.6 * self.level)

        self.flash_time = max(0.0, self.flash_time - dt)

        if self.flash_time > 0:

            # two quick flashes
            light_target = 1.0 if math.sin(self.flash_time * 14) > 0 else 0.1

        self.light = approach(self.light, light_target, 18 if self.flash_time > 0 else 6, dt)
        self.rev = approach(self.rev, rev_target, 5, dt)
        self.energy = approach(self.energy, 0.2 + 0.8 * self.rev, 4, dt)

        # suspension is a damped spring
        accel_b = -220 * self.bounce - 12 * self._bounce_velocity
        self._bounce_velocity += accel_b * dt
        self.bounce += self._bounce_velocity * dt

        self.shake_time = max(0.0, self.shake_time - dt)

        # wiper: sweeps while thinking or after a "wipe" request, then
        # returns to its parked position
        self.wipe_time = max(0.0, self.wipe_time - dt)

        if self.wipe_time > 0 or self.state == "thinking":

            self._wipe_clock += dt

            target = 0.5 - 0.5 * math.cos(math.tau * self._wipe_clock / WIPER_SWEEP_SECONDS)

            self.wiper = approach(self.wiper, target, 30, dt)

        else:

            self._wipe_clock = 0.0
            self.wiper = approach(self.wiper, 0.0, 10, dt)

        # exhaust smoke while revving or accelerating
        self._smoke_timer -= dt

        if self._smoke_timer <= 0 and (self.rev > 0.55 or accel * self.facing > 900):

            rear_x = CAR_X + 46   # the canvas is mirrored when facing left

            self.particles.append(Particle(
                rear_x, 122, -self.rng.uniform(8, 30), self.rng.uniform(-14, -4),
                self.rng.uniform(0.5, 0.9), self.rng.uniform(3, 6), "smoke",
            ))

            self._smoke_timer = 0.07

        for p in self.particles:

            p.age += dt
            # smoke stays where it was left on the road; sparkles ride on the car
            p.x += p.vx * dt - (0.0 if p.kind == "spark" else dx * self.facing)
            p.y += p.vy * dt

            if p.kind == "spark":
                p.vy += 160 * dt

        self.particles = [p for p in self.particles if p.age < p.life]

    # ------------------------------------------------

    @property
    def hazard(self):
        """
        Blinking indicator lights while thinking, or while an agent is
        waiting for the user.
        """

        return (self.state == "thinking" or self.attention) and math.sin(self.time * 8) > 0

    @property
    def vibration(self):
        """
        Small engine shake (logical px) while revving, plus error shake.
        """

        shake = 0.0

        if self.rev > 0.3:
            shake += math.sin(self.time * 70) * 0.5 * self.rev

        if self.shake_time > 0:
            shake += math.sin(self.time * 55) * 3.0 * (self.shake_time / 0.5)

        return shake


# ---------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------

def tc(m, color):
    """
    A yellow paint colour, recoloured to the car's current tint: the hue
    follows the agent while the shading (light and dark parts) stays.
    """

    mix = getattr(m, "tint_mix", 0.0)

    if mix <= 0.004:
        return color

    h, s, l, a = color.getHslF()
    th, ts, tl, _ = m.tint.getHslF()

    # yellow's shading is kept; saturation follows the tint
    target = QColor.fromHslF(
        th if th >= 0 else 0.0,
        min(1.0, max(0.0, ts * (0.55 + 0.6 * s))),
        min(0.95, max(0.08, l + (tl - 0.55) * 0.35)),
        a,
    )

    return QColor(
        int(color.red() + (target.red() - color.red()) * mix),
        int(color.green() + (target.green() - color.green()) * mix),
        int(color.blue() + (target.blue() - color.blue()) * mix),
        color.alpha(),
    )


def _body_path():

    path = QPainterPath()

    path.moveTo(52, 129)
    path.lineTo(44, 120)
    path.cubicTo(37, 111, 37, 99, 43, 93)            # rear bumper up to the tail
    path.lineTo(60, 88)                               # duck-tail lip
    path.cubicTo(86, 72, 124, 52, 172, 45)            # the long fastback sweep
    path.cubicTo(198, 41, 224, 41, 238, 48)           # roof peak to windscreen header
    path.cubicTo(256, 57, 272, 66, 292, 72)           # raked windscreen
    path.cubicTo(322, 77, 346, 82, 366, 91)           # low bonnet to the nose
    path.cubicTo(380, 98, 382, 113, 374, 128)         # rounded nose
    path.closeSubpath()

    for cx, cy in (FRONT_WHEEL, REAR_WHEEL):

        arch = QPainterPath()
        arch.addEllipse(QPointF(cx, cy), WHEEL_RADIUS + 6, WHEEL_RADIUS + 6)

        path = path.subtracted(arch)

    return path


def _window_path():

    path = QPainterPath()

    path.moveTo(120, 76)
    path.cubicTo(136, 64, 158, 54, 182, 49)
    path.lineTo(220, 48)
    path.cubicTo(237, 50, 250, 58, 266, 68)
    path.lineTo(282, 73)
    path.closeSubpath()

    return path


_BODY = None
_WINDOW = None


def draw_car(painter, rect, m, with_ground=True):
    """
    Paint the car model into `rect` (a QRectF or QRect). The canvas
    keeps its 480:170 shape and is centred in the rect.
    """

    global _BODY, _WINDOW

    if _BODY is None:

        _BODY = _body_path()
        _WINDOW = _window_path()

    rect = QRectF(rect)

    scale = min(rect.width() / CANVAS_W, rect.height() / CANVAS_H)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    painter.translate(
        rect.center().x() - CANVAS_W * scale / 2,
        rect.center().y() - CANVAS_H * scale / 2,
    )
    painter.scale(scale, scale)

    # face left by mirroring the whole canvas
    if m.facing < 0:

        painter.translate(CANVAS_W, 0)
        painter.scale(-1, 1)

    painter.translate(CAR_X, 0)

    # ---- ground shadow (does not tilt)
    if with_ground:

        shadow = QRadialGradient(QPointF(200, GROUND_Y), 190)

        shadow.setColorAt(0.0, QColor(0, 0, 0, 90))
        shadow.setColorAt(0.6, QColor(0, 0, 0, 35))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.save()
        painter.translate(200, GROUND_Y)
        painter.scale(1, 0.12)
        painter.translate(-200, -GROUND_Y)
        painter.drawEllipse(QPointF(200, GROUND_Y), 190, 190)
        painter.restore()

    # ---- the car body moves and tilts as a unit
    painter.save()

    painter.translate(m.vibration, m.bounce)
    painter.translate(210, 128)
    painter.rotate(-m.pitch)
    painter.translate(-210, -128)

    _draw_beams(painter, m)
    _draw_wheels(painter, m)
    _draw_body(painter, m)

    painter.restore()

    _draw_particles(painter, m)

    _draw_pips(painter, m)

    painter.restore()


def _draw_beams(painter, m):

    if m.light < 0.05:
        return

    lx, ly = LAMP

    # headlight cone, drawn first so the body sits on top
    beam = QLinearGradient(QPointF(lx, ly), QPointF(lx + 120, ly + 20))

    warm = QColor(255, 244, 200, int(150 * m.light))

    # a listening car lights up cool white-blue
    if m.state == "listening":
        warm = QColor(200, 240, 255, int(170 * m.light))

    beam.setColorAt(0.0, warm)
    beam.setColorAt(1.0, QColor(warm.red(), warm.green(), warm.blue(), 0))

    cone = QPainterPath()
    cone.moveTo(lx, ly - 5)
    cone.lineTo(lx + 120, ly - 14 + 8 * (1 - m.light))
    cone.lineTo(lx + 120, ly + 46)
    cone.lineTo(lx, ly + 6)
    cone.closeSubpath()

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(beam))
    painter.drawPath(cone)


def _draw_wheels(painter, m):

    for cx, cy in (REAR_WHEEL, FRONT_WHEEL):

        painter.save()
        painter.translate(cx, cy)

        # tyre
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#17171b"))
        painter.drawEllipse(QPointF(0, 0), WHEEL_RADIUS, WHEEL_RADIUS)

        painter.setBrush(QColor("#2a2a31"))
        painter.drawEllipse(QPointF(0, 0), WHEEL_RADIUS - 3, WHEEL_RADIUS - 3)

        # alloy rim
        rim = QRadialGradient(QPointF(-4, -5), 21)

        rim.setColorAt(0.0, QColor("#f4f6f8"))
        rim.setColorAt(0.7, QColor("#b8bec6"))
        rim.setColorAt(1.0, QColor("#7f8791"))

        painter.setBrush(QBrush(rim))
        painter.drawEllipse(QPointF(0, 0), 17.5, 17.5)

        # five spokes that turn with the road
        painter.rotate(math.degrees(m.wheel_angle))

        painter.setBrush(QColor("#2b2f36"))

        for i in range(5):

            painter.save()
            painter.rotate(i * 72)
            painter.drawRoundedRect(QRectF(-2.4, 3, 4.8, 13), 2.2, 2.2)
            painter.restore()

        painter.setBrush(QColor("#4b4f58"))
        painter.drawEllipse(QPointF(0, 0), 6, 6)

        painter.setBrush(tc(m, QColor("#ffd23c")))
        painter.drawEllipse(QPointF(0, 0), 3.2, 3.2)

        painter.restore()


def _draw_body(painter, m):

    body = _BODY

    painter.setPen(Qt.NoPen)

    # paint: a deep yellow with a lighter shoulder and a darker sill
    paint = QLinearGradient(QPointF(0, 42), QPointF(0, 130))

    paint.setColorAt(0.0, tc(m, QColor("#ffe86a")))
    paint.setColorAt(0.35, tc(m, QColor("#ffcf10")))
    paint.setColorAt(0.8, tc(m, QColor("#f0ae00")))
    paint.setColorAt(1.0, tc(m, QColor("#c98800")))

    painter.setBrush(QBrush(paint))
    painter.drawPath(body)

    painter.save()
    painter.setClipPath(body)

    # soft highlight sweeping along the shoulder
    sheen = QLinearGradient(QPointF(80, 66), QPointF(350, 96))

    sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
    sheen.setColorAt(0.35, QColor(255, 255, 255, 120))
    sheen.setColorAt(0.65, QColor(255, 255, 255, 30))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))

    painter.setBrush(QBrush(sheen))
    painter.drawRect(QRectF(40, 80, 340, 12))

    # roof reflection
    roof = QLinearGradient(QPointF(0, 42), QPointF(0, 62))

    roof.setColorAt(0.0, QColor(255, 255, 255, 110))
    roof.setColorAt(1.0, QColor(255, 255, 255, 0))

    painter.setBrush(QBrush(roof))
    painter.drawRect(QRectF(100, 40, 170, 22))

    # shadow along the bottom edge
    base = QLinearGradient(QPointF(0, 110), QPointF(0, 131))

    base.setColorAt(0.0, QColor(0, 0, 0, 0))
    base.setColorAt(1.0, tc(m, QColor(60, 30, 0, 110)))

    painter.setBrush(QBrush(base))
    painter.drawRect(QRectF(40, 108, 340, 24))

    painter.restore()

    # crisp outline
    painter.setPen(QPen(tc(m, QColor(150, 98, 0, 170)), 1.2))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(body)

    # wheel-arch lips
    painter.setPen(QPen(QColor(48, 36, 10, 200), 2.2))

    for cx, cy in (FRONT_WHEEL, REAR_WHEEL):
        painter.drawArc(QRectF(cx - 32, cy - 32, 64, 64), 0, 180 * 16)

    # black sill between the wheels
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#1d1a14"))
    painter.drawRoundedRect(QRectF(134, 121, 130, 7), 3, 3)

    # glass
    glass = QLinearGradient(QPointF(0, 50), QPointF(0, 76))

    glass.setColorAt(0.0, QColor("#38465c"))
    glass.setColorAt(1.0, QColor("#141a24"))

    painter.setBrush(QBrush(glass))
    painter.drawPath(_WINDOW)

    painter.save()
    painter.setClipPath(_WINDOW)

    streak = QPainterPath()

    streak.moveTo(150, 78)
    streak.lineTo(178, 49)
    streak.lineTo(198, 49)
    streak.lineTo(170, 78)
    streak.closeSubpath()

    painter.setBrush(QColor(255, 255, 255, 46))
    painter.drawPath(streak)

    painter.restore()

    _draw_wiper(painter, m)

    # window frame
    painter.setPen(QPen(QColor("#0e0e11"), 1.6))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(_WINDOW)

    # door shut line and handle
    painter.setPen(QPen(tc(m, QColor(120, 78, 0, 170)), 1.3))
    painter.drawLine(QPointF(198, 78), QPointF(198, 119))
    painter.drawLine(QPointF(126, 80), QPointF(128, 112))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 244, 190, 220))
    painter.drawRoundedRect(QRectF(170, 88, 18, 4.5), 2.2, 2.2)

    # side mirror
    painter.setBrush(tc(m, QColor("#e9a900")))
    painter.drawRoundedRect(QRectF(262, 67, 14, 8), 4, 4)

    # exhaust tip
    painter.setBrush(QColor("#c8cdd3"))
    painter.drawEllipse(QPointF(50, 121), 4.4, 3.2)

    _draw_lights(painter, m)


def _draw_wiper(painter, m):
    """
    A wiper arm pivoting at the foot of the windscreen. Parked it lies
    along the bottom of the glass; swept it rises up the screen.
    """

    pivot = QPointF(286, 73)

    angle = math.radians(181 + 27 * m.wiper)

    painter.save()
    painter.setClipPath(_WINDOW)

    painter.translate(pivot)
    painter.rotate(math.degrees(angle) - 180)

    pen = QPen(QColor(215, 222, 234, 255), 2.2)
    pen.setCapStyle(Qt.RoundCap)

    painter.setPen(pen)
    painter.drawLine(QPointF(0, 0), QPointF(-50, 0))

    blade = QPen(QColor(8, 8, 10, 255), 3.4)
    blade.setCapStyle(Qt.RoundCap)

    painter.setPen(blade)
    painter.drawLine(QPointF(-12, 2.0), QPointF(-50, 2.0))

    painter.restore()

    # the pivot nut stays outside the clip
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(205, 212, 224))
    painter.drawEllipse(pivot, 1.8, 1.8)


def _draw_lights(painter, m):

    lx, ly = LAMP

    painter.setPen(Qt.NoPen)

    # the wing rises into a rounded housing around the lamp
    housing = QRadialGradient(QPointF(lx - 3, ly - 5), 18)

    housing.setColorAt(0.0, tc(m, QColor("#ffe86a")))
    housing.setColorAt(1.0, tc(m, QColor("#f0ae00")))

    painter.setBrush(QBrush(housing))
    painter.drawEllipse(QPointF(lx, ly), 14.5, 13)

    painter.setBrush(QColor("#25262b"))
    painter.drawEllipse(QPointF(lx, ly), 11, 11)

    lamp = QRadialGradient(QPointF(lx - 3, ly - 3), 10)

    on = m.light

    lamp.setColorAt(0.0, QColor(255, 255, int(235 + 20 * on)))
    lamp.setColorAt(0.6, QColor(int(215 + 40 * on), int(225 + 25 * on), int(235 - 20 * on)))
    lamp.setColorAt(1.0, QColor("#8d97a3"))

    painter.setBrush(QBrush(lamp))
    painter.drawEllipse(QPointF(lx, ly), 8.6, 8.6)

    if on > 0.05:

        glow = QRadialGradient(QPointF(lx, ly), 28)

        glow.setColorAt(0.0, QColor(255, 246, 205, int(190 * on)))
        glow.setColorAt(1.0, QColor(255, 246, 205, 0))

        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(lx, ly), 28, 28)

    # front air intake and amber indicator
    painter.setBrush(QColor("#1d1a14"))
    painter.drawRoundedRect(QRectF(352, 113, 22, 5), 2.4, 2.4)

    painter.setBrush(QColor("#ffb020") if m.hazard else QColor("#7a5a1a"))
    painter.drawRoundedRect(QRectF(362, 106, 9, 4), 2, 2)

    # tail light: a slim red lamp across the tail
    red = 90 + int(150 * m.brake)

    painter.setBrush(QColor(red, 20, 24))
    painter.drawRoundedRect(QRectF(41, 97, 13, 5), 2.2, 2.2)

    if m.brake > 0.1 or m.hazard:

        halo = QRadialGradient(QPointF(46, 100), 20)

        halo.setColorAt(0.0, QColor(255, 40, 40, int(150 * max(m.brake, 0.6 if m.hazard else 0))))
        halo.setColorAt(1.0, QColor(255, 40, 40, 0))

        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(46, 100), 20, 20)

    # rear indicator
    painter.setBrush(QColor("#ffb020") if m.hazard else QColor("#6e4e14"))
    painter.drawRoundedRect(QRectF(42, 106, 8, 3.5), 1.8, 1.8)


def _draw_pips(painter, m):
    """
    A small dot over the car for each other agent that is working.
    """

    pips = getattr(m, "pips", None)

    if not pips:
        return

    painter.setPen(Qt.NoPen)

    for i, color in enumerate(pips[:6]):

        pulse = 0.5 + 0.5 * math.sin(m.time * 3 + i * 1.3)

        c = QColor(color)

        halo = QColor(c)
        halo.setAlpha(int(70 * pulse))

        x = 160 + i * 16
        y = 14

        painter.setBrush(halo)
        painter.drawEllipse(QPointF(x, y), 10, 10)

        painter.setBrush(c)
        painter.drawEllipse(QPointF(x, y), 6, 6)


def _draw_particles(painter, m):

    painter.setPen(Qt.NoPen)

    for p in m.particles:

        t = p.age / p.life

        if p.kind == "smoke":

            painter.setBrush(QColor(210, 210, 215, int(110 * (1 - t))))
            painter.drawEllipse(QPointF(p.x, p.y), p.size * (1 + 1.6 * t), p.size * (1 + 1.6 * t))

        else:

            painter.setBrush(QColor(255, 240, 170, int(255 * (1 - t))))
            painter.drawEllipse(QPointF(p.x, p.y), p.size * (1 - 0.5 * t), p.size * (1 - 0.5 * t))


class CarWidget(QWidget):
    """
    Shows a CarModel. Used on the welcome screen and in the header.
    """

    def __init__(self, model, width=300, height=106):

        super().__init__()

        self.model = model

        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):

        painter = QPainter(self)

        draw_car(painter, self.rect(), self.model)

        painter.end()


__all__ = ["CANVAS_H", "CANVAS_W", "CarModel", "CarWidget", "draw_car"]
