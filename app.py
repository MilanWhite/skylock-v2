#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, json, requests, math
from datetime import datetime, timezone
import pygame
from pygame.locals import QUIT, KEYDOWN, K_ESCAPE, MOUSEBUTTONUP

# ---------- Device/telemetry defaults ----------
DEVICE_ID = "DEV-123"
DEFAULT_LAT = 43.7000
DEFAULT_LON = -79.4000
DEFAULT_PDOP = 1.2
POST_URL = "http://192.168.137.1:4000/api/pings"

# ---------- Arrow math constants (assumed fixed for this build) ----------
# Device geodetic position (WGS-84) and height in meters:
DEV_LAT_DEG = 43.7000
DEV_LON_DEG = -79.4000
DEV_H_M = 250.0

# Nearest satellite position in ECEF meters:
SAT_ECEF_M = (15600000.0, -20400000.0, 13000000.0)

# Compass inputs assumed constant here:
MAG_HEADING_DEG = 15.0        # magnetic heading 0..360 (set from your sensor if available)
DECLINATION_DEG = 10.0        # magnetic→true correction for your location/date

# ---------- Config ----------
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480
FPS = 60
SEND_DELAY_MS = 3000  # 3 seconds

BG = (10, 12, 16)
CARD = (22, 26, 34)
TEXT = (230, 235, 240)
MUTED = (170, 178, 189)
BTN_BG = (36, 41, 51)
BTN_BG_HOVER = (48, 54, 65)
BTN_BORDER = (80, 90, 110)

# ---------- ENU helpers (WGS-84) ----------
_A = 6378137.0                      # semi-major axis (m)
_F = 1.0 / 298.257223563            # flattening
_E2 = _F * (2.0 - _F)               # first eccentricity squared
# ECEF→ENU rotation and az/el use standard formulas. :contentReference[oaicite:0]{index=0}

def geodetic_to_ecef(lat_deg, lon_deg, h_m):
    lat = math.radians(lat_deg); lon = math.radians(lon_deg)
    sL, cL = math.sin(lat), math.cos(lat)
    sλ, cλ = math.sin(lon), math.cos(lon)
    N = _A / math.sqrt(1.0 - _E2 * sL * sL)
    x = (N + h_m) * cL * cλ
    y = (N + h_m) * cL * sλ
    z = (N * (1.0 - _E2) + h_m) * sL
    return x, y, z  # meters
# WGS-84 parameters are standard. :contentReference[oaicite:1]{index=1}

def ecef_to_enu_vector(lat_deg, lon_deg, rx, ry, rz):
    lat = math.radians(lat_deg); lon = math.radians(lon_deg)
    sL, cL = math.sin(lat), math.cos(lat)
    sλ, cλ = math.sin(lon), math.cos(lon)
    e = -sλ*rx +  cλ*ry
    n = -sL*cλ*rx + -sL*sλ*ry + cL*rz
    u =  cL*cλ*rx +  cL*sλ*ry + sL*rz
    return e, n, u  # meters in ENU
# Local-tangent ENU construction and relative vector rotation are textbook. :contentReference[oaicite:2]{index=2}

def az_el_from_enu(e, n, u):
    az = math.degrees(math.atan2(e, n))                      # 0°=North, +East
    el = math.degrees(math.atan2(u, math.hypot(e, n)))
    return az, el
# Azimuth/elevation from ENU uses atan2(E,N) and atan2(U,√(E²+N²)). :contentReference[oaicite:3]{index=3}

def bearing_to_satellite_deg(dev_lat, dev_lon, dev_h_m, sat_ecef_xyz, heading_mag_deg, declination_deg):
    dx, dy, dz = geodetic_to_ecef(dev_lat, dev_lon, dev_h_m)
    rx = sat_ecef_xyz[0] - dx
    ry = sat_ecef_xyz[1] - dy
    rz = sat_ecef_xyz[2] - dz
    e, n, u = ecef_to_enu_vector(dev_lat, dev_lon, rx, ry, rz)
    az_deg, el_deg = az_el_from_enu(e, n, u)
    heading_true = (heading_mag_deg + declination_deg)
    # Screen arrow rotation relative to device heading:
    angle_screen = (az_deg - heading_true) % 360.0
    return angle_screen, el_deg

# ---------- Minimal UI primitives ----------
class Button:
    def __init__(self, rect, label, font, on_click=None, data=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.font = font
        self.on_click = on_click
        self.data = data
    def draw(self, surf, mouse_pos):
        hovered = self.rect.collidepoint(mouse_pos)
        bg = BTN_BG_HOVER if hovered else BTN_BG
        pygame.draw.rect(surf, bg, self.rect, border_radius=12)
        pygame.draw.rect(surf, BTN_BORDER, self.rect, width=2, border_radius=12)
        text_surf = self.font.render(self.label, True, TEXT)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surf.blit(text_surf, text_rect)
    def handle(self, event, mouse_pos):
        if event.type == MOUSEBUTTONUP and event.button == 1:
            if self.rect.collidepoint(mouse_pos):
                if self.on_click:
                    self.on_click(self)

def draw_centered_label(surf, font, line1, line2=None, y_frac=0.32):
    w, h = surf.get_size()
    y = int(h * y_frac)
    t1 = font.render(line1, True, TEXT)
    r1 = t1.get_rect(center=(w // 2, y))
    surf.blit(t1, r1)
    if line2:
        t2 = font.render(line2, True, MUTED)
        r2 = t2.get_rect(center=(w // 2, r1.bottom + 16))
        surf.blit(t2, r2)

def layout_buttons_center(labels, font, surf, cols=3, row_y=None, gap=20, btn_w=220, btn_h=70, on_click=None):
    w, h = surf.get_size()
    count = len(labels)
    if cols > count:
        cols = count
    rows = (count + cols - 1) // cols
    total_w = cols * btn_w + (cols - 1) * gap
    start_x = (w - total_w) // 2
    if row_y is None:
        block_h = rows * btn_h + (rows - 1) * gap
        start_y = (h - block_h) // 2 + 40
    else:
        start_y = row_y
    buttons = []
    i = 0
    for r in range(rows):
        y = start_y + r * (btn_h + gap)
        for c in range(cols):
            if i >= count:
                break
            x = start_x + c * (btn_w + gap)
            buttons.append(Button((x, y, btn_w, btn_h), labels[i], font, on_click=on_click, data=labels[i]))
            i += 1
    return buttons

# ---------- App State ----------
STATE_BEGIN = "begin"
STATE_POINT = "point"
STATE_DANGER_Q = "danger_q"
STATE_YES_FLOW = "yes_flow"
STATE_NO_FLOW = "no_flow"
STATE_SENDING = "sending"

class App:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True

        self.h1 = pygame.font.SysFont(None, 56)
        self.h2 = pygame.font.SysFont(None, 40)
        self.h3 = pygame.font.SysFont(None, 34)
        self.small = pygame.font.SysFont(None, 26)

        self.state = STATE_BEGIN
        self.buttons = []
        self.mouse_pos = (0, 0)

        # Flow memory
        self.answers = {
            "in_danger": None,
            "injured": None,
            "alone": None,
            "threat_active": None,
            "status": None,
        }

        # yes-flow questions
        self.yes_questions = [
            ("Are you injured?", "injured"),
            ("Are you alone?", "alone"),
            ("Is the threat still active?", "threat_active"),
        ]
        self.yes_index = 0

        self.sending_started_at = None
        self.post_result = None  # True/False/None

        # ---- Arrow graphics (build once) ----
        self.arrow_base = pygame.Surface((140, 140), pygame.SRCALPHA)
        cx, cy = 70, 70
        pygame.draw.polygon(self.arrow_base, TEXT, [(cx, 10), (cx-18, 60), (cx+18, 60)])
        pygame.draw.rect(self.arrow_base, TEXT, (cx-6, 60, 12, 58), border_radius=6)
        # Rotations are counter-clockwise by default; negative angle rotates clockwise. :contentReference[oaicite:4]{index=4}

        self.build_ui()

    # ---------- Helpers ----------
    def _answers_list(self):
        out = []
        order = ["in_danger", "injured", "alone", "threat_active", "status"]
        for k in order:
            v = self.answers.get(k)
            if v is None:
                continue
            if k == "status":
                mapping = {
                    "Checking in": "checking_in",
                    "Low Battery": "low_battery",
                    "Doing good": "doing_good",
                    "checking_in": "checking_in",
                    "low_battery": "low_battery",
                    "doing_good": "doing_good",
                }
                v = mapping.get(v, str(v).lower().replace(" ", "_"))
            out.append({"q": k, "a": v})
        return out

    def _build_payload(self):
        answers_list = self._answers_list()
        first = next((a for a in answers_list if a["q"] == "in_danger"), None)
        mode = "SOS" if (first and first["a"] == "yes") else "OK"
        payload = {
            "deviceId": DEVICE_ID,
            "ts": datetime.now(timezone.utc).isoformat(),
            "lat": DEFAULT_LAT,
            "lon": DEFAULT_LON,
            "mode": mode,
            "pdop": DEFAULT_PDOP,
            "answers": answers_list,
        }
        return payload

    def _post_payload(self, payload):
        try:
            r = requests.post(
                POST_URL,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=3,
            )
            return r.ok
        except Exception:
            return False

    # ---------- State transitions ----------
    def reset_to_begin(self):
        print("[payload]", self.answers, "post_ok:", self.post_result)
        self.answers = {k: None for k in self.answers.keys()}
        self.yes_index = 0
        self.post_result = None
        self.state = STATE_BEGIN
        self.build_ui()

    def goto_point(self):
        self.state = STATE_POINT
        self.build_ui()

    def goto_danger_question(self):
        self.state = STATE_DANGER_Q
        self.build_ui()

    def goto_yes_flow(self):
        self.state = STATE_YES_FLOW
        self.build_ui()

    def goto_no_flow(self):
        self.state = STATE_NO_FLOW
        self.build_ui()

    def goto_sending(self):
        self.state = STATE_SENDING
        self.sending_started_at = pygame.time.get_ticks()
        payload = self._build_payload()
        self.post_result = self._post_payload(payload)
        self.build_ui()

    # ---------- UI builders ----------
    def build_ui(self):
        self.buttons = []
        if self.state == STATE_BEGIN:
            def _start(_btn): self.goto_point()
            self.buttons = layout_buttons_center(
                ["Start"], self.h2, self.screen, cols=1, btn_w=260, btn_h=88, on_click=_start
            )
        elif self.state == STATE_POINT:
            def _cont(_btn): self.goto_danger_question()
            self.buttons = layout_buttons_center(
                ["Continue"], self.h2, self.screen, cols=1, btn_w=260, btn_h=88, on_click=_cont
            )
        elif self.state == STATE_DANGER_Q:
            def _danger_click(btn):
                choice = btn.data.lower()
                self.answers["in_danger"] = choice
                if choice == "yes":
                    self.yes_index = 0
                    self.goto_yes_flow()
                else:
                    self.goto_no_flow()
            self.buttons = layout_buttons_center(
                ["yes", "no"], self.h2, self.screen, cols=2, btn_w=220, btn_h=80, on_click=_danger_click
            )
        elif self.state == STATE_YES_FLOW:
            q_text, key = self.yes_questions[self.yes_index]
            def _yes_no(btn, key=key):
                self.answers[key] = btn.data.lower()
                self.yes_index += 1
                if self.yes_index >= len(self.yes_questions):
                    self.goto_sending()
                else:
                    self.build_ui()
            self.buttons = layout_buttons_center(
                ["yes", "no"], self.h2, self.screen, cols=2, btn_w=220, btn_h=80, on_click=_yes_no
            )
        elif self.state == STATE_NO_FLOW:
            def _status(btn):
                self.answers["status"] = btn.data
                self.goto_sending()
            self.buttons = layout_buttons_center(
                ["Checking in", "Low Battery", "Doing good"],
                self.h2, self.screen, cols=1, btn_w=320, btn_h=76, gap=18, on_click=_status
            )
        elif self.state == STATE_SENDING:
            self.buttons = []

    # ---------- Event loop ----------
    def handle_event(self, event):
        if event.type == QUIT:
            self.running = False
        elif event.type == KEYDOWN and event.key == K_ESCAPE:
            self.running = False
        elif event.type == MOUSEBUTTONUP:
            for b in self.buttons:
                b.handle(event, self.mouse_pos)

    # ---------- Draw ----------
    def draw(self):
        self.screen.fill(BG)
        pad = 16
        pygame.draw.rect(self.screen, CARD, (pad, pad, SCREEN_WIDTH - 2*pad, SCREEN_HEIGHT - 2*pad), border_radius=16)

        if self.state == STATE_BEGIN:
            draw_centered_label(self.screen, self.h1, "Begin Search")
            draw_centered_label(self.screen, self.h3, "Press Start to begin", y_frac=0.42)

        elif self.state == STATE_POINT:
            draw_centered_label(self.screen, self.h1, "Point device to sattelite...")
            draw_centered_label(self.screen, self.h3, "Align and press Continue", y_frac=0.42)

            # --- Arrow computation and drawing ---
            angle_deg, el_deg = bearing_to_satellite_deg(
                DEV_LAT_DEG, DEV_LON_DEG, DEV_H_M,
                SAT_ECEF_M,
                MAG_HEADING_DEG,
                DECLINATION_DEG
            )
            # Rotate arrow; negative angle = clockwise (matches compass rose). :contentReference[oaicite:5]{index=5}
            arrow = pygame.transform.rotate(self.arrow_base, -angle_deg)
            rect = arrow.get_rect(center=(SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.72)))
            self.screen.blit(arrow, rect)

            # Optional debug readout
            dbg = self.h3.render(f"bearing {angle_deg:.0f}°, el {el_deg:.0f}°", True, MUTED)
            self.screen.blit(dbg, (SCREEN_WIDTH//2 - dbg.get_width()//2, rect.bottom + 6))

        elif self.state == STATE_DANGER_Q:
            draw_centered_label(self.screen, self.h1, "Are you in danger?")

        elif self.state == STATE_YES_FLOW:
            q_text, _ = self.yes_questions[self.yes_index]
            draw_centered_label(self.screen, self.h1, q_text)

        elif self.state == STATE_NO_FLOW:
            draw_centered_label(self.screen, self.h1, "Select a status")

        elif self.state == STATE_SENDING:
            title = "Sending to sattelite..."
            if self.post_result is False:
                title = "Sending to sattelite... (retry later)"
            draw_centered_label(self.screen, self.h1, title)
            dots = ((pygame.time.get_ticks() // 400) % 4)
            msg = "." * dots
            hint = self.h3.render(msg, True, TEXT)
            rect = hint.get_rect(center=(SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.55)))
            self.screen.blit(hint, rect)

        for b in self.buttons:
            b.draw(self.screen, self.mouse_pos)

        footer = self.small.render("Press ESC to quit", True, MUTED)
        self.screen.blit(footer, (24, SCREEN_HEIGHT - 16 - footer.get_height()))

    # ---------- Update ----------
    def update(self):
        if self.state == STATE_SENDING and self.sending_started_at is not None:
            if pygame.time.get_ticks() - self.sending_started_at >= SEND_DELAY_MS:
                self.reset_to_begin()

    # ---------- Main loop ----------
    def run(self):
        while self.running:
            self.mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                self.handle_event(event)
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Satellite UI")
    app = App(screen)
    app.run()
    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
