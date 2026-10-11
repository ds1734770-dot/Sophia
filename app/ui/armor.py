"""
The armoured hero: a red and gold metallic powered suit with a glowing
arc reactor, drawn in code (an original design inspired by the comic-book
armoured hero, not official artwork). It uses the car's state machine, so
everything Sophia does shows up in it too:

    idle        hovers on its boot thrusters, eyes and reactor glow softly
    hover       waves
    listening   one hand raised, the reactor follows your voice
    thinking    eyes scan, a ring of lights orbits the chest, hand by the head
    speaking    both hands gesture, palms pulse with the voice
    alert       both palms and the reactor flash (also: an agent needs you)
    burst       a repulsor blast and a flash

and two sequences driven by the floating window:

    arrive      fly in on full thrust, brake with the palm repulsors, drop,
                touch down with a shockwave and dust, settle
    depart      crouch and charge the palms, then launch away
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

# metal: dark edge, bright highlight, mid, shadow, dark edge (across the part)
RED_STOPS = [(0.0, "#44060b"), (0.2, "#c8232a"), (0.38, "#ee3f39"), (0.6, "#b0151c"), (1.0, "#4e0a10")]
GOLD_STOPS = [(0.0, "#5e400a"), (0.2, "#dca127"), (0.38, "#fff6b8"), (0.6, "#d19a25"), (1.0, "#6e4a0d")]
STEEL_STOPS = [(0.0, "#101318"), (0.3, "#4a5260"), (0.5, "#8b95a5"), (0.75, "#353b46"), (1.0, "#101318")]

OUTLINE = QColor("#1a0b0d")
GLOW = QColor("#d6fbff")
ORANGE = QColor("#ff9a3c")

# the phases of the two sequences
THRUST = {"fly": 1.0, "brake": 0.85, "land": 0.35, "touch": 0.2, "charge": 0.25, "launch": 1.0}
LEAN = {"fly": 38.0, "brake": 6.0, "land": 0.0, "touch": 0.0, "charge": 0.0, "launch": 22.0}


def clamp(value, low=0.0, high=1.0):

    return max(low, min(high, value))


class ArmorModel(CarModel):
    """
    Same states and effects as the car, plus arm poses and the flight
    sequences.
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
        self.thrust = 0.0
        self.crouch = 0.0

        # arrive / depart sequences (set by the window)
        self.mode = None
        self.phase = ""
        self.shock = -1.0            # seconds since touchdown (-1: none)
        self.rings = 0.0             # palm repulsor rings while braking

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
    # Sequences
    # ------------------------------------------------

    def begin(self, mode):

        self.mode = mode
        self.phase = ""
        self.shock = -1.0

    def set_phase(self, phase):
        """
        Move to the next phase of arrive / depart (the window calls this
        as it moves the figure).
        """

        if phase == self.phase:
            return

        self.phase = phase

        if phase == "land":

            # the legs reach down for the ground
            self.charge = 0.6

        elif phase == "touch":
            self._touch_down()

    def _touch_down(self):
        """
        Landing: the knees take the weight, a shockwave and dust spread
        along the ground.
        """

        self.crouch = 1.0
        self.shock = 0.0
        self._bounce_velocity = -28.0
        self.flash_time = 0.0

        for _ in range(26):

            side = self.rng.choice((-1, 1))

            self.particles.append(Particle(
                100 + side * self.rng.uniform(6, 30), 266,
                side * self.rng.uniform(40, 150), self.rng.uniform(-26, -6),
                self.rng.uniform(0.5, 1.0), self.rng.uniform(4, 9), "dust",
            ))

        for _ in range(14):

            angle = self.rng.uniform(math.pi * 1.05, math.pi * 1.95)
            speed = self.rng.uniform(60, 180)

            self.particles.append(Particle(
                100, 262, math.cos(angle) * speed, math.sin(angle) * speed,
                self.rng.uniform(0.3, 0.7), self.rng.uniform(1.2, 2.6), "spark",
            ))

    def end_sequence(self):

        self.mode = None
        self.phase = ""

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

        # the flight sequences take over the arms
        phase = self.phase

        if phase == "fly" or phase == "launch":

            left = right = [-22.0, -4.0]

        elif phase == "brake":

            # palms down and out, firing against the fall
            left = right = [34.0, 6.0]

        elif phase == "land" or phase == "touch":

            left = right = [20.0, 14.0]

        elif phase == "charge":

            left = right = [30.0, 8.0]

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

        phase_time = (self.time % period) / period

        self.blink = 0.0 if phase_time < 0.94 else 1.0 - abs(phase_time - 0.97) / 0.03

        charge_target = {
            "idle": 0.1, "listening": 0.3 + 0.7 * self.level,
            "thinking": 0.35, "speaking": 0.3 + 0.6 * self.level, "alert": 0.9,
        }[self.state]

        if self.hover:
            charge_target = max(charge_target, 0.5)

        if self.phase in ("brake", "land", "charge"):
            charge_target = 1.0

        elif self.phase in ("fly", "launch"):
            charge_target = 0.35

        self.charge = approach(self.charge, charge_target, 7, dt)

        # lean and thrust
        if self.phase in LEAN:

            lean_target = LEAN[self.phase]
            thrust_target = THRUST[self.phase]

        else:

            lean_target = clamp(self.speed / 600, -1, 1) * 14
            thrust_target = clamp(0.25 + 0.5 * self.rev + abs(self.speed) / 350)

        self.lean = approach(self.lean, lean_target, 7, dt)
        self.thrust = approach(self.thrust, thrust_target, 8, dt)

        # the palm repulsors ring while braking
        self.rings = approach(self.rings, 1.0 if self.phase == "brake" else 0.0, 10, dt)

        # crouch: the legs take the landing, or load up for launch
        crouch_target = 0.0

        if self.phase == "charge":
            crouch_target = 0.8

        elif self.phase in ("touch",) or 0 <= self.shock < 0.25:
            crouch_target = 1.0

        self.crouch = approach(self.crouch, crouch_target, 14 if crouch_target else 6, dt)

        if self.shock >= 0:

            self.shock += dt

            if self.shock > 0.9:
                self.shock = -1.0

        # thruster sparks and exhaust while flying
        flying = self.phase in ("fly", "brake", "launch")

        if (flying or abs(self.speed) > 120) and self.rng.random() < 0.65:

            direction = -1.0 if self.facing > 0 else 1.0

            self.particles.append(Particle(
                100 + self.rng.uniform(-14, 14), 254,
                direction * self.rng.uniform(10, 60) * (1 if self.phase != "brake" else 0.2)
                + self.rng.uniform(-14, 14),
                self.rng.uniform(70, 150), self.rng.uniform(0.25, 0.55),
                self.rng.uniform(1.2, 2.6), "spark",
            ))


# ---------------------------------------------------------------
# Drawing helpers
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


def _path(*segments):
    """
    A closed polygon through (x, y) points.
    """

    path = QPainterPath()
    path.moveTo(*segments[0])

    for point in segments[1:]:
        path.lineTo(*point)

    path.closeSubpath()

    return path


def _round(x, y, w, h, r):

    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)

    return path


def _metal(painter, m, path, kind="red", direction="h", shine=True, edge=1.1):
    """
    Fill a part with brushed-metal shading: dark edges, a bright band,
    a shadow band and a glossy highlight along the top. Red parts follow
    the agent's colour.
    """

    stops = {"red": RED_STOPS, "gold": GOLD_STOPS, "steel": STEEL_STOPS}[kind]

    box = path.boundingRect()

    if direction == "h":
        gradient = QLinearGradient(box.left(), 0, box.right(), 0)

    elif direction == "v":
        gradient = QLinearGradient(0, box.top(), 0, box.bottom())

    else:
        gradient = QLinearGradient(box.topLeft(), box.bottomRight())

    for position, color in stops:

        c = QColor(color)

        gradient.setColorAt(position, tc(m, c) if kind == "red" else c)

    painter.setBrush(QBrush(gradient))
    painter.setPen(QPen(OUTLINE, edge))
    painter.drawPath(path)

    if shine:

        painter.save()
        painter.setClipPath(path)

        gloss = QLinearGradient(0, box.top(), 0, box.top() + box.height() * 0.45)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 72))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gloss))
        painter.drawRect(box)

        painter.restore()


def _line(painter, color, width, *points):

    painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)

    for a, b in zip(points, points[1:]):
        painter.drawLine(QPointF(*a), QPointF(*b))


def _thruster(painter, cx, cy, power, t, seed):

    flicker = 0.86 + 0.14 * math.sin(t * 41 + seed)

    power = clamp(power) * flicker

    _glow(painter, QPointF(cx, cy + 2), 8 + 14 * power, GLOW, 0.35 + 0.55 * power)

    if power > 0.05:

        length = 6 + 34 * power

        path = QPainterPath()
        path.moveTo(cx - 6.5, cy)
        path.lineTo(cx + 6.5, cy)
        path.lineTo(cx, cy + length)
        path.closeSubpath()

        gradient = QLinearGradient(cx, cy, cx, cy + length)
        gradient.setColorAt(0.0, QColor(245, 253, 255, 250))
        gradient.setColorAt(0.35, QColor(140, 220, 255, 200))
        gradient.setColorAt(1.0, QColor(50, 110, 255, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)


def _draw_leg(painter, m, cx, power, seed):

    # thigh
    _metal(painter, m, _round(cx - 14, 164, 28, 44, 11), "red", "h")

    # gold knee shield
    knee = QPainterPath()
    knee.moveTo(cx - 12.5, 204)
    knee.quadTo(cx, 197, cx + 12.5, 204)
    knee.lineTo(cx + 10, 218)
    knee.quadTo(cx, 224, cx - 10, 218)
    knee.closeSubpath()

    _metal(painter, m, knee, "gold", "h")

    # shin guard: gold, flared at the calf
    shin = _path((cx - 12.5, 218), (cx + 12.5, 218), (cx + 9.5, 249), (cx - 9.5, 249))

    _metal(painter, m, shin, "gold", "h")

    # red stripe down the shin
    _metal(painter, m, _round(cx - 3, 221, 6, 26, 3), "red", "h", shine=False, edge=0.8)

    # boot
    _metal(painter, m, _round(cx - 13, 247, 26, 13, 6), "red", "v")
    _metal(painter, m, _round(cx - 13.5, 257, 27, 5, 2), "steel", "v", shine=False, edge=0.8)

    _thruster(painter, cx, 263, power, m.time, seed)


def _draw_arm(painter, m, side, pose, charge, flash, rings):
    """
    side: -1 for the figure's right arm (screen right), +1 for the left.
    pose: [upper, bend] degrees, positive = outward and up.
    """

    upper, bend = pose

    painter.save()
    painter.translate(QPointF(100 - side * 47, 80))

    painter.rotate(-upper if side < 0 else upper)

    # upper arm: red, with a gold band
    _metal(painter, m, _round(-10, -2, 20, 35, 9), "red", "h")
    _metal(painter, m, _round(-10.3, 11, 20.6, 5, 2), "gold", "h", shine=False, edge=0.8)

    # elbow joint
    painter.translate(0, 32)

    painter.setPen(QPen(OUTLINE, 1))
    painter.setBrush(QColor("#2d323b"))
    painter.drawEllipse(QPointF(0, 0), 7.2, 6.2)

    painter.rotate(-bend if side < 0 else bend)

    # forearm gauntlet: gold, wider at the wrist
    gauntlet = _path((-9.5, 0), (9.5, 0), (12, 32), (-12, 32))

    _metal(painter, m, gauntlet, "gold", "h")
    _metal(painter, m, _round(-4, 4, 8, 22, 3), "red", "h", shine=False, edge=0.8)

    # hand: red glove with the repulsor disc
    painter.translate(0, 34)

    _metal(painter, m, _round(-9, -1, 18, 15, 7), "red", "v")

    colour = ORANGE if flash else GLOW

    _glow(painter, QPointF(0, 7), 11 + 12 * charge, colour, 0.25 + 0.75 * charge)

    painter.setPen(QPen(OUTLINE, 1))
    painter.setBrush(QColor("#c99a2a"))
    painter.drawEllipse(QPointF(0, 7), 5.6, 5.6)

    painter.setBrush(colour if charge > 0.25 else QColor("#6f8088"))
    painter.drawEllipse(QPointF(0, 7), 3.8, 3.8)

    # repulsor rings pulse outward from the palm while braking
    if rings > 0.05:

        for i in range(3):

            grow = (m.time * 3.4 + i / 3) % 1.0

            ring = QColor(GLOW)
            ring.setAlpha(int(200 * rings * (1 - grow)))

            painter.setPen(QPen(ring, 1.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 10 + 14 * grow), 6 + 16 * grow, 2.5 + 6 * grow)

    painter.restore()


def _draw_head(painter, m, t, eye_power, narrow, shift, eye_colour):

    # helmet shell and ear plates behind the face
    _metal(painter, m, _round(80.5, 31, 39, 27, 11), "red", "h")

    # faceplate
    face = QPainterPath()
    face.moveTo(86, 27)
    face.quadTo(100, 21, 114, 27)
    face.lineTo(116, 43)
    face.quadTo(115, 53, 108, 59)
    face.lineTo(100, 64)
    face.lineTo(92, 59)
    face.quadTo(85, 53, 84, 43)
    face.closeSubpath()

    _metal(painter, m, face, "gold", "h")

    # the red crown with its centre ridge
    crown = QPainterPath()
    crown.moveTo(83.5, 36)
    crown.quadTo(82, 19, 100, 15)
    crown.quadTo(118, 19, 116.5, 36)
    crown.quadTo(100, 27, 83.5, 36)
    crown.closeSubpath()

    _metal(painter, m, crown, "red", "h")

    _line(painter, QColor("#e9b432"), 1.8, (100, 16.5), (100, 27))

    # cheek and jaw seams
    _line(painter, QColor(26, 11, 13, 190), 1.0, (88, 44), (92, 56), (100, 62))
    _line(painter, QColor(26, 11, 13, 190), 1.0, (112, 44), (108, 56), (100, 62))

    # eye slits: angled, glowing, narrowing on a blink
    for sign in (-1, 1):

        ex = 100 + sign * 9 + shift

        _glow(painter, QPointF(ex, 41.5), 11, eye_colour, eye_power * 0.85)

        slit = QPainterPath()
        slit.moveTo(100 + sign * 3 + shift, 41 + (1 - narrow) * 1.5)
        slit.lineTo(100 + sign * 14 + shift, 37.2 + (1 - narrow) * 1.5)
        slit.lineTo(100 + sign * 14 + shift, 37.2 + 3.6 * narrow + (1 - narrow) * 1.5)
        slit.lineTo(100 + sign * 3 + shift, 43.6 + (1 - narrow) * 0.5)
        slit.closeSubpath()

        painter.setPen(QPen(OUTLINE, 0.9))
        painter.setBrush(QColor(
            eye_colour.red(), eye_colour.green(), eye_colour.blue(),
            int(130 + 125 * eye_power),
        ))
        painter.drawPath(slit)

    # nose ridge and the mouth grille
    _line(painter, QColor(26, 11, 13, 170), 1.0, (100, 44), (100, 50))

    for i in range(3):

        y = 54 + i * 2.6
        half = 6 - i * 1.2

        _line(painter, QColor(26, 11, 13, 200), 0.9, (100 - half, y), (100 + half, y))


def _draw_chest(painter, m, t, alert_blink):

    # main chest plate
    chest = QPainterPath()
    chest.moveTo(53, 72)
    chest.quadTo(100, 62, 147, 72)
    chest.lineTo(134, 115)
    chest.quadTo(100, 130, 66, 115)
    chest.closeSubpath()

    _metal(painter, m, chest, "red", "d")

    # gold pectoral plates
    for sign in (-1, 1):

        pec = _path(
            (100 + sign * 6, 77), (100 + sign * 37, 75),
            (100 + sign * 33, 98), (100 + sign * 9, 102),
        )

        _metal(painter, m, pec, "gold", "d")

    # collarbone line
    _line(painter, QColor(255, 220, 120, 200), 1.4, (62, 75), (100, 69), (138, 75))

    # abdomen: stacked gold plates
    for i, (y, w) in enumerate(((122, 40), (131, 36), (140, 32))):

        _metal(painter, m, _round(100 - w / 2, y, w, 8, 3), "gold", "v", shine=False, edge=0.9)

    # belt and hips
    _metal(painter, m, _round(70, 150, 60, 18, 8), "red", "v")
    _metal(painter, m, _round(91, 152, 18, 13, 5), "gold", "d")

    # the arc reactor
    pulse = 0.5 + 0.5 * math.sin(t * (6 if m.state == "thinking" else 3))

    power = clamp(0.35 + 0.45 * m.light + 0.2 * pulse)

    colour = ORANGE if alert_blink else GLOW

    _glow(painter, QPointF(100, 94), 28 + 10 * m.charge, colour, power * 0.9)

    # housing ring
    ring = QRadialGradient(QPointF(98, 92), 16)
    ring.setColorAt(0.0, QColor("#fff1a8"))
    ring.setColorAt(0.6, QColor("#c99320"))
    ring.setColorAt(1.0, QColor("#6e4a0d"))

    painter.setPen(QPen(OUTLINE, 1.4))
    painter.setBrush(QBrush(ring))
    painter.drawEllipse(QPointF(100, 94), 15, 15)

    painter.setBrush(QColor("#1d2229"))
    painter.drawEllipse(QPointF(100, 94), 11.5, 11.5)

    # coil segments around the core
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#59626f"))

    for i in range(10):

        angle = i * math.tau / 10 + 0.31

        painter.save()
        painter.translate(100 + math.cos(angle) * 8.6, 94 + math.sin(angle) * 8.6)
        painter.rotate(math.degrees(angle) + 90)
        painter.drawRect(QRectF(-1.5, -2.2, 3, 4.4))
        painter.restore()

    painter.setBrush(colour)
    painter.drawEllipse(QPointF(100, 94), 6, 6)

    painter.setBrush(QColor(255, 255, 255, int(170 + 85 * power)))
    painter.drawEllipse(QPointF(100, 94), 3.2, 3.2)


def _draw_shoulder(painter, m, x):

    pad = QPainterPath()
    pad.moveTo(x - 18, 84)
    pad.quadTo(x - 18, 63, x, 62)
    pad.quadTo(x + 18, 63, x + 18, 84)
    pad.quadTo(x, 90, x - 18, 84)
    pad.closeSubpath()

    _metal(painter, m, pad, "red", "d")

    # gold edge band and rivet
    _metal(painter, m, _round(x - 17, 82, 34, 6, 3), "gold", "h", shine=False, edge=0.9)

    painter.setPen(QPen(OUTLINE, 0.8))
    painter.setBrush(QColor("#fff0a0"))
    painter.drawEllipse(QPointF(x, 74), 2.2, 2.2)


# ---------------------------------------------------------------
# The figure
# ---------------------------------------------------------------

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

    # face the other way by mirroring
    if m.facing < 0:

        painter.translate(ARMOR_W, 0)
        painter.scale(-1, 1)

    painter.translate(30, 0)

    t = m.time

    # hover: a gentle bob, higher while the engines work (none on the ground)
    on_ground = m.mode is None and m.crouch > 0.5

    bob = 0.0 if on_ground else math.sin(t * 2.0) * 3.0 - 6.0 - 4.0 * m.rev

    # ---- ground shadow, and the landing shockwave
    if with_ground:

        shadow = QRadialGradient(QPointF(100, 272), 60)
        shadow.setColorAt(0.0, QColor(0, 0, 0, int(120 - 40 * m.rev)))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))

        painter.save()
        painter.translate(100, 272)
        painter.scale(1, 0.16)
        painter.translate(-100, -272)
        painter.drawEllipse(QPointF(100, 272), 60, 60)
        painter.restore()

    if m.shock >= 0:

        spread = m.shock / 0.9

        ring = QColor(210, 235, 255, int(190 * (1 - spread) ** 1.5))

        painter.setPen(QPen(ring, 3 * (1 - spread) + 0.8))
        painter.setBrush(Qt.NoBrush)

        painter.save()
        painter.translate(100, 268)
        painter.scale(1, 0.18)
        painter.drawEllipse(QPointF(0, 0), 14 + 118 * spread ** 0.7, 14 + 118 * spread ** 0.7)
        painter.restore()

    # ---- the figure itself
    painter.save()

    painter.translate(m.vibration, m.bounce + bob)

    # the knees take the landing: squash from the feet
    crouch = clamp(m.crouch)

    painter.translate(100, 262)
    painter.scale(1 + 0.05 * crouch, 1 - 0.1 * crouch)
    painter.translate(-100, -262)

    # lean into the flight, pivoting at the hips
    painter.translate(100, 160)
    painter.rotate(m.lean)
    painter.translate(-100, -160)

    power = clamp(m.thrust)

    _draw_leg(painter, m, 84, power, 0.0)
    _draw_leg(painter, m, 116, power * 0.96, 1.7)

    alert_blink = m.hazard

    left, right = m.left, m.right

    # the left arm sits behind the torso
    _draw_arm(painter, m, +1, left, m.charge * 0.6, alert_blink, m.rings)

    _draw_chest(painter, m, t, alert_blink)

    # neck, shoulders
    _metal(painter, m, _round(92, 58, 16, 12, 3), "steel", "h", shine=False)

    _draw_shoulder(painter, m, 54)
    _draw_shoulder(painter, m, 146)

    # head
    eye_power = clamp(0.45 + 0.55 * m.light + (0.25 if m.phase in ("fly", "launch") else 0))

    narrow = 1.0 - 0.75 * m.blink

    shift = math.sin(t * 4) * 3 if m.state == "thinking" else 0.0

    eye_colour = ORANGE if alert_blink else GLOW

    _draw_head(painter, m, t, eye_power, narrow, shift, eye_colour)

    # the right arm in front
    _draw_arm(painter, m, -1, right, m.charge, alert_blink, m.rings)

    # thinking: a ring of lights orbits the chest
    if m.state == "thinking":

        for i in range(4):

            angle = t * 2.6 + i * math.tau / 4

            x = 100 + math.cos(angle) * 48
            y = 96 + math.sin(angle) * 22

            _glow(painter, QPointF(x, y), 8, GLOW, 0.8)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)

    painter.restore()

    # ---- particles: sparks, landing dust
    for p in m.particles:

        life = p.age / p.life

        painter.setPen(Qt.NoPen)

        if p.kind == "spark":

            painter.setBrush(QColor(190, 240, 255, int(255 * (1 - life))))
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

        elif p.kind == "dust":

            painter.setBrush(QColor(200, 196, 190, int(150 * (1 - life))))
            painter.drawEllipse(QPointF(p.x, p.y), p.size * (1 + life * 1.6), p.size * (0.7 + life))

    # ---- the other agents, as dots over the head
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
