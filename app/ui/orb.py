"""
Sophia's living avatar: a glowing orb that reacts to what is happening.

OrbModel holds the animation state and physics (no Qt, so it is easy to
test); OrbWidget draws it.

States: idle (slow breathing), listening (ripples that follow your
voice), thinking (orbiting sparks), speaking (pulsing rings) and alert
(a bounce). Short effects: burst (success sparkle) and shake (error).
"""

import math
import random

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

# state -> (core colour, glow colour)
PALETTES = {
    "idle": ("#7c5cff", "#4c7dff"),
    "listening": ("#27d3a2", "#2ab8ff"),
    "thinking": ("#a259ff", "#ff5cc8"),
    "speaking": ("#7c5cff", "#35c7ff"),
    "alert": ("#ffb347", "#ff6b6b"),
}

STATES = tuple(PALETTES)


def hex_to_rgb(value):

    value = value.lstrip("#")

    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def approach(current, target, rate, dt):
    """
    Move `current` toward `target`, smoothly (exponential easing).
    """

    return current + (target - current) * (1 - math.exp(-rate * dt))


class Particle:

    __slots__ = ("x", "y", "vx", "vy", "life", "age", "size")

    def __init__(self, x, y, vx, vy, life, size):

        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life, self.age, self.size = life, 0.0, size


class OrbModel:

    def __init__(self, seed=None):

        self.rng = random.Random(seed)

        self.state = "idle"

        # eased values
        self.color1 = list(hex_to_rgb(PALETTES["idle"][0]))
        self.color2 = list(hex_to_rgb(PALETTES["idle"][1]))
        self.energy = 0.0          # 0..1, how animated the orb is
        self.level = 0.0           # 0..1, voice or speech loudness
        self.gaze = [0.0, 0.0]     # -1..1, where the orb looks

        self._level_target = 0.0
        self._gaze_target = [0.0, 0.0]

        # clocks
        self.time = 0.0
        self.breath = 0.0
        self.spin = 0.0

        # one-off effects
        self.bounce = 0.0
        self.bounce_velocity = 0.0
        self.shake_time = 0.0
        self.rings = []             # ages of expanding rings
        self.particles = []
        self._ring_timer = 0.0

    # ------------------------------------------------

    def set_state(self, state):

        if state not in PALETTES:
            raise ValueError(f"unknown orb state '{state}'")

        self.state = state

    def set_level(self, level):

        self._level_target = max(0.0, min(1.0, float(level)))

    def look_at(self, x, y):

        self._gaze_target = [
            max(-1.0, min(1.0, x)),
            max(-1.0, min(1.0, y)),
        ]

    def kick(self, kind):
        """
        A short effect: "bounce", "burst" or "shake".
        """

        if kind == "bounce":

            self.bounce_velocity = -4.5

        elif kind == "shake":

            self.shake_time = 0.5

        elif kind == "burst":

            self.bounce_velocity = -2.0

            for i in range(22):

                angle = self.rng.uniform(0, math.tau)
                speed = self.rng.uniform(0.5, 1.4)

                self.particles.append(
                    Particle(
                        0.0, 0.0,
                        math.cos(angle) * speed, math.sin(angle) * speed,
                        self.rng.uniform(0.6, 1.1),
                        self.rng.uniform(0.02, 0.05),
                    )
                )

        else:

            raise ValueError(f"unknown effect '{kind}'")

    # ------------------------------------------------

    def step(self, dt):
        """
        Advance the animation by dt seconds.
        """

        dt = max(0.0, min(dt, 0.1))

        self.time += dt

        # colours ease toward the state's palette
        target1, target2 = (hex_to_rgb(c) for c in PALETTES[self.state])

        for i in range(3):

            self.color1[i] = approach(self.color1[i], target1[i], 6, dt)
            self.color2[i] = approach(self.color2[i], target2[i], 6, dt)

        # how lively the orb is in each state
        energy_target = {
            "idle": 0.15, "listening": 0.6, "thinking": 0.75,
            "speaking": 0.7, "alert": 0.9,
        }[self.state]

        self.energy = approach(self.energy, energy_target, 4, dt)
        self.level = approach(self.level, self._level_target, 14, dt)

        for i in range(2):
            self.gaze[i] = approach(self.gaze[i], self._gaze_target[i], 8, dt)

        # breathing is slower when calm
        self.breath += dt * (1.2 + 2.2 * self.energy)
        self.spin += dt * (0.6 + 4.0 * (self.state == "thinking"))

        # bounce is a damped spring
        accel = -60 * self.bounce - 7 * self.bounce_velocity
        self.bounce_velocity += accel * dt
        self.bounce += self.bounce_velocity * dt

        self.shake_time = max(0.0, self.shake_time - dt)

        # expanding rings while listening or speaking
        self._ring_timer -= dt

        if self.state in ("listening", "speaking") and self._ring_timer <= 0:

            if self.level > 0.08 or self.state == "speaking":
                self.rings.append(0.0)

            self._ring_timer = 0.55 - 0.3 * self.level

        self.rings = [a + dt for a in self.rings if a + dt < 1.2]

        for p in self.particles:

            p.age += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 0.9 * dt

        self.particles = [p for p in self.particles if p.age < p.life]

    # ------------------------------------------------

    @property
    def radius_scale(self):
        """
        1.0 at rest: breathing, voice level and bounce change it.
        """

        breathing = 0.035 * math.sin(self.breath) * (0.5 + self.energy)

        return 1.0 + breathing + 0.12 * self.level + 0.18 * self.bounce

    @property
    def shake_offset(self):

        if self.shake_time <= 0:
            return 0.0

        return math.sin(self.time * 60) * 0.04 * (self.shake_time / 0.5)

    def rgb(self, which):

        values = self.color1 if which == 1 else self.color2

        return tuple(int(max(0, min(255, v))) for v in values)


class OrbWidget(QWidget):
    """
    Draws an OrbModel. Click to talk, double-click to stop speaking.
    """

    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, model, size=180):

        super().__init__()

        self.model = model

        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to talk. Double-click to stop speaking.")
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_orb_size(self, size):

        self.setFixedSize(size, size)

    def mouseReleaseEvent(self, event):

        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, event):

        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()

    # ------------------------------------------------

    def paintEvent(self, event):

        m = self.model

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())

        center = QPointF(
            self.width() / 2 + m.shake_offset * side,
            self.height() / 2,
        )

        base = side * (0.27 if side > 100 else 0.32)
        radius = base * m.radius_scale

        c1 = QColor(*m.rgb(1))
        c2 = QColor(*m.rgb(2))

        # soft outer glow
        glow = QRadialGradient(center, side * 0.5)

        glow_color = QColor(c2)
        glow_color.setAlphaF(0.30 + 0.25 * m.energy)

        glow.setColorAt(0.0, glow_color)
        glow.setColorAt(0.55, QColor(c2.red(), c2.green(), c2.blue(), int(30 + 40 * m.energy)))
        glow.setColorAt(1.0, QColor(c2.red(), c2.green(), c2.blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, side * 0.5, side * 0.5)

        # expanding rings
        for age in m.rings:

            progress = age / 1.2

            ring = QColor(c2)
            ring.setAlphaF(max(0.0, 0.55 * (1 - progress)))

            painter.setPen(QPen(ring, max(1.0, side * 0.012)))
            painter.setBrush(Qt.NoBrush)

            r = radius * (1.05 + 0.9 * progress)

            painter.drawEllipse(center, r, r)

        # thinking: orbiting sparks
        if m.state == "thinking" or m.energy > 0.7:

            for i in range(5):

                angle = m.spin * (1 + i * 0.15) + i * math.tau / 5

                orbit = radius * (1.35 + 0.08 * math.sin(m.time * 2 + i))

                spark = QColor(255, 255, 255, int(160 * min(1.0, m.energy)))

                painter.setPen(Qt.NoPen)
                painter.setBrush(spark)

                painter.drawEllipse(
                    QPointF(
                        center.x() + math.cos(angle) * orbit,
                        center.y() + math.sin(angle) * orbit * 0.55,
                    ),
                    side * 0.012, side * 0.012,
                )

        # the orb
        body = QRadialGradient(
            QPointF(
                center.x() - radius * 0.3 + m.gaze[0] * radius * 0.35,
                center.y() - radius * 0.35 + m.gaze[1] * radius * 0.35,
            ),
            radius * 1.4,
        )

        light = QColor(
            min(255, c1.red() + 90), min(255, c1.green() + 90), min(255, c1.blue() + 90)
        )

        body.setColorAt(0.0, light)
        body.setColorAt(0.45, c1)
        body.setColorAt(1.0, QColor(c2.red() // 2, c2.green() // 2, c2.blue() // 2))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(body))
        painter.drawEllipse(center, radius, radius)

        # glossy highlight that follows the gaze
        highlight = QColor(255, 255, 255, 120)

        painter.setBrush(highlight)
        painter.drawEllipse(
            QPointF(
                center.x() - radius * 0.32 + m.gaze[0] * radius * 0.2,
                center.y() - radius * 0.38 + m.gaze[1] * radius * 0.2,
            ),
            radius * 0.22, radius * 0.13,
        )

        # success sparkles
        for p in m.particles:

            alpha = max(0.0, 1.0 - p.age / p.life)

            spark = QColor(255, 244, 200, int(255 * alpha))

            painter.setBrush(spark)

            painter.drawEllipse(
                QPointF(center.x() + p.x * side * 0.5, center.y() + p.y * side * 0.5),
                side * p.size * alpha, side * p.size * alpha,
            )

        painter.end()
