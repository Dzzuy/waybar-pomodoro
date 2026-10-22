#!/usr/bin/env python3
"""Animated terminal companion for waybar-pomodoro.
Keys: space start/pause · s skip · r reset · q quit"""
import colorsys, math, os, random, select, shutil, subprocess, sys, termios, time, tty

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPT = os.environ.get("POMO_SCRIPT", os.path.join(HERE, "pomodoro.sh"))
STATE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "waybar-pomodoro", "state")
EVERY = int(os.environ.get("POMO_LONG_EVERY", 4))
DUR = {k: int(os.environ.get(e, d)) * 60 for k, e, d in
       (("work", "POMO_WORK", 25), ("short", "POMO_SHORT", 5), ("long", "POMO_LONG", 15))}
FPS = 24
THEMES = {"work": (0.95, 1.12, "FOCUS"), "short": (0.40, 0.52, "SHORT BREAK"), "long": (0.58, 0.78, "LONG BREAK")}
GRAY, DIM = (140, 140, 155), (62, 62, 74)
FONT = {
    "0": ["###", "# #", "# #", "# #", "###"], "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"], "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"], "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"], "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"], "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
}


def rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)


class Buf:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.ch = [[" "] * w for _ in range(h)]
        self.co = [[None] * w for _ in range(h)]

    def put(self, x, y, text, col):
        if not 0 <= y < self.h:
            return
        for i, c in enumerate(text):
            X = x + i
            if 0 <= X < self.w:
                self.ch[y][X] = c
                self.co[y][X] = col(X, y) if callable(col) else col

    def fill(self, x0, y0, x1, y1):
        for y in range(max(0, y0), min(self.h, y1)):
            for x in range(max(0, x0), min(self.w, x1)):
                self.ch[y][x], self.co[y][x] = " ", None

    def render(self):
        out, last = [], 0
        for y in range(self.h):
            out.append("\x1b[%d;1H" % (y + 1))
            for x in range(self.w):
                c = self.co[y][x]
                if c != last:
                    out.append("\x1b[0m" if c is None else "\x1b[38;2;%d;%d;%dm" % c)
                    last = c
                out.append(self.ch[y][x])
        return "".join(out)


def read_state():
    d = {"MODE": "work", "STATUS": "idle", "END": "0", "REMAIN": str(DUR["work"]), "COUNT": "0"}
    try:
        with open(STATE) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                d[k] = v
    except OSError:
        pass
    mode = d["MODE"] if d["MODE"] in DUR else "work"
    status = d["STATUS"]
    try:
        left = int(d["END"]) - time.time() if status == "running" else float(d["REMAIN"])
        count = int(d["COUNT"])
    except ValueError:
        left, count = DUR[mode], 0
    return mode, status, max(0.0, left), count


def make_space(W, H):
    return {"stars": [[random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.05, 1)]
                      for _ in range(max(40, W * H // 35))], "shoot": []}


def hsh(x, y, k):
    v = math.sin(x * 127.1 + y * 311.7 + k * 74.7) * 43758.5453
    return v - math.floor(v)


def draw_space(buf, W, H, t, sp, speed, hue):
    ch, co = buf.ch, buf.co
    for y in range(H):  # drifting nebula
        for x in range(W):
            n = math.sin(x * 0.045 + t * 0.05) * math.cos(y * 0.11 - t * 0.04) + math.sin((x + y * 2) * 0.025 + t * 0.03)
            if n > 0.9:
                k = min(1.0, (n - 0.9) / 0.8)
                ch[y][x] = "░" if k > 0.35 else "·"
                co[y][x] = rgb(hue(x * 0.4, y) + 0.08 * math.sin(x * 0.02), 0.7, 0.07 + 0.13 * k)
    cx, cy = W / 2, H / 2
    for y in range(H):  # blinking pixel dots around the outer edge
        for gx in range(W // 2):
            x = gx * 2
            d = max(abs(x - cx) / cx, abs(y - cy) / cy)
            if d < 0.82:
                continue
            ep = math.floor(t * 0.4 + hsh(gx, y, 9) * 10)
            r = hsh(gx, y, ep)
            if r < (d - 0.82) * 1.6:
                ch[y][x] = "■"
                co[y][x] = rgb(hue(x, y), 0.55, 0.22 + 0.3 * hsh(gx, y, ep + 0.5))
    for s in sp["stars"]:  # warp starfield
        s[2] -= speed / FPS
        if s[2] <= 0.04:
            s[0], s[1], s[2] = random.uniform(-1, 1), random.uniform(-1, 1), 1.0
        z = s[2]
        sx, sy = int(cx + s[0] / z * cx * 0.5), int(cy + s[1] / z * cy * 0.5)
        if not (0 <= sx < W and 0 <= sy < H):
            s[2] = 0
            continue
        b = (1 - z) ** 1.5
        c = "✦" if z < 0.15 else "•" if z < 0.35 else "∙" if z < 0.6 else "·"
        tw = 0.85 + 0.15 * math.sin(t * 5 + s[0] * 40)
        buf.put(sx, sy, c, rgb(hue(sx, sy), 0.25 * (1 - z), (0.22 + 0.78 * b) * tw))
    if random.random() < 0.012:
        sp["shoot"].append([random.uniform(0, W * 0.7), random.uniform(0, H * 0.4), random.uniform(1.2, 2.2)])
    for s in sp["shoot"][:]:
        s[0] += s[2] * 1.6
        s[1] += s[2] * 0.4
        for i in range(10):
            buf.put(int(s[0] - i * 1.6), int(s[1] - i * 0.4), "✦" if i == 0 else "•" if i < 3 else "·",
                    rgb(hue(s[0], s[1]), 0.15 + i * 0.04, 1 - i / 10))
        if s[0] - 16 > W or s[1] - 4 > H:
            sp["shoot"].remove(s)


def draw(W, H, t, st, parts, flash):
    mode, status, left, count = st
    a, b, label = THEMES[mode]
    hue = lambda x, y: a + (b - a) * (0.5 + 0.5 * math.sin(x * 0.07 + y * 0.15 - t * 1.4))
    hue0 = lambda x, y: a + (b - a) * (0.5 + 0.5 * math.sin(x * 0.07 + y * 0.15))  # frozen: digits stay still
    buf = Buf(W, H)
    secs = int(math.ceil(left))
    clock = "%02d:%02d" % (min(99, secs // 60), secs % 60)

    speed = {"running": 0.35 if left <= 60 else 0.12, "paused": 0.03}.get(status, 0.05) + flash * 1.5
    draw_space(buf, W, H, t, parts, speed, hue)

    sc = next((s for s in (3, 2, 1) if W >= 34 * s + 12 and H >= 5 * s + 14), 0)
    if not sc:
        buf.put((W - 5) // 2, H // 2, clock, lambda x, y: rgb(hue(x, y), 0.75, 1))
        return buf

    dw, dh = 34 * sc, 5 * sc
    bw, bh = dw + 10, dh + 12
    bx, by = (W - bw) // 2, max(0, (H - 1 - bh) // 2)
    buf.fill(bx, by, bx + bw, by + bh)
    border = lambda x, y: rgb(hue(x, y), 0.5, 0.45)
    buf.put(bx, by, "╭" + "─" * (bw - 2) + "╮", border)
    buf.put(bx, by + bh - 1, "╰" + "─" * (bw - 2) + "╯", border)
    for y in range(by + 1, by + bh - 1):
        buf.put(bx, y, "│", border)
        buf.put(bx + bw - 1, y, "│", border)

    title = "●  " + " ".join(label)
    buf.put((W - len(title)) // 2, by + 2, title, lambda x, y: rgb(hue(x, y), 0.55, 0.95))

    v, s = {"paused": (0.55, 0.45), "idle": (0.8, 0.6)}.get(status, (1.0, 0.75))
    s *= 1 - flash
    v = min(1.0, v + flash)
    dx, dy = (W - dw) // 2, by + 4
    dcol = lambda x, y: rgb(hue0(x, y), s, v)
    shadow = lambda x, y: rgb(hue0(x, y), 0.7, 0.22 * v)
    for colfn, ox, oy in ((shadow, 1, 1), (dcol, 0, 0)):
        px = 0
        for g in clock:
            rows = FONT[g]
            for ry, row in enumerate(rows):
                for rx, c in enumerate(row):
                    if c == "#":
                        for k in range(sc):
                            buf.put(dx + (px + rx) * 2 * sc + ox, dy + ry * sc + k + oy, "█" * (2 * sc), colfn)
            px += len(rows[0]) + 1

    total = DUR[mode] or 1
    pr = max(0.0, min(1.0, 1 - left / total))
    yb, fill = by + dh + 6, int(round(pr * dw))
    shim = (t * 0.5 % 1) * max(fill, 1)
    for i in range(dw):
        X = dx + i
        if i < fill:
            boost = max(0.0, 1 - abs(i - shim) / 5) * 0.4
            buf.put(X, yb, "━", rgb(hue(X, yb), 0.75 * (1 - boost), 0.95))
        else:
            buf.put(X, yb, "─", DIM)

    done = count % EVERY
    if mode == "long" and done == 0 and count > 0:
        done = EVERY
    dots = " ".join("●" if i < done else ("◉" if i == done and mode == "work" else "○") for i in range(EVERY))
    tail = "   %d done   %d%%" % (count, pr * 100)
    x0 = (W - len(dots) - len(tail)) // 2
    buf.put(x0, by + dh + 8, dots, lambda x, y: rgb(hue(x, y), 0.6, 0.9))
    buf.put(x0 + len(dots), by + dh + 8, tail, GRAY)

    if status == "paused":
        msg, col = "❚❚  paused", rgb(0.13, 0.5, 0.6 + 0.35 * math.sin(t * 4))
    elif status == "idle":
        msg, col = "press space to start", GRAY
    else:
        nxt = "break" if mode == "work" else "focus"
        msg, col = "%s at %s" % (nxt, time.strftime("%H:%M", time.localtime(time.time() + left))), GRAY
    buf.put((W - len(msg)) // 2, by + dh + 9, msg, col)

    hints = [("space", " start/pause   "), ("s", " skip   "), ("r", " reset   "), ("q", " quit")]
    x = (W - sum(len(k) + len(d) for k, d in hints)) // 2
    for k, d in hints:
        buf.put(x, H - 1, k, rgb(hue(x, H), 0.5, 0.75))
        x += len(k)
        buf.put(x, H - 1, d, DIM)
        x += len(d)
    return buf


def run(cmd):
    subprocess.run(["bash", SCRIPT, cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    out = sys.stdout
    out.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    try:
        tty.setcbreak(fd)
        size, parts, t0, last_poll, last_mode, flash = None, [], time.time(), 0.0, None, 0.0
        while True:
            now = time.time()
            if now - last_poll >= 1:
                run("status")  # lets the script handle phase transitions + notifications
                last_poll = now
            W, H = shutil.get_terminal_size((80, 24))
            if (W, H) != size:
                size = (W, H)
                out.write("\x1b[2J")
                parts = make_space(W, H)
            st = read_state()
            if last_mode and st[0] != last_mode:
                flash = 1.0
            last_mode = st[0]
            out.write(draw(W, H, now - t0, st, parts, flash).render())
            out.flush()
            flash *= 0.88
            r, _, _ = select.select([sys.stdin], [], [], 1 / FPS)
            if r:
                k = os.read(fd, 8).decode(errors="ignore")
                if k in ("q", "Q", "\x1b"):
                    break
                cmd = {" ": "toggle", "\r": "toggle", "\n": "toggle", "s": "skip", "r": "reset"}.get(k[:1])
                if cmd:
                    run(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()


if __name__ == "__main__":
    main()
