"""
Colours and the Qt style sheet. One place, so the whole look can change
by editing this file.

The look follows the yellow car: near-black surfaces with a warm amber
accent, soft borders, and cards for what the assistant is doing.
"""

BG = "#0b0d12"
PANEL = "#10131a"
SURFACE = "#151922"
INPUT_BG = "#151922"
BORDER = "#252b38"
BORDER_SOFT = "#1b2029"
TEXT = "#e9ebf2"
MUTED = "#8a93a6"
ACCENT = "#ffb800"
ACCENT_HOVER = "#ffc933"
ACCENT_DARK = "#1b1400"
ACCENT_GLOW = "rgba(255, 184, 0, 0.14)"
USER_BUBBLE = "#ffb800"
BOT_BUBBLE = SURFACE
DANGER = "#ff6b6b"
OK = "#3ddc97"

STYLE = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 14px;
}}

QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    border: none;
    background: {BG};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #343c4d; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ---------- header ---------- */

QFrame#header {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #161a24, stop:0.6 {PANEL}, stop:1 {BG});
    border-bottom: 1px solid {BORDER_SOFT};
}}
QFrame#header QWidget {{ background: transparent; }}

QLabel#title {{
    font-size: 17px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}

QLabel#badge {{
    color: {ACCENT};
    background: {ACCENT_GLOW};
    border: 1px solid rgba(255, 184, 0, 0.35);
    border-radius: 8px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: 700;
}}

QLabel#status {{
    color: {MUTED};
    font-size: 12px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 4px 12px 4px 24px;
}}
QLabel#status[state="working"] {{ color: {ACCENT}; border-color: rgba(255, 184, 0, 0.35); }}
QLabel#status[state="listening"] {{ color: {OK}; border-color: rgba(61, 220, 151, 0.35); }}
QLabel#status[state="problem"] {{ color: {DANGER}; border-color: rgba(255, 107, 107, 0.35); }}

/* ---------- messages ---------- */

QFrame#bubble_user {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ffc21a, stop:1 #f59e0b);
    border-radius: 16px;
    border-bottom-right-radius: 5px;
}}
QFrame#bubble_user QLabel {{ background: transparent; color: {ACCENT_DARK}; font-weight: 500; }}

QFrame#bubble_bot {{
    background: {BOT_BUBBLE};
    border: 1px solid {BORDER};
    border-radius: 16px;
    border-top-left-radius: 5px;
}}
QFrame#bubble_bot QLabel {{ background: transparent; }}

QFrame#bubble_note {{
    background: {SURFACE};
    border: 1px solid {BORDER_SOFT};
    border-left: 3px solid {ACCENT};
    border-radius: 10px;
}}
QFrame#bubble_note QLabel {{ color: {TEXT}; font-size: 13px; background: transparent; }}

QPushButton#copy {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0;
    font-size: 11px;
    color: {MUTED};
}}
QPushButton#copy:hover {{ color: {ACCENT}; border-color: {ACCENT}; }}

/* ---------- what she is doing ---------- */

QFrame#steps {{
    background: {PANEL};
    border: 1px solid {BORDER_SOFT};
    border-left: 3px solid {ACCENT};
    border-radius: 12px;
}}
QFrame#steps QWidget {{ background: transparent; }}
QLabel#steps_title {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QLabel#step_text {{ color: #c9cedb; font-size: 13px; }}
QLabel#step_time {{ color: {MUTED}; font-size: 11px; }}

/* ---------- composer ---------- */

QFrame#composer {{
    background: {BG};
    border-top: 1px solid {BORDER_SOFT};
}}

QPlainTextEdit#input {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 18px;
    padding: 10px 16px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_DARK};
}}
QPlainTextEdit#input:focus {{
    border: 1px solid {ACCENT};
    background: #181c26;
}}

QPushButton {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 8px 14px;
}}
QPushButton:hover {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}

QPushButton#send {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ffc21a, stop:1 #f59e0b);
    border: none;
    border-radius: 18px;
    color: {ACCENT_DARK};
    font-weight: 700;
    padding: 9px 22px;
}}
QPushButton#send:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#send:disabled {{ background: {BORDER}; color: {MUTED}; }}

QPushButton#icon {{ padding: 8px 10px; min-width: 22px; border-radius: 14px; }}
QPushButton#icon:checked {{ background: {ACCENT}; border: none; color: {ACCENT_DARK}; }}

QPushButton#mic {{ border-radius: 18px; padding: 9px 11px; }}
QPushButton#mic[listening="true"] {{ background: {DANGER}; border: none; color: white; }}

QPushButton#yes {{ background: {OK}; color: #06281c; border: none; font-weight: 700; border-radius: 12px; }}
QPushButton#no {{ background: {INPUT_BG}; border-radius: 12px; }}

QLineEdit {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}

/* ---------- welcome ---------- */

QFrame#hero {{
    background: transparent;
}}
QLabel#hero_title {{
    font-size: 28px;
    font-weight: 700;
    background: transparent;
}}
QLabel#hero_subtitle {{
    color: {MUTED};
    font-size: 14px;
    background: transparent;
}}

QPushButton#chip {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 12px 16px;
    color: {TEXT};
    text-align: left;
}}
QPushButton#chip:hover {{
    border: 1px solid {ACCENT};
    background: #1b2030;
}}
QPushButton#chip:pressed {{ background: {ACCENT}; color: {ACCENT_DARK}; }}

QMenu {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: {ACCENT_DARK}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
"""
