import logging
from logging.handlers import RotatingFileHandler

from app.settings.paths import LOGS_DIR

_configured = False


def setup_logging(debug=False):
    """
    Log to data/logs/sophia.log (rotating, 3 x 512 KB). Safe to call
    more than once.
    """

    global _configured

    if _configured:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        LOGS_DIR / "sophia.log",
        maxBytes=512 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root = logging.getLogger("sophia")
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(handler)

    _configured = True
