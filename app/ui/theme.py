"""
Colours and the Qt style sheet. One place, so the whole look can change
by editing this file.
"""

BG = "#0f1115"
PANEL = "#171a21"
INPUT_BG = "#1d212b"
BORDER = "#2a2f3c"
TEXT = "#e8eaf0"
MUTED = "#8b92a5"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#9279ff"
USER_BUBBLE = "#7c5cff"
BOT_BUBBLE = "#1d212b"
DANGER = "#ff5c6c"
OK = "#4cd8a0"

STYLE = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", sans-serif;
    font-size: 14px;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    border: none;
    background: {BG};
}}

QScrollBar:vertical {{
    background: {BG};
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QFrame#header {{
    background: {PANEL};
    border-bottom: 1px solid {BORDER};
}}

QLabel#title {{
    font-size: 16px;
    font-weight: 600;
    background: transparent;
}}

QLabel#status {{
    color: {MUTED};
    font-size: 12px;
    background: transparent;
}}

QFrame#bubble_user {{
    background: {USER_BUBBLE};
    border-radius: 14px;
}}
QFrame#bubble_user QLabel {{ background: transparent; color: white; }}

QFrame#bubble_bot {{
    background: {BOT_BUBBLE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#bubble_bot QLabel {{ background: transparent; }}

QFrame#bubble_note {{
    background: transparent;
}}
QFrame#bubble_note QLabel {{ color: {MUTED}; font-size: 12px; background: transparent; }}

QFrame#composer {{
    background: {PANEL};
    border-top: 1px solid {BORDER};
}}

QPlainTextEdit#input {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 8px 12px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit#input:focus {{ border: 1px solid {ACCENT}; }}

QPushButton {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 8px 14px;
}}
QPushButton:hover {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}

QPushButton#send {{
    background: {ACCENT};
    border: none;
    color: white;
    font-weight: 600;
    padding: 8px 18px;
}}
QPushButton#send:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#send:disabled {{ background: {BORDER}; color: {MUTED}; }}

QPushButton#icon {{ padding: 8px 10px; min-width: 22px; }}
QPushButton#icon:checked {{ background: {ACCENT}; border: none; color: white; }}
QPushButton#mic[listening="true"] {{ background: {DANGER}; border: none; color: white; }}

QPushButton#yes {{ background: {OK}; color: #06281c; border: none; font-weight: 600; }}
QPushButton#no {{ background: {INPUT_BG}; }}

QLineEdit {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}

QMenu {{
    background: {PANEL};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
"""
