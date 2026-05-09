#!/usr/bin/env python3
"""
Terminal Text Rotator
Cycles through text snippets every minute with configurable font styles and positioning.
Controls:
  n / p   - next / previous text manually
  f       - cycle font style
  a       - cycle alignment (left / center / right)
  v       - cycle vertical position (top / middle / bottom)
  e       - edit current text inline
  +/-     - increase / decrease interval (in seconds)
  q       - quit
"""

import curses
import time
import threading

# ── Configuration ──────────────────────────────────────────────────────────────

TEXTS = [
    "The quick brown fox jumps over the lazy dog.",
    "To be, or not to be — that is the question.",
    "All that glitters is not gold.",
    "In the beginning was the Word.",
    "Not all those who wander are lost.",
    "It was the best of times, it was the worst of times.",
]

FONT_STYLES = [
    ("Normal",    curses.A_NORMAL),
    ("Bold",      curses.A_BOLD),
    ("Dim",       curses.A_DIM),
    ("Underline", curses.A_UNDERLINE),
    ("Reverse",   curses.A_REVERSE),
    ("Blink",     curses.A_BLINK),
    ("Bold+Underline", curses.A_BOLD | curses.A_UNDERLINE),
    ("Bold+Reverse",   curses.A_BOLD | curses.A_REVERSE),
]

ALIGNMENTS   = ["left", "center", "right"]
V_POSITIONS  = ["top", "middle", "bottom"]
DEFAULT_INTERVAL = 60   # seconds


# ── State ──────────────────────────────────────────────────────────────────────

state = {
    "text_idx":    0,
    "style_idx":   1,          # Bold by default
    "align_idx":   1,          # center
    "vpos_idx":    1,          # middle
    "interval":    DEFAULT_INTERVAL,
    "countdown":   DEFAULT_INTERVAL,
    "texts":       list(TEXTS),
    "dirty":       True,       # force redraw
    "editing":     False,
    "edit_buf":    "",
}

lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────────

def compute_xy(stdscr, text, align, vpos):
    """Return (y, x) for the text given alignment and vertical position."""
    rows, cols = stdscr.getmaxyx()
    text_len   = len(text)

    if align == "left":
        x = 1
    elif align == "right":
        x = max(1, cols - text_len - 1)
    else:                          # center
        x = max(1, (cols - text_len) // 2)

    if vpos == "top":
        y = 1
    elif vpos == "bottom":
        y = max(1, rows - 4)
    else:                          # middle
        y = max(1, (rows - 1) // 2)

    return y, x


def wrap_text(text, max_width):
    """Simple word-wrap: returns list of lines."""
    words  = text.split()
    lines  = []
    current = ""
    for w in words:
        if current:
            candidate = current + " " + w
        else:
            candidate = w
        if len(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w[:max_width]
    if current:
        lines.append(current)
    return lines or [""]


def draw_screen(stdscr, s):
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()

    # ── border ──
    try:
        stdscr.border()
    except curses.error:
        pass

    # ── current text ──
    text       = s["texts"][s["text_idx"]]
    style_name, style_attr = FONT_STYLES[s["style_idx"]]
    align      = ALIGNMENTS[s["align_idx"]]
    vpos       = V_POSITIONS[s["vpos_idx"]]

    max_w      = max(10, cols - 4)
    lines      = wrap_text(text, max_w)
    base_y, _  = compute_xy(stdscr, lines[0], align, vpos)

    for i, line in enumerate(lines):
        if align == "left":
            x = 2
        elif align == "right":
            x = max(2, cols - len(line) - 2)
        else:
            x = max(2, (cols - len(line)) // 2)
        y = base_y + i
        if 0 < y < rows - 1:
            try:
                stdscr.addstr(y, x, line, style_attr)
            except curses.error:
                pass

    # ── status bar (bottom) ──
    bar_y = rows - 2
    if bar_y > 0:
        interval   = s["interval"]
        countdown  = max(0, s["countdown"])
        status = (
            f" [{s['text_idx']+1}/{len(s['texts'])}] "
            f"Style:{style_name}  "
            f"Align:{align}  "
            f"Pos:{vpos}  "
            f"Next:{countdown}s/{interval}s "
        )
        status = status[:cols - 2]
        try:
            stdscr.addstr(bar_y, 1, status, curses.A_DIM)
        except curses.error:
            pass

    # ── help bar (very bottom) ──
    help_y = rows - 1
    if help_y > 0:
        help_str = " n/p:next/prev  f:font  a:align  v:vpos  e:edit  +/-:speed  q:quit "
        help_str = help_str[:cols - 2]
        try:
            stdscr.addstr(help_y, 0, help_str, curses.A_REVERSE)
        except curses.error:
            pass

    # ── edit mode overlay ──
    if s["editing"]:
        prompt = f" Edit text (Enter=save, Esc=cancel): {s['edit_buf']}_"
        mid_y  = rows // 2
        try:
            stdscr.addstr(mid_y, 1, prompt[:cols - 2], curses.A_BOLD | curses.A_REVERSE)
        except curses.error:
            pass

    stdscr.refresh()


# ── Countdown thread ───────────────────────────────────────────────────────────

def countdown_thread(s, lk, stop_event):
    while not stop_event.is_set():
        time.sleep(1)
        with lk:
            if not s["editing"]:
                s["countdown"] -= 1
                if s["countdown"] <= 0:
                    s["text_idx"] = (s["text_idx"] + 1) % len(s["texts"])
                    s["countdown"] = s["interval"]
                s["dirty"] = True


# ── Main ───────────────────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(200)          # refresh every 200 ms

    stop_event = threading.Event()
    t = threading.Thread(target=countdown_thread, args=(state, lock, stop_event), daemon=True)
    t.start()

    while True:
        with lock:
            s_snap = dict(state)

        if s_snap["dirty"]:
            draw_screen(stdscr, s_snap)
            with lock:
                state["dirty"] = False

        key = stdscr.getch()

        if key == -1:
            continue

        with lock:
            s = state

            # ── quit ──
            if key in (ord("q"), ord("Q")):
                stop_event.set()
                return

            # ── editing mode ──
            if s["editing"]:
                if key in (curses.KEY_ENTER, 10, 13):
                    if s["edit_buf"].strip():
                        s["texts"][s["text_idx"]] = s["edit_buf"].strip()
                    s["editing"] = False
                    s["edit_buf"] = ""
                    curses.curs_set(0)
                elif key == 27:   # Esc
                    s["editing"] = False
                    s["edit_buf"] = ""
                    curses.curs_set(0)
                elif key == curses.KEY_BACKSPACE or key == 127:
                    s["edit_buf"] = s["edit_buf"][:-1]
                elif 32 <= key < 127:
                    s["edit_buf"] += chr(key)
                s["dirty"] = True
                continue

            # ── normal mode ──
            if key in (ord("n"), ord("N")):
                s["text_idx"] = (s["text_idx"] + 1) % len(s["texts"])
                s["countdown"] = s["interval"]
            elif key in (ord("p"), ord("P")):
                s["text_idx"] = (s["text_idx"] - 1) % len(s["texts"])
                s["countdown"] = s["interval"]
            elif key in (ord("f"), ord("F")):
                s["style_idx"] = (s["style_idx"] + 1) % len(FONT_STYLES)
            elif key in (ord("a"), ord("A")):
                s["align_idx"] = (s["align_idx"] + 1) % len(ALIGNMENTS)
            elif key in (ord("v"), ord("V")):
                s["vpos_idx"] = (s["vpos_idx"] + 1) % len(V_POSITIONS)
            elif key in (ord("e"), ord("E")):
                s["editing"]  = True
                s["edit_buf"] = s["texts"][s["text_idx"]]
                curses.curs_set(1)
            elif key == ord("+"):
                s["interval"]  = min(3600, s["interval"] + 5)
                s["countdown"] = min(s["countdown"], s["interval"])
            elif key == ord("-"):
                s["interval"]  = max(5, s["interval"] - 5)
                s["countdown"] = min(s["countdown"], s["interval"])
            elif key == curses.KEY_RESIZE:
                pass   # just redraw

            s["dirty"] = True


if __name__ == "__main__":
    curses.wrapper(main)