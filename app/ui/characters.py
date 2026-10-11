"""
The appearances Sophia can have. Each is a model (the same states and
effects, its own drawing and size) plus the sizes used in the chat window.
"""

from app.ui.armor import ArmorModel
from app.ui.car import CarModel

DEFAULT_CHARACTER = "car"

CHARACTERS = {
    "car": {
        "label": "Sports car",
        "model": CarModel,
        "hero": (220, 78),      # welcome screen
        "mini": (110, 40),      # chat header
    },
    "armor": {
        "label": "Iron Man armor",
        "model": ArmorModel,
        "hero": (112, 122),
        "mini": (38, 42),
    },
}


def valid(name):

    return name if name in CHARACTERS else DEFAULT_CHARACTER


def make_model(name):

    return CHARACTERS[valid(name)]["model"]()
