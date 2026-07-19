"""Terminal Text Rotator — JSON edition
Loads quotes from data.json keyed by time (HH:MM).
At the start of each new minute the matching quote is displayed.

data.json format (array of objects):
  [
    {
      "time":       "HH:MM",
      "timeString": "One past midnight",
      "quote":      "The actual quote text.",
      "author":     "Author Name",
      "title":      "Source Title"
    },
    ...
  ]

Controls:
  n / p   - next / previous entry manually
  f       - cycle font style
  a       - cycle alignment (left / center / right)
  v       - cycle vertical position (top / middle / bottom)
  r       - reload data.json from disk
  q       - quit
"""

import curses
import time
import json
import os
import threading
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────

DATA_FILE = os.path.join(os.path.dirname("/Users/skyefuller/Downloads/data.json"), "data.json")


FONT_STYLES = [
    ("Normal",         curses.A_NORMAL),
    ("Bold",           curses.A_BOLD),
    ("Dim",            curses.A_DIM),
    ("Underline",      curses.A_UNDERLINE),
    ("Reverse",        curses.A_REVERSE),
    ("Blink",          curses.A_BLINK),
    ("Bold+Underline", curses.A_BOLD | curses.A_UNDERLINE),
    ("Bold+Reverse",   curses.A_BOLD | curses.A_REVERSE),
]

ALIGNMENTS  = ["left", "center", "right"]
V_POSITIONS = ["top", "middle", "bottom"]


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data():
    """Load and index data.json. Returns (entries_list, by_time_dict, error_str)."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
        by_time = {e["time"]: e for e in entries if "time" in e}
        return entries, by_time, None
    except FileNotFoundError:
        return [], {}, f"data.json not found at: {DATA_FILE}"
    except json.JSONDecodeError as exc:
        return [], {}, f"JSON parse error: {exc}"


def format_entry(entry):
    """Turn a JSON entry into display strings."""
    time_str    = entry.get("timeString", entry.get("time", ""))
    quote       = entry.get("quote", "")
    author      = entry.get("author", "")
    title       = entry.get("title", "")
    attribution = f"— {author}" if author else ""
    if title:
        attribution += f', "{title}"'
    return time_str, quote, attribution


def current_hhmm():
    return datetime.now().strftime("%H:%M")


def find_entry_for_now(entries, by_time):
    """Return entry matching current HH:MM, or closest earlier one."""
    now = current_hhmm()
    if now in by_time:
        return by_time[now]
    times   = sorted(by_time.keys())
    earlier = [t for t in times if t <= now]
    if earlier:
        return by_time[earlier[-1]]
    return entries[-1] if entries else None


def entry_index(entries, entry):
    try:
        return entries.index(entry)
    except ValueError:
        return 0


# ── State ──────────────────────────────────────────────────────────────────────

entries, by_time, load_error = load_data()
_start = find_entry_for_now(entries, by_time)

state = {
    "entries":    entries,
    "by_time":    by_time,
    "load_error": load_error,
    "entry_idx":  entry_index(entries, _start) if _start else 0,
    "style_idx":  1,
    "align_idx":  1,
    "vpos_idx":   1,
    "last_hhmm":  current_hhmm(),
    "dirty":      True,
}

lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────────

def wrap_text(text, max_width):
    words, lines, current = text.split(), [], ""
    for w in words:
        candidate = (current + " " + w).strip()
        if len(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w[:max_width]
    if current:
        lines.append(current)
    return lines or [""]


def x_for_line(line, align, cols):
    if align == "left":   return 2
    if align == "right":  return max(2, cols - len(line) - 2)
    return max(2, (cols - len(line)) // 2)


def base_y(rows, num_lines, vpos):
    if vpos == "top":    return 2
    if vpos == "bottom": return max(2, rows - 3 - num_lines)
    return max(2, (rows - num_lines) // 2)


def safe_addstr(stdscr, y, x, text, attr=curses.A_NORMAL):
    rows, cols = stdscr.getmaxyx()
    text = text[:max(0, cols - x - 1)]
    if 0 < y < rows - 1 and x >= 0:
        try:
            stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass


# ── Drawing ────────────────────────────────────────────────────────────────────

def draw_screen(stdscr, s):
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()
    try:
        stdscr.border()
    except curses.error:
        pass

    style_name, style_attr = FONT_STYLES[s["style_idx"]]
    align = ALIGNMENTS[s["align_idx"]]
    vpos  = V_POSITIONS[s["vpos_idx"]]
    max_w = max(10, cols - 4)

    if s["load_error"]:
        safe_addstr(stdscr, rows // 2,     2, s["load_error"], curses.A_BOLD)
        safe_addstr(stdscr, rows // 2 + 1, 2, "Press 'r' to reload data.json")
    elif not s["entries"]:
        safe_addstr(stdscr, rows // 2, 2, "No entries found in data.json", curses.A_BOLD)
    else:
        entry = s["entries"][s["entry_idx"]]
        time_str, quote, attribution = format_entry(entry)

        time_lines  = wrap_text(time_str,    max_w) if time_str    else []
        quote_lines = wrap_text(quote,       max_w) if quote       else []
        attr_lines  = wrap_text(attribution, max_w) if attribution else []

        # Assemble with blank separator lines
        all_lines = (
            time_lines
            + ([""] if time_lines and quote_lines else [])
            + quote_lines
            + ([""] if attr_lines else [])
            + attr_lines
        )

        time_end  = len(time_lines)
        quote_end = time_end + (1 if time_lines and quote_lines else 0) + len(quote_lines)
        start_y   = base_y(rows, len(all_lines), vpos)

        for i, line in enumerate(all_lines):
            y = start_y + i
            x = x_for_line(line, align, cols)
            if i < time_end:
                safe_addstr(stdscr, y, x, line, curses.A_BOLD)       # timeString
            elif i < quote_end:
                safe_addstr(stdscr, y, x, line, style_attr)          # quote
            else:
                safe_addstr(stdscr, y, x, line, curses.A_UNDERLINE)   # attribution

    # status bar
    now    = current_hhmm()
    total  = len(s["entries"])
    idx    = s["entry_idx"] + 1
    status = f" [{idx}/{total}]  Style:{style_name}  Align:{align}  Pos:{vpos}  Clock:{now} "
    safe_addstr(stdscr, rows - 2, 1, status[:cols - 2], curses.A_DIM)

    # help bar
    help_str = " n/p:next/prev  f:font  a:align  v:vpos  r:reload  q:quit "
    safe_addstr(stdscr, rows - 1, 0, help_str[:cols - 1], curses.A_REVERSE)

    stdscr.refresh()


# ── Clock thread ───────────────────────────────────────────────────────────────

def clock_thread(s, lk, stop_event):
    while not stop_event.is_set():
        time.sleep(1)
        now = current_hhmm()
        with lk:
            if now != s["last_hhmm"]:
                s["last_hhmm"] = now
                entry = find_entry_for_now(s["entries"], s["by_time"])
                if entry:
                    s["entry_idx"] = entry_index(s["entries"], entry)
                s["dirty"] = True


# ── Main ───────────────────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(250)

    stop_event = threading.Event()
    t = threading.Thread(target=clock_thread, args=(state, lock, stop_event), daemon=True)
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

            if key in (ord("q"), ord("Q")):
                stop_event.set()
                return
            elif key in (ord("n"), ord("N")):
                if s["entries"]:
                    s["entry_idx"] = (s["entry_idx"] + 1) % len(s["entries"])
            elif key in (ord("p"), ord("P")):
                if s["entries"]:
                    s["entry_idx"] = (s["entry_idx"] - 1) % len(s["entries"])
            elif key in (ord("f"), ord("F")):
                s["style_idx"] = (s["style_idx"] + 1) % len(FONT_STYLES)
            elif key in (ord("a"), ord("A")):
                s["align_idx"] = (s["align_idx"] + 1) % len(ALIGNMENTS)
            elif key in (ord("v"), ord("V")):
                s["vpos_idx"] = (s["vpos_idx"] + 1) % len(V_POSITIONS)
            elif key in (ord("r"), ord("R")):
                new_entries, new_by_time, err = load_data()
                s["entries"]    = new_entries
                s["by_time"]    = new_by_time
                s["load_error"] = err
                entry = find_entry_for_now(new_entries, new_by_time)
                s["entry_idx"]  = entry_index(new_entries, entry) if entry else 0
            elif key == curses.KEY_RESIZE:
                pass

            s["dirty"] = True


if __name__ == "__main__":
    curses.wrapper(main)
