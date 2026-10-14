#!/usr/bin/env python3
"""BlockFall - Block Blast benzeri blok bulmaca oyunu (GTK3 + Cairo)."""

import json
import math
import os
import random
import sys
from functools import lru_cache

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

APP_ID = "io.github.blockfall"
VERSION = "0.2.3"
SIZE = 8  # tahta boyutu (8x8)

# ---------------------------------------------------------------------------
# Renkler
# ---------------------------------------------------------------------------

BG_TOP = (0.36, 0.37, 0.40)
BG_BOTTOM = (0.33, 0.34, 0.38)
FRAME = (0.27, 0.28, 0.31)
GRID_LINE = (0.11, 0.12, 0.14)
EMPTY = (0.18, 0.19, 0.22)
TEXT = (1.0, 1.0, 1.0)
TEXT_DIM = (0.78, 0.79, 0.82)
GOLD = (0.96, 0.78, 0.27)
GOLD_DARK = (0.80, 0.55, 0.12)
SCORE_A = (0.85, 0.96, 0.48)  # skor geçişi: sarı-yeşil
SCORE_B = (0.38, 0.95, 0.84)  # skor geçişi: turkuaz

FONT = "Quicksand, Ubuntu, Sans"

PALETTE = [
    (0.82, 0.61, 0.61),  # gül pembesi
    (0.57, 0.64, 0.78),  # gri mavi
    (0.61, 0.73, 0.73),  # adaçayı
    (0.50, 0.55, 0.42),  # haki
    (0.83, 0.76, 0.55),  # kum
    (0.66, 0.59, 0.76),  # lavanta
    (0.82, 0.66, 0.52),  # kiremit
]

# ---------------------------------------------------------------------------
# Şekiller
# ---------------------------------------------------------------------------

# (ağırlık, şekil) - ağırlık tüm döndürülmüş varyantlara bölüştürülür
BASE_SHAPES = [
    (2, ["#"]),
    (3, ["##"]),
    (3, ["###"]),
    (2, ["####"]),
    (1, ["#####"]),
    (3, ["##", "##"]),
    (1, ["###", "###", "###"]),
    (2, ["###", "###"]),
    (3, ["#.", "##"]),
    (3, ["#.", "#.", "##"]),
    (1, ["#..", "#..", "###"]),
    (2, ["###", ".#."]),
    (2, ["##.", ".##"]),
]


def _normalize(cells):
    mr = min(r for r, _ in cells)
    mc = min(c for _, c in cells)
    return tuple(sorted((r - mr, c - mc) for r, c in cells))


def _variants(rows):
    cells = [(r, c) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "#"]
    out = set()
    for mirror in (False, True):
        cur = [(r, -c) for r, c in cells] if mirror else cells
        for _ in range(4):
            cur = [(c, -r) for r, c in cur]
            out.add(_normalize(cur))
    return sorted(out)


SHAPES = []  # [(ağırlık, hücreler)]
for _w, _rows in BASE_SHAPES:
    _vs = _variants(_rows)
    for _v in _vs:
        SHAPES.append((_w / len(_vs), _v))


class Piece:
    def __init__(self, cells, color):
        self.cells = cells
        self.color = color
        self.rows = max(r for r, _ in cells) + 1
        self.cols = max(c for _, c in cells) + 1

    @staticmethod
    def random():
        weights = [w for w, _ in SHAPES]
        cells = random.choices([s for _, s in SHAPES], weights=weights)[0]
        return Piece(cells, random.randrange(len(PALETTE)))


# ---------------------------------------------------------------------------
# Oyun mantığı
# ---------------------------------------------------------------------------


class Game:
    def __init__(self, best=0):
        self.best = best
        self.new_game()

    def new_game(self):
        self.grid = [[None] * SIZE for _ in range(SIZE)]
        self.score = 0
        self.combo = 0
        self.moves_since_clear = 0
        self.game_over = False
        self.tray = [None, None, None]
        self.refill()

    # --- tahta sorguları ---

    def can_place(self, piece, row, col):
        for r, c in piece.cells:
            rr, cc = row + r, col + c
            if not (0 <= rr < SIZE and 0 <= cc < SIZE) or self.grid[rr][cc] is not None:
                return False
        return True

    def fits_anywhere(self, piece):
        return any(
            self.can_place(piece, r, c)
            for r in range(SIZE - piece.rows + 1)
            for c in range(SIZE - piece.cols + 1)
        )

    def lines_completed(self, piece, row, col):
        """Parça (row, col)'a konursa dolacak satır ve sütunlar."""
        filled = {(row + r, col + c) for r, c in piece.cells}

        def full(cells):
            return all(self.grid[r][c] is not None or (r, c) in filled for r, c in cells)

        rows = [r for r in range(SIZE) if full([(r, c) for c in range(SIZE)])]
        cols = [c for c in range(SIZE) if full([(r, c) for r in range(SIZE)])]
        return rows, cols

    # --- hamleler ---

    def refill(self):
        # En az bir parçanın sığdığı bir üçlü bulmaya çalış
        for _ in range(40):
            tray = [Piece.random() for _ in range(3)]
            if any(self.fits_anywhere(p) for p in tray):
                break
        self.tray = tray

    def place(self, index, row, col):
        piece = self.tray[index]
        rows, cols = self.lines_completed(piece, row, col)
        for r, c in piece.cells:
            self.grid[row + r][col + c] = piece.color
        self.tray[index] = None

        points = len(piece.cells)
        lines = len(rows) + len(cols)
        cleared = {}  # (r, c) -> renk; animasyon için temizlenmeden önce kaydedilir
        all_clear = False
        if lines:
            self.combo = self.combo + 1 if self.moves_since_clear < 3 else 1
            self.moves_since_clear = 0
            points += 10 * lines * (lines + 1) // 2 * self.combo
            for r in rows:
                for c in range(SIZE):
                    cleared[(r, c)] = self.grid[r][c]
            for c in cols:
                for r in range(SIZE):
                    cleared[(r, c)] = self.grid[r][c]
            for r, c in cleared:
                self.grid[r][c] = None
            if all(cell is None for line in self.grid for cell in line):
                all_clear = True
                points += 300  # tahta tamamen temizlendi
        else:
            self.moves_since_clear += 1
            if self.moves_since_clear >= 3:
                self.combo = 0

        self.score += points
        self.best = max(self.best, self.score)

        refilled = all(p is None for p in self.tray)
        if refilled:
            self.refill()
        if not any(p is not None and self.fits_anywhere(p) for p in self.tray):
            self.game_over = True
        return {
            "points": points,
            "lines": lines,
            "placed": [(row + r, col + c) for r, c in piece.cells],
            "cleared": cleared,
            "combo": self.combo if lines else 0,
            "all_clear": all_clear,
            "refilled": refilled,
        }


# ---------------------------------------------------------------------------
# Kalıcı veri
# ---------------------------------------------------------------------------


def data_path():
    return os.path.join(GLib.get_user_data_dir(), "blockfall", "save.json")


def load_data():
    try:
        with open(data_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_data(**updates):
    path = data_path()
    data = load_data()
    data.update(updates)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def load_best():
    try:
        return int(load_data().get("best", 0))
    except (ValueError, TypeError):
        return 0


def save_best(best):
    save_data(best=best)


DESKTOP_FILE = f"/usr/share/applications/{APP_ID}.desktop"


def ensure_desktop_shortcut():
    """İlk açılışta masaüstüne güvenilir bir kısayol koyar (paket kuruluysa).

    Kurulum betiği oturum açık kullanıcılar için bunu zaten yapar; bu, kurulum
    sırasında oturumu kapalı olan kullanıcılar içindir. Kullanıcı kısayolu
    silerse bir daha oluşturulmaz.
    """
    if load_data().get("shortcut_done") or not os.path.exists(DESKTOP_FILE):
        return
    desk = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
    if desk and os.path.isdir(desk) and desk != GLib.get_home_dir():
        dst = os.path.join(desk, os.path.basename(DESKTOP_FILE))
        try:
            if not os.path.exists(dst):
                with open(DESKTOP_FILE, "rb") as src, open(dst, "wb") as out:
                    out.write(src.read())
            os.chmod(dst, 0o755)
            # GNOME masaüstü simgeleri (DING) güvenilmeyen başlatıcıları çalıştırmaz
            Gio.File.new_for_path(dst).set_attribute_string(
                "metadata::trusted", "true", Gio.FileQueryInfoFlags.NONE, None)
        except (OSError, GLib.Error):
            pass
    save_data(shortcut_done=True)


# ---------------------------------------------------------------------------
# Çizim yardımcıları
# ---------------------------------------------------------------------------


def rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


def shade(color, k):
    """k > 0 açar, k < 0 koyulaştırır."""
    if k >= 0:
        return tuple(v + (1 - v) * k for v in color)
    return tuple(v * (1 + k) for v in color)


def _polygon(cr, pts, color, alpha):
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.set_source_rgba(*color, alpha)
    cr.fill()


@lru_cache(maxsize=256)
def _bevel(color):
    """Bloğun üst, sol, alt, sağ kenar tonları (renk başına bir kez hesaplanır)."""
    return shade(color, 0.32), shade(color, 0.16), shade(color, -0.24), shade(color, -0.12)


def draw_block(cr, x, y, s, color, alpha=1.0):
    """Pahlı (bevel) kare blok: üst/sol kenar açık, alt/sağ kenar koyu."""
    gap = max(1.0, s * 0.025)
    x, y, s = x + gap / 2, y + gap / 2, s - gap
    b = s * 0.11
    x2, y2 = x + s, y + s
    top, left, bottom, right = _bevel(color)
    cr.rectangle(x + b, y + b, s - 2 * b, s - 2 * b)
    cr.set_source_rgba(*color, alpha)
    cr.fill()
    _polygon(cr, [(x, y), (x2, y), (x2 - b, y + b), (x + b, y + b)], top, alpha)
    _polygon(cr, [(x, y), (x + b, y + b), (x + b, y2 - b), (x, y2)], left, alpha)
    _polygon(cr, [(x, y2), (x + b, y2 - b), (x2 - b, y2 - b), (x2, y2)], bottom, alpha)
    _polygon(cr, [(x2, y), (x2, y2), (x2 - b, y2 - b), (x2 - b, y + b)], right, alpha)


def draw_block_fx(cr, x, y, s, color, scale=1.0, rot=0.0, alpha=1.0, flash=0.0):
    """Ölçekli/döndürülmüş blok; `flash` kadar beyaz parlama ekler."""
    size = s * scale
    if size < 0.5:
        return
    cr.save()
    cr.translate(x + s / 2, y + s / 2)
    if rot:
        cr.rotate(rot)
    draw_block(cr, -size / 2, -size / 2, size, color, alpha)
    if flash > 0:
        gap = max(1.0, size * 0.025)
        cr.rectangle(-size / 2 + gap / 2, -size / 2 + gap / 2, size - gap, size - gap)
        cr.set_source_rgba(1, 1, 1, flash * alpha)
        cr.fill()
    cr.restore()


def draw_piece(cr, piece, ox, oy, s, alpha=1.0, shadow=True):
    """Parçayı, sağ-alta düşen gölgesiyle birlikte çizer."""
    if shadow:
        off = s * 0.16
        for r, c in piece.cells:
            cr.rectangle(ox + c * s + off, oy + r * s + off, s, s)
        cr.set_source_rgba(0, 0, 0, 0.28 * alpha)
        cr.fill()
    for r, c in piece.cells:
        draw_block(cr, ox + c * s, oy + r * s, s, PALETTE[piece.color], alpha)


_LAYOUTS = {}  # (metin, boyut, kalın) -> Pango yerleşimi; her karede yeniden kurulmasın


def _layout(cr, text, size, bold=True):
    key = (text, size, bold)
    layout = _LAYOUTS.get(key)
    if layout is None:
        if len(_LAYOUTS) > 200:  # sayaç gibi sürekli değişen metinler birikmesin
            _LAYOUTS.clear()
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription.from_string(f"{FONT} {'Bold' if bold else 'Medium'}")
        fd.set_absolute_size(max(1, size) * Pango.SCALE)
        layout.set_font_description(fd)
        layout.set_text(text, -1)
        _LAYOUTS[key] = layout
    else:
        PangoCairo.update_layout(cr, layout)
    _, logical = layout.get_pixel_extents()
    return layout, logical


def draw_text(cr, text, x, y, size, color=TEXT, bold=True, align=0.5, shadow=0.0, alpha=1.0):
    layout, logical = _layout(cr, text, size, bold)
    tx, ty = x - logical.width * align, y - logical.height / 2
    if shadow:
        cr.move_to(tx, ty + shadow)
        cr.set_source_rgba(0, 0, 0, 0.25 * alpha)
        PangoCairo.show_layout(cr, layout)
    cr.move_to(tx, ty)
    cr.set_source_rgba(*color, alpha)
    PangoCairo.show_layout(cr, layout)
    cr.new_path()  # move_to'dan kalan noktayı temizle (sonraki yay ona bağlanmasın)
    return logical.width


def draw_score(cr, text, x, y, size, colors=None, alpha=1.0):
    """Sarı-yeşilden turkuaza geçişli, hafif parlayan skor yazısı."""
    col_a, col_b = colors or (SCORE_A, SCORE_B)
    layout, logical = _layout(cr, text, size)
    tx, ty = x - logical.width / 2, y - logical.height / 2
    cr.save()
    cr.move_to(tx, ty)
    PangoCairo.layout_path(cr, layout)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    for width, a in ((size * 0.30, 0.05), (size * 0.18, 0.07), (size * 0.08, 0.10)):
        cr.set_line_width(width)
        cr.set_source_rgba(*col_b, a * alpha)
        cr.stroke_preserve()
    grad = cairo.LinearGradient(tx, ty, tx + logical.width, ty + logical.height)
    grad.add_color_stop_rgba(0, *col_a, alpha)
    grad.add_color_stop_rgba(1, *col_b, alpha)
    cr.set_source(grad)
    cr.fill()
    cr.restore()


def draw_crown(cr, x, y, h):
    """(x, y) sol-orta noktası olan, h yüksekliğinde altın taç."""
    w = h * 1.25
    top = y - h / 2

    def p(u, v):
        return (x + u * w, top + v * h)

    def shape(dy):
        cr.move_to(*p(0.10, 0.78 + dy))
        for u, v in ((0.0, 0.28), (0.30, 0.52), (0.50, 0.12), (0.70, 0.52), (1.0, 0.28),
                     (0.90, 0.78)):
            cr.line_to(*p(u, v + dy))
        cr.close_path()
        cr.rectangle(*p(0.10, 0.82 + dy), w * 0.80, h * 0.16)
        for u, v in ((0.0, 0.24), (0.5, 0.08), (1.0, 0.24)):
            cr.new_sub_path()
            cr.arc(*p(u, v + dy), h * 0.09, 0, 6.2832)

    shape(0.06)
    cr.set_source_rgba(0, 0, 0, 0.22)
    cr.fill()
    shape(0)
    grad = cairo.LinearGradient(0, top, 0, top + h)
    grad.add_color_stop_rgb(0, 1.0, 0.88, 0.40)
    grad.add_color_stop_rgb(1, *GOLD_DARK)
    cr.set_source(grad)
    cr.fill()
    return w


# ---------------------------------------------------------------------------
# Animasyon yardımcıları
# ---------------------------------------------------------------------------

PRAISE_GOLD = ((1.0, 0.93, 0.50), (1.0, 0.66, 0.26))
PRAISE_PINK = ((1.0, 0.80, 0.55), (0.98, 0.50, 0.62))


def now():
    return GLib.get_monotonic_time() / 1e6


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out_cubic(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.7):
    t = clamp01(t) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def praise_for(lines):
    if lines >= 5:
        return "Amazing!"
    return {2: "Good!", 3: "Great!", 4: "Excellent!"}.get(lines)


def gray_of(color):
    v = sum(color) / 3 * 0.55 + 0.18
    return (v, v, v + 0.02)


# ---------------------------------------------------------------------------
# Oyun alanı
# ---------------------------------------------------------------------------


class GameView(Gtk.DrawingArea):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.drag = None  # {"i", "x", "y", "lift", "t0"}
        self.hover = None
        self.tick_id = None
        self.anim_until = 0.0
        self.lit_active = False  # sürüklerken tamamlanacak satır parlıyor mu
        self.fits = (None, [])  # (tahta sürümü, parça sığıyor mu listesi)
        self.board_version = 0
        self.reset_effects()
        self.set_can_focus(True)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_release)
        self.start_spawn()

    def reset_effects(self):
        self.returning = {}  # tepsi indeksi -> {"t0", "from": (x, y, boyut)}
        self.pops = []  # {"cells", "t0"}
        self.clears = []  # {"cells": [(r, c, renk, gecikme)], "t0"}
        self.particles = []  # tahta koordinatlarında (hücre birimi)
        self.texts = []  # uçan yazılar
        self.shake = None
        self.spawn_t0 = [0.0, 0.0, 0.0]
        self.score_anim = {"from": self.game.score, "to": self.game.score, "t0": 0.0}
        self.game_over_t0 = None

    # --- animasyon döngüsü ---

    def animate(self, duration):
        """En az `duration` saniye boyunca her karede yeniden çiz."""
        self.anim_until = max(self.anim_until, now() + duration)
        if self.tick_id is None:
            self.tick_id = self.add_tick_callback(self.on_tick)

    def on_tick(self, _widget, _clock):
        self.queue_draw()
        # Sürüklerken yalnızca parlama varsa sürekli çiz; yoksa fare hareketi yeter
        if now() < self.anim_until or (self.drag is not None and self.lit_active):
            return True
        self.tick_id = None
        return False

    def start_spawn(self):
        t = now()
        self.spawn_t0 = [t + i * 0.07 for i in range(3)]
        self.animate(0.5)

    # --- yerleşim ---

    def layout(self):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        cell = max(8.0, min((w - 24) / 8.4, (h - 16) / 15.4))
        board = cell * SIZE
        top = (h - cell * 15.4) / 2
        bx = (w - board) / 2
        L = {
            "w": w,
            "h": h,
            "cell": cell,
            "bx": bx,
            "by": top + cell * 3.6,
            "board": board,
            "best_y": top + cell * 0.8,
            "score_y": top + cell * 2.2,
            "tray_y": top + cell * 11.9,
            "tray_h": cell * 3.4,
            "mini": cell * 0.45,
        }
        L["slots"] = [
            (bx + i * board / 3, L["tray_y"], board / 3, L["tray_h"]) for i in range(3)
        ]
        btn = cell * 0.8
        L["restart"] = (bx + board - btn, L["best_y"] - btn / 2, btn, btn)
        return L

    def tray_origin(self, L, i, piece):
        sx, sy, sw, sh = L["slots"][i]
        m = L["mini"]
        return sx + (sw - piece.cols * m) / 2, sy + (sh - piece.rows * m) / 2

    def tray_fits(self):
        """Tepsideki parçaların tahtaya sığıp sığmadığı; yalnızca hamleden sonra değişir."""
        if self.fits[0] != self.board_version:
            g = self.game
            self.fits = (self.board_version,
                         [p is not None and g.fits_anywhere(p) for p in g.tray])
        return self.fits[1]

    def drag_size(self, L):
        k = ease_out_cubic((now() - self.drag["t0"]) / 0.12)
        return lerp(L["mini"], L["cell"], k)

    def drag_target(self, L):
        """Sürüklenen parçanın çizim konumu, boyutu ve oturacağı hücre."""
        piece = self.game.tray[self.drag["i"]]
        c = L["cell"]
        s = self.drag_size(L)
        cy = self.drag["y"] - self.drag["lift"]
        px = self.drag["x"] - piece.cols * s / 2
        py = cy - piece.rows * s / 2
        col = round((self.drag["x"] - piece.cols * c / 2 - L["bx"]) / c)
        row = round((cy - piece.rows * c / 2 - L["by"]) / c)
        target = (row, col) if self.game.can_place(piece, row, col) else None
        return px, py, s, target

    # --- hamle ve efektler ---

    def do_place(self, i, row, col):
        g = self.game
        t = now()
        old_score = self.shown_score()
        info = g.place(i, row, col)
        self.board_version += 1

        self.pops.append({"cells": info["placed"], "t0": t})
        self.score_anim = {"from": old_score, "to": g.score, "t0": t}

        # Puan yazısı: yerleştirilen parçanın ortasından yükselir
        cr_ = sum(r for r, _ in info["placed"]) / len(info["placed"]) + 0.5
        cc_ = sum(c for _, c in info["placed"]) / len(info["placed"]) + 0.5
        self.texts.append({"kind": "points", "text": f"+{info['points']}", "u": cc_, "v": cr_,
                           "t0": t, "dur": 0.9})

        if info["cleared"]:
            cells = []
            for (r, c), color in info["cleared"].items():
                delay = 0.035 * (abs(r + 0.5 - cr_) + abs(c + 0.5 - cc_))
                cells.append((r, c, color, delay))
                for _ in range(3):
                    self.particles.append({
                        "u": c + 0.5, "v": r + 0.5,
                        "vu": random.uniform(-3.0, 3.0), "vv": random.uniform(-6.0, -1.5),
                        "size": random.uniform(0.12, 0.24), "color": color,
                        "t0": t + delay + 0.08, "life": random.uniform(0.5, 0.8),
                        "spin": random.uniform(-8, 8),
                    })
            self.clears.append({"cells": cells, "t0": t})

            banners = []
            if info["all_clear"]:
                banners.append(("All Clear!", PRAISE_PINK))
            praise = praise_for(info["lines"])
            if praise:
                banners.append((praise, PRAISE_GOLD))
            if info["combo"] > 1:
                banners.append((f"Combo x{info['combo']}", None))
            for k, (text, colors) in enumerate(banners):
                self.texts.append({"kind": "banner", "text": text, "colors": colors,
                                   "u": 4.0, "v": 4.0 + (k - (len(banners) - 1) / 2) * 1.2,
                                   "t0": t + 0.05 + k * 0.08, "dur": 1.3})
            if info["lines"] >= 3 or info["all_clear"]:
                self.shake = {"t0": t, "amp": min(info["lines"], 5) / 5}

        if info["refilled"]:
            self.start_spawn()
            for k in range(3):
                self.spawn_t0[k] += 0.15
        if g.game_over:
            self.game_over_t0 = t + 0.3
            save_best(g.best)
        self.animate(2.6 if g.game_over else 1.4)

    def shown_score(self):
        a = self.score_anim
        k = ease_out_cubic((now() - a["t0"]) / 0.5)
        return round(lerp(a["from"], a["to"], k))

    def overlay_alpha(self):
        if self.game_over_t0 is None:
            return 1.0 if self.game.game_over else 0.0
        return clamp01((now() - self.game_over_t0 - 0.75) / 0.35)

    # --- çizim ---

    def on_draw(self, _widget, cr):
        L = self.layout()
        g = self.game
        c = L["cell"]
        t = now()

        # Arka plan
        grad = cairo.LinearGradient(0, 0, 0, L["h"])
        grad.add_color_stop_rgb(0, *BG_TOP)
        grad.add_color_stop_rgb(1, *BG_BOTTOM)
        cr.set_source(grad)
        cr.paint()

        cr.save()
        if self.shake is not None:
            st = t - self.shake["t0"]
            if st < 0.35:
                amp = c * 0.12 * self.shake["amp"] * (1 - st / 0.35)
                cr.translate(amp * math.sin(st * 70), amp * math.cos(st * 55))
            else:
                self.shake = None

        drag = self.drag_target(L) if self.drag is not None else None
        self.draw_header(cr, L, t)
        self.draw_board(cr, L, t, drag)
        self.draw_clears(cr, L, t)
        self.draw_particles(cr, L, t)
        self.draw_tray(cr, L, t)

        if drag is not None:
            px, py, s, _ = drag
            draw_piece(cr, g.tray[self.drag["i"]], px, py, s)

        self.draw_texts(cr, L, t)
        cr.restore()

        a = self.overlay_alpha()
        if a >= 1:
            self.draw_game_over(cr, L, a)
        elif a > 0:  # yalnızca belirirken ara katman gerekir
            cr.push_group()
            self.draw_game_over(cr, L, a)
            cr.pop_group_to_source()
            cr.paint_with_alpha(a)

    def draw_header(self, cr, L, t):
        g, c = self.game, L["cell"]
        crown_w = draw_crown(cr, L["bx"], L["best_y"], c * 0.55)
        draw_text(cr, str(g.best), L["bx"] + crown_w + c * 0.12, L["best_y"], c * 0.52,
                  GOLD, align=0.0, shadow=c * 0.04)

        a = self.score_anim
        pulse = 0.0
        if a["to"] != a["from"]:
            pulse = 0.18 * (1 - ease_out_cubic((t - a["t0"]) / 0.3))
        cr.save()
        cr.translate(L["w"] / 2, L["score_y"])
        cr.scale(1 + pulse, 1 + pulse)
        draw_score(cr, str(self.shown_score()), 0, 0, c * 1.0)
        cr.restore()

        if g.combo > 1:
            draw_text(cr, f"Combo x{g.combo}", L["w"] / 2, L["score_y"] + c * 0.8,
                      c * 0.3, SCORE_A, shadow=c * 0.03)
        self.draw_restart(cr, L)

    def draw_board(self, cr, L, t, drag):
        g, c = self.game, L["cell"]
        pad = c * 0.16
        rounded_rect(cr, L["bx"] - pad, L["by"] - pad, L["board"] + 2 * pad,
                     L["board"] + 2 * pad, c * 0.14)
        cr.set_source_rgb(*FRAME)
        cr.fill()
        cr.rectangle(L["bx"], L["by"], L["board"], L["board"])
        cr.set_source_rgb(*GRID_LINE)
        cr.fill()

        preview = set()
        lit_rows, lit_cols = [], []
        drag_piece = None
        if drag is not None:
            drag_piece = g.tray[self.drag["i"]]
            target = drag[3]
            if target:
                tr, tc = target
                preview = {(tr + r, tc + cc) for r, cc in drag_piece.cells}
                lit_rows, lit_cols = g.lines_completed(drag_piece, tr, tc)
        self.lit_active = bool(lit_rows or lit_cols)
        if self.lit_active and self.tick_id is None:
            self.animate(0)  # parlama nabzı için kare döngüsünü başlat

        # Yerleştirme "pop" efekti: hücre -> ilerleme (0..1)
        popping = {}
        self.pops = [p for p in self.pops if t - p["t0"] < 0.25]
        for p in self.pops:
            for cell in p["cells"]:
                popping[cell] = (t - p["t0"]) / 0.22

        gap = max(1.0, c * 0.025)
        for r in range(SIZE):
            for col in range(SIZE):
                x = L["bx"] + col * c
                y = L["by"] + r * c
                color = g.grid[r][col]
                lit = r in lit_rows or col in lit_cols
                if lit and (color is not None or (r, col) in preview):
                    k = 0.5 + 0.5 * math.sin(t * 9)
                    draw_block(cr, x, y, c, shade(PALETTE[drag_piece.color], 0.12 * k))
                elif color is not None:
                    base = PALETTE[color]
                    if self.game_over_t0 is not None and t >= self.game_over_t0 + r * 0.07:
                        base = gray_of(base)
                    if (r, col) in popping:
                        k = ease_out_cubic(popping[(r, col)])
                        draw_block_fx(cr, x, y, c, base, scale=1 + 0.14 * (1 - k),
                                      flash=0.45 * (1 - k))
                    else:
                        draw_block(cr, x, y, c, base)
                elif (r, col) in preview:
                    draw_block(cr, x, y, c, PALETTE[drag_piece.color], 0.45)
                else:
                    cr.rectangle(x + gap / 2, y + gap / 2, c - gap, c - gap)
                    cr.set_source_rgb(*EMPTY)
                    cr.fill()

    def draw_clears(self, cr, L, t):
        c = L["cell"]
        alive = []
        for eff in self.clears:
            done = True
            for r, col, color, delay in eff["cells"]:
                lt = t - eff["t0"] - delay
                if lt > 0.42:
                    continue
                done = False
                x, y = L["bx"] + col * c, L["by"] + r * c
                base = PALETTE[color]
                if lt < 0.1:  # beyaza parlama
                    draw_block_fx(cr, x, y, c, base, flash=0.75 * clamp01(lt / 0.1))
                else:  # dönerek küçülme
                    k = ease_out_cubic((lt - 0.1) / 0.32)
                    draw_block_fx(cr, x, y, c, base, scale=1 - k, rot=k * 0.9,
                                  alpha=1 - k * 0.4, flash=0.75 * (1 - k))
            if not done:
                alive.append(eff)
        self.clears = alive

    def draw_particles(self, cr, L, t):
        c = L["cell"]
        alive = []
        for p in self.particles:
            lt = t - p["t0"]
            if lt > p["life"]:
                continue
            alive.append(p)
            if lt < 0:
                continue
            u = p["u"] + p["vu"] * lt
            v = p["v"] + p["vv"] * lt + 0.5 * 14.0 * lt * lt
            s = p["size"] * c * (1 - 0.5 * lt / p["life"])
            cr.save()
            cr.translate(L["bx"] + u * c, L["by"] + v * c)
            cr.rotate(p["spin"] * lt)
            cr.rectangle(-s / 2, -s / 2, s, s)
            cr.set_source_rgba(*shade(PALETTE[p["color"]], 0.2), 1 - lt / p["life"])
            cr.fill()
            cr.restore()
        self.particles = alive

    def draw_tray(self, cr, L, t):
        g, m = self.game, L["mini"]
        fits = self.tray_fits()
        for i, piece in enumerate(g.tray):
            if piece is None or (self.drag is not None and self.drag["i"] == i):
                continue
            ox, oy = self.tray_origin(L, i, piece)
            alpha = 1.0 if fits[i] else 0.35

            ret = self.returning.get(i)
            if ret is not None:
                k = ease_out_cubic((t - ret["t0"]) / 0.2)
                if k < 1:
                    fx, fy, fs = ret["from"]
                    draw_piece(cr, piece, lerp(fx, ox, k), lerp(fy, oy, k), lerp(fs, m, k), alpha)
                    continue
                del self.returning[i]

            k = (t - self.spawn_t0[i]) / 0.32
            if k < 1:
                if k <= 0:
                    continue
                s = ease_out_back(k)
                w, h = piece.cols * m, piece.rows * m
                cr.save()
                cr.translate(ox + w / 2, oy + h / 2)
                cr.scale(s, s)
                draw_piece(cr, piece, -w / 2, -h / 2, m, alpha)
                cr.restore()
            else:
                draw_piece(cr, piece, ox, oy, m, alpha)

    def draw_texts(self, cr, L, t):
        c = L["cell"]
        alive = []
        for tx in self.texts:
            lt = (t - tx["t0"]) / tx["dur"]
            if lt > 1:
                continue
            alive.append(tx)
            if lt < 0:
                continue
            x = L["bx"] + tx["u"] * c
            y = L["by"] + tx["v"] * c
            # Saydamlık doğrudan renge uygulanır (pencere boyutunda ara katman açılmaz)
            if tx["kind"] == "points":
                y -= ease_out_cubic(lt) * c * 1.0
                draw_text(cr, tx["text"], x, y, c * 0.55, shadow=c * 0.05,
                          alpha=1 - clamp01((lt - 0.6) / 0.4))
            else:
                scale = ease_out_back(lt * tx["dur"] / 0.28, 2.2)
                y -= clamp01((lt - 0.7) / 0.3) * c * 0.4
                cr.save()
                cr.translate(x, y)
                cr.scale(scale, scale)
                draw_score(cr, tx["text"], 0, 0, c * 0.85, tx["colors"],
                           alpha=1 - clamp01((lt - 0.75) / 0.25))
                cr.restore()
        self.texts = alive

    def draw_restart(self, cr, L):
        """Sağ üstte silik, dairesel ok biçiminde yeniden başlat düğmesi."""
        x, y, s, _ = L["restart"]
        cx, cy, r = x + s / 2, y + s / 2, s * 0.32
        alpha = 0.55 if self.hover == "restart" else 0.22
        cr.set_source_rgba(1, 1, 1, alpha)
        cr.set_line_width(s * 0.09)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.new_path()
        cr.arc(cx, cy, r, 0.9, 6.2832 - 0.4)
        cr.stroke()
        ax, ay = cx + r * 0.921, cy - r * 0.389  # yay sonu (açı -0.4)
        cr.move_to(ax + s * 0.13, ay - s * 0.02)
        cr.line_to(ax - s * 0.02, ay - s * 0.16)
        cr.line_to(ax - s * 0.05, ay + s * 0.06)
        cr.close_path()
        cr.fill()

    def game_over_button(self, L):
        c = L["cell"]
        bw, bh = c * 4.2, c * 1.1
        return (L["w"] / 2 - bw / 2, L["h"] / 2 + c * 1.3, bw, bh)

    def draw_game_over(self, cr, L, appear):
        c = L["cell"]
        cr.set_source_rgba(0.16, 0.17, 0.19, 0.82)
        cr.paint()
        cx, cy = L["w"] / 2, L["h"] / 2
        s = lerp(0.85, 1.0, ease_out_back(appear))
        cr.translate(cx, cy)
        cr.scale(s, s)
        cr.translate(-cx, -cy)
        draw_text(cr, "Oyun Bitti", cx, cy - c * 2.2, c * 0.75, shadow=c * 0.05)
        draw_score(cr, str(self.game.score), cx, cy - c * 0.8, c * 1.1)
        crown_h = c * 0.42
        label = str(self.game.best)
        _, logical = _layout(cr, label, c * 0.42)
        total = crown_h * 1.25 + c * 0.12 + logical.width
        sx = cx - total / 2
        draw_crown(cr, sx, cy + c * 0.35, crown_h)
        draw_text(cr, label, sx + crown_h * 1.25 + c * 0.12, cy + c * 0.35, c * 0.42,
                  GOLD, align=0.0, shadow=c * 0.03)
        x, y, w, h = self.game_over_button(L)
        color = PALETTE[2] if self.hover != "again" else shade(PALETTE[2], 0.15)
        cr.rectangle(x, y, w, h)
        cr.set_source_rgb(*color)
        cr.fill()
        cr.rectangle(x, y, w, h * 0.12)
        cr.set_source_rgb(*shade(color, 0.32))
        cr.fill()
        cr.rectangle(x, y + h * 0.88, w, h * 0.12)
        cr.set_source_rgb(*shade(color, -0.24))
        cr.fill()
        draw_text(cr, "Tekrar Oyna", cx, y + h / 2, c * 0.45, shadow=c * 0.03)

    # --- girdi ---

    @staticmethod
    def _inside(rect, x, y):
        rx, ry, rw, rh = rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def new_game(self):
        save_best(self.game.best)
        self.game.new_game()
        self.board_version += 1
        self.drag = None
        self.reset_effects()
        self.start_spawn()
        self.queue_draw()

    def on_press(self, _w, ev):
        if ev.button != 1:
            return False
        L = self.layout()
        if self.game.game_over:
            if self.overlay_alpha() > 0.5 and self._inside(self.game_over_button(L), ev.x, ev.y):
                self.new_game()
            return True
        if self._inside(L["restart"], ev.x, ev.y):
            self.new_game()
            return True
        for i, slot in enumerate(L["slots"]):
            if self.game.tray[i] is not None and self._inside(slot, ev.x, ev.y):
                self.returning.pop(i, None)
                dev = ev.get_source_device()
                touch = dev is not None and dev.get_source() == Gdk.InputSource.TOUCHSCREEN
                self.drag = {"i": i, "x": ev.x, "y": ev.y, "t0": now(),
                             "lift": L["cell"] * 1.5 if touch else 0}
                self.animate(0.15)
                return True
        return True

    def on_motion(self, _w, ev):
        if self.drag is not None:
            self.drag["x"], self.drag["y"] = ev.x, ev.y
            self.queue_draw()
            return True
        L = self.layout()
        hover = None
        if self.game.game_over:
            if self._inside(self.game_over_button(L), ev.x, ev.y):
                hover = "again"
        elif self._inside(L["restart"], ev.x, ev.y):
            hover = "restart"
        if hover != self.hover:
            self.hover = hover
            self.queue_draw()
        return True

    def on_release(self, _w, ev):
        if self.drag is None or ev.button != 1:
            return False
        self.drag["x"], self.drag["y"] = ev.x, ev.y
        px, py, s, target = self.drag_target(self.layout())
        i = self.drag["i"]
        self.drag = None
        if target:
            self.do_place(i, *target)
        else:
            self.returning[i] = {"t0": now(), "from": (px, py, s)}
            self.animate(0.25)
        self.queue_draw()
        return True


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------


class BlockFallApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.window = None
        self.game = None

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        GLib.set_application_name("BlockFall")
        self.game = Game(load_best())
        win = Gtk.ApplicationWindow(application=self, title="BlockFall")
        height = 740
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0) if display else None
        if monitor is not None:
            height = min(height, monitor.get_workarea().height - 80)
        win.set_default_size(round(height * 0.57), height)
        win.set_icon_name(APP_ID)
        ensure_desktop_shortcut()
        view = GameView(self.game)
        win.add(view)
        win.connect("key-press-event", self.on_key, view)
        win.connect("delete-event", lambda *_: save_best(self.game.best) or False)
        win.show_all()
        self.window = win

    def on_key(self, _win, ev, view):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        if ev.keyval == Gdk.KEY_F2 or (ctrl and ev.keyval in (Gdk.KEY_n, Gdk.KEY_N)):
            view.new_game()
            return True
        if ctrl and ev.keyval in (Gdk.KEY_q, Gdk.KEY_Q):
            save_best(self.game.best)
            self.quit()
            return True
        return False


def main():
    GLib.set_prgname("blockfall")
    return BlockFallApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
