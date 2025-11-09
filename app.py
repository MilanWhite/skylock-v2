#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, json, requests
from datetime import datetime, timezone
import pygame
from pygame.locals import QUIT, KEYDOWN, K_ESCAPE, MOUSEBUTTONUP

# ---------- Device/telemetry defaults ----------
DEVICE_ID = "DEV-123"
DEFAULT_LAT = 43.7000
DEFAULT_LON = -79.4000
DEFAULT_PDOP = 1.2
POST_URL = "http://192.168.137.1:4000/api/pings"  # include scheme

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
            "status": None,  # for "no" branch
        }

        # yes-flow questions in order
        self.yes_questions = [
            ("Are you injured?", "injured"),
            ("Are you alone?", "alone"),
            ("Is the threat still active?", "threat_active"),
        ]
        self.yes_index = 0

        self.sending_started_at = None
        self.post_result = None  # True/False/None

        self.build_ui()

    # ---------- Helpers ----------
    def _answers_list(self):
        """Return list of {'q': key, 'a': 'yes'|'no'|status} in fixed order."""
        out = []
        order = ["in_danger", "injured", "alone", "threat_active", "status"]
        for k in order:
            v = self.answers.get(k)
            if v is None:
                continue
            # normalize status labels to snake_case values
            if k == "status":
                mapping = {
                    "Checking in": "checking_in",
                    "Low Battery": "low_battery",
                    "Doing good": "doing_good",
                    # already-normalized values pass through
                    "checking_in": "checking_in",
                    "low_battery": "low_battery",
                    "doing_good": "doing_good",
                }
                v = mapping.get(v, str(v).lower().replace(" ", "_"))
            out.append({"q": k, "a": v})
        return out

    def _build_payload(self):
        answers_list = self._answers_list()
        # mode depends on first answer (in_danger)
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
        # Matches your required pattern; json= is simpler, but we follow your snippet. :contentReference[oaicite:1]{index=1}
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
        # Build and send immediately; UI continues to animate.
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
