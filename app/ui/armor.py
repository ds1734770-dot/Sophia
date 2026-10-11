"""
The armoured hero: a red and gold powered suit with a glowing chest and
eyes, drawn in code (an original design inspired by the comic-book
armoured hero, not official artwork). It uses the car's state machine, so
every thing Sophia does shows up in it too:

    idle        hovers, eyes and chest glow softly
    listening   one hand raised, chest glow follows your voice
    thinking    eyes scan, a ring of lights orbits the chest, hand by the head
    speaking    both hands gesture, palms pulse with the voice
    alert       both palms up and flashing (also: an agent needs you)
    moving      leans into the flight, thrusters roar
    burst       a repulsor blast from the palm and a flash
"""

import math

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

from app.ui.car import CarModel, Particle, approach, tc

ARMOR_W = 260
ARMOR_H = 285
CENTER_X = 130          # the figure is drawn around x = 100, shifted by 30

RED = QColor("#d9262c")
RED_LIGHT = QColor("#f2504a")
RED_DARK = QColor("#8a1017")
GOLD = QColor("#f4b93a")
GOLD_LIGHT = QColor("#ffe08a")
GOLD_DARK = QColor("#b97d14")
DARK = QColor("#1a1216")
GLOW = QColor("#bff6ff")


def clamp(value, low=0.0, high=1.0):

    return max(low, min(high, value))


class ArmorModel(CarModel):
    """
    Same states and effects as the car, plus arm poses.
    """

    character = "armor"
    canvas = (ARMOR_W, ARMOR_H)

    def __init__(self, seed=None):

        super().__init__(seed)

        self.tint = QColor("#d9262c")

        # eased arm angles in degrees: [upper, bend] for the left and right arm
        self.left = [6.0, 4.0]
        self.right = [6.0, 4.0]

        self.blink = 0.0
        self.charge = 0.0
        self.lean = 0.0

    # ------------------------------------------------

    def draw(self, painter, rect, with_ground=True):

        draw_armor(painter, rect, self, with_ground)

    def kick(self, kind):

        if kind == "burst":

            # a repulsor blast from the raised palm
            self.flash_time = 0.9
            self._bounce_velocity = -35.0
            self.charge = 1.0

            for _ in range(22):

                angle = self.rng.uniform(-0.5, 0.5)
                speed = self.rng.uniform(80, 220)

                self.particles.append(Particle(
                    150, 70, math.cos(angle) * speed, math.sin(angle) * speed - 30,
                    self.rng.uniform(0.4, 0.9), self.rng.uniform(1.5, 3.4), "spark",
                ))

            return

        super().kick(kind)

    # ------------------------------------------------

    def _poses(self):
        """
        Target arm angles [upper, bend] (degrees, positive = outward and
        up) for the left and right arm in the current situation.
        """

        t = self.time
        sway = math.sin(t * 1.7) * 2.0

        left = [6.0 + sway, 4.0]
        right = [6.0 - sway, 4.0]

        if self.state == "listening":

            right = [74.0, 38.0 + 8 * self.level]

        elif self.state == "thinking":

            right = [48.0, 118.0 + 6 * math.sin(t * 3)]

        elif self.state == "speaking":

            talk = math.sin(t * 5.2) * (6 + 14 * self.level)

            left = [34.0 + talk, 22.0 - talk * 0.6]
            right = [38.0 - talk, 26.0 + talk * 0.6]

        elif self.state == "alert":

            left = [82.0, 12.0]
            right = [82.0, 12.0]

        if self.hover and self.state == "idle":

            # a friendly wave
            right = [96.0, 30.0 + 26 * math.sin(t * 8)]

        if self.flash_time > 0.2:

            # the blast: arm straight out
            right = [92.0, 4.0]

        if self.moving or abs(self.speed) > 30:

            left = [-14.0, 0.0]
            right = [-14.0, 0.0]

        return left, right

    def step(self, dt, dx=0.0):

        super().step(dt, dx)

        # the car's exhaust smoke does not belong here
        self.particles = [p for p in self.particles if p.kind != "smoke"]

        left, right = self._poses()

        for current, target in ((self.left, left), (self.right, right)):

            current[0] = approach(current[0], target[0], 9, dt)
            current[1] = approach(current[1], target[1], 9, dt)

        # blink: the eyes narrow briefly now and then (often while thinking)
        period = 1.1 if self.state == "thinking" else 3.4

        phase = (self.time % period) / period

        self.blink = 0.0 if phase < 0.94 else 1.0 - abs(phase - 0.97) / 0.03

        charge_target = {
            "idle": 0.1, "listening": 0.3 + 0.7 * self.level,
            "thinking": 0.35, "speaking": 0.3 + 0.6 * self.level, "alert": 0.9,
        }[self.state]

        if self.hover:
            charge_target = max(charge_target, 0.5)

        self.charge = approach(self.charge, charge_target, 7, dt)

        lean_target = clamp(self.speed / 600, -1, 1) * 14

        self.lean = approach(self.lean, lean_target, 6, dt)

        # thruster sparks while flying
        if abs(self.speed) > 120 and self.rng.random() < 0.5:

            self.particles.append(Particle(
                100 + self.rng.uniform(-14, 14), 250,
                -self.speed * 0.05 * self.facing + self.rng.uniform(-10, 10),
                self.rng.uniform(40, 90), self.rng.uniform(0.25, 0.5),
                self.rng.uniform(1.2, 2.4), "spark",
            ))


# ---------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------

def _glow(painter, centre, radius, color, strength):

    if strength <= 0.02:
        return

    gradient = QRadialGradient(centre, radius)

    core = QColor(color)
    core.setAlpha(int(255 * clamp(strength)))

    edge = QColor(color)
    edge.setAlpha(0)

    gradient.setColorAt(0.0, core)
    gradient.setColorAt(1.0, edge)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawEllipse(centre, radius, radius)


def _plate(painter, path, top, bottom, outline):

    gradient = QLinearGradient(path.boundingRect().topLeft(), path.boundingRect().bottomRight())
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, bottom)

    painter.setBrush(QBrush(gradient))
    painter.setPen(QPen(outline, 1.4))
    painter.drawPath(path)


def _rounded(x, y, w, h, r):

    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)

    return path


def _red(m, color):
    """
    The suit's red, recoloured to the active agent's colour.
    """

    return tc(m, color)


def _draw_leg(painter, m, cx, flame):

    red = _red(m, RED)
    red_dark = _red(m, RED_DARK)

    # thigh and shin
    _plate(painter, _rounded(cx - 11, 166, 22, 46, 8), _red(m, RED_LIGHT), red_dark, DARK)
    _plate(painter, _rounded(cx - 9, 206, 18, 40, 7), GOLD_LIGHT, GOLD_DARK, DARK)

    # knee
    painter.setPen(QPen(DARK, 1.2))
    painter.setBrush(GOLD)
    painter.drawEllipse(QPointF(cx, 208), 8, 7)

    # boot
    _plate(painter, _rounded(cx - 12, 240, 24, 14, 6), red, red_dark, DARK)

    # thruster
    _glow(painter, QPointF(cx, 256), 9 + 10 * flame, GLOW, 0.5 + 0.5 * flame)

    if flame > 0.05:

        length = 8 + 26 * flame

        path = QPainterPath()
        path.moveTo(cx - 7, 254)
        path.lineTo(cx + 7, 254)
        path.lineTo(cx, 254 + length)
        path.closeSubpath()

        gradient = QLinearGradient(cx, 254, cx, 254 + length)
        gradient.setColorAt(0.0, QColor(235, 252, 255, 240))
        gradient.setColorAt(0.5, QColor(120, 210, 255, 180))
        gradient.setColorAt(1.0, QColor(60, 120, 255, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)


def _draw_arm(painter, m, side, pose, charge, alert_blink):
    """
    side: -1 for the figure's right arm (screen right), +1 for the left.
    pose: [upper, bend] degrees, positive = outward and up.
    """

    upper, bend = pose

    pivot = QPointF(100 - side * 44, 92)

    painter.save()
    painter.translate(pivot)

    # outward is away from the body: clockwise on the right, counter-clockwise on the left
    painter.rotate(-upper if side < 0 else upper)

    # shoulder pad (round), then the upper arm
    _plate(painter, _rounded(-9, -2, 18, 36, 8), _red(m, RED_LIGHT), _red(m, RED_DARK), DARK)

    painter.translate(0, 32)
    painter.rotate(-bend if side < 0 else bend)

    painter.setPen(QPen(DARK, 1.2))
    painter.setBrush(GOLD)
    painter.drawEllipse(QPointF(0, 0), 7, 6)

    # forearm gauntlet
    _plate(painter, _rounded(-8, 0, 16, 34, 7), GOLD_LIGHT, GOLD_DARK, DARK)

    # hand and its repulsor
    painter.translate(0, 38)

    painter.setPen(QPen(DARK, 1.2))
    painter.setBrush(_red(m, RED))
    painter.drawEllipse(QPointF(0, 0), 8, 8)

    colour = QColor("#ffb347") if alert_blink else GLOW

    _glow(painter, QPointF(0, 2), 12 + 10 * charge, colour, 0.25 + 0.75 * charge)

    painter.setPen(QPen(DARK, 1))
    painter.setBrush(colour if charge > 0.3 else QColor("#7a8a92"))
    painter.drawEllipse(QPointF(0, 2), 4.2, 4.2)

    painter.restore()


def draw_armor(painter, rect, m, with_ground=True):

    rect = QRectF(rect)

    scale = min(rect.width() / ARMOR_W, rect.height() / ARMOR_H)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    painter.translate(
        rect.center().x() - ARMOR_W * scale / 2,
        rect.center().y() - ARMOR_H * scale / 2,
    )
    painter.scale(scale, scale)

    # face left by mirroring
    if m.facing < 0:

        painter.translate(ARMOR_W, 0)
        painter.scale(-1, 1)

    painter.translate(30, 0)

    t = m.time

    # hover: a gentle bob, higher while the engines are working
    bob = math.sin(t * 2.0) * 3.0 - 6.0 - 4.0 * m.rev

    # ---- ground glow and shadow
    if with_ground:

        shadow = QRadialGradient(QPointF(100, 272), 60)
        shadow.setColorAt(0.0, QColor(0, 0, 0, int(110 - 40 * m.rev)))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))

        painter.save()
        painter.translate(100, 272)
        painter.scale(1, 0.16)
        painter.translate(-100, -272)
        painter.drawEllipse(QPointF(100, 272), 60, 60)
        painter.restore()

    # ---- the figure
    painter.save()

    painter.translate(m.vibration, m.bounce + bob)
    painter.translate(100, 150)
    painter.rotate(m.lean * 0.6 * (1 if m.facing > 0 else 1))
    painter.translate(-100, -150)

    flame = clamp(0.25 + 0.5 * m.rev + abs(m.speed) / 350)

    flicker = 0.85 + 0.15 * math.sin(t * 38)

    _draw_leg(painter, m, 84, flame * flicker)
    _draw_leg(painter, m, 116, flame * flicker * (0.9 + 0.1 * math.sin(t * 31 + 1)))

    alert_blink = m.hazard

    # arms behind the torso when they swing back, in front otherwise
    left, right = m.left, m.right

    _draw_arm(painter, m, +1, left, m.charge * 0.6, alert_blink)

    # ---- torso
    red = _red(m, RED)
    red_light = _red(m, RED_LIGHT)
    red_dark = _red(m, RED_DARK)

    # hips and waist
    _plate(painter, _rounded(74, 156, 52, 20, 7), red, red_dark, DARK)
    _plate(painter, _rounded(80, 138, 40, 22, 6), GOLD_LIGHT, GOLD_DARK, DARK)

    # chest
    chest = QPainterPath()
    chest.moveTo(62, 84)
    chest.quadTo(100, 74, 138, 84)
    chest.lineTo(128, 144)
    chest.quadTo(100, 152, 72, 144)
    chest.closeSubpath()

    _plate(painter, chest, red_light, red_dark, DARK)

    # gold chest trim
    painter.setPen(QPen(GOLD, 2))
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(QPointF(70, 128), QPointF(130, 128))
    painter.drawLine(QPointF(66, 100), QPointF(76, 98))
    painter.drawLine(QPointF(134, 100), QPointF(124, 98))

    # the glowing chest reactor
    pulse = 0.5 + 0.5 * math.sin(t * (6 if m.state == "thinking" else 3))

    power = clamp(0.35 + 0.45 * m.light + 0.2 * pulse)

    reactor_colour = QColor("#ff7a45") if alert_blink else GLOW

    _glow(painter, QPointF(100, 110), 26 + 10 * m.charge, reactor_colour, power * 0.9)

    painter.setPen(QPen(DARK, 2))
    painter.setBrush(QColor("#2b3238"))
    painter.drawEllipse(QPointF(100, 110), 12.5, 12.5)

    painter.setPen(Qt.NoPen)
    painter.setBrush(reactor_colour)
    painter.drawEllipse(QPointF(100, 110), 8.5, 8.5)

    painter.setBrush(QColor(255, 255, 255, int(160 + 90 * power)))
    painter.drawEllipse(QPointF(100, 110), 4, 4)

    # shoulders
    for x in (56, 144):

        _plate(painter, _rounded(x - 17, 78, 34, 26, 12), red_light, red_dark, DARK)

        painter.setPen(QPen(GOLD, 1.6))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(x - 12, 83, 24, 14), 20 * 16, 140 * 16)

    # neck
    painter.setPen(QPen(DARK, 1))
    painter.setBrush(QColor("#2a2127"))
    painter.drawRect(QRectF(92, 68, 16, 14))

    # ---- head
    head = QPainterPath()
    head.moveTo(82, 46)
    head.quadTo(82, 24, 100, 22)
    head.quadTo(118, 24, 118, 46)
    head.quadTo(118, 66, 100, 72)
    head.quadTo(82, 66, 82, 46)
    head.closeSubpath()

    _plate(painter, head, GOLD_LIGHT, GOLD_DARK, DARK)

    # the red crown of the helmet
    crown = QPainterPath()
    crown.moveTo(83, 40)
    crown.quadTo(84, 24, 100, 22)
    crown.quadTo(116, 24, 117, 40)
    crown.quadTo(100, 33, 83, 40)
    crown.closeSubpath()

    _plate(painter, crown, red_light, red_dark, DARK)

    # eyes: glow follows the light, narrow when blinking, scan while thinking
    eye_power = clamp(0.4 + 0.6 * m.light)

    narrow = 1.0 - 0.75 * m.blink

    shift = math.sin(t * 4) * 3 if m.state == "thinking" else 0.0

    eye_colour = QColor("#ffb347") if alert_blink else GLOW

    for sign in (-1, 1):

        ex = 100 + sign * 9 + shift

        _glow(painter, QPointF(ex, 49), 10, eye_colour, eye_power * 0.8)

        eye = QPainterPath()
        eye.moveTo(ex - sign * 7, 46 + (1 - narrow) * 2)
        eye.lineTo(ex + sign * 5, 47)
        eye.lineTo(ex + sign * 5, 47 + 5 * narrow)
        eye.lineTo(ex - sign * 6, 49 + 4 * narrow)
        eye.closeSubpath()

        painter.setPen(QPen(DARK, 1))
        painter.setBrush(QColor(eye_colour.red(), eye_colour.green(), eye_colour.blue(), int(120 + 135 * eye_power)))
        painter.drawPath(eye)

    # faceplate lines
    painter.setPen(QPen(DARK, 1.2))
    painter.drawLine(QPointF(100, 52), QPointF(100, 64))
    painter.drawLine(QPointF(94, 62), QPointF(106, 62))

    # the other arm in front of the torso
    _draw_arm(painter, m, -1, right, m.charge, alert_blink)

    # thinking: a ring of lights orbits the chest
    if m.state == "thinking":

        for i in range(4):

            angle = t * 2.6 + i * math.tau / 4

            x = 100 + math.cos(angle) * 46
            y = 112 + math.sin(angle) * 14 * 1.6

            _glow(painter, QPointF(x, y), 8, GLOW, 0.8)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)

    painter.restore()

    # sparks, thruster particles
    for p in m.particles:

        t_life = p.age / p.life

        if p.kind == "spark":

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(190, 240, 255, int(255 * (1 - t_life))))
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

    # the other agents, as dots over the head
    for i, color in enumerate((m.pips or [])[:6]):

        pulse = 0.5 + 0.5 * math.sin(t * 3 + i * 1.3)

        c = QColor(color)

        halo = QColor(c)
        halo.setAlpha(int(70 * pulse))

        x = 70 + i * 12
        y = 8

        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(x, y), 8, 8)

        painter.setBrush(c)
        painter.drawEllipse(QPointF(x, y), 4.5, 4.5)

    painter.restore()
