"""Controles na tela para celular: analógico à esquerda, botões à direita (multi-toque)."""
import math
import pygame
from settings import *
from ui import draw_text

DEAD = 22          # zona morta do analógico (px lógicos)
FOLLOW = 60        # o analógico "segue" o dedo para inverter rápido


class TouchControls:
    def __init__(self):
        rx = PAD + WIDTH                                   # início do painel direito
        self.stick_zone = pygame.Rect(0, 0, PAD, HEIGHT)
        self.rod_btns = {"G": pygame.Rect(rx + 12, 96, 84, 84), "D": pygame.Rect(rx + 104, 96, 84, 84),
                         "M": pygame.Rect(rx + 12, 192, 84, 84), "A": pygame.Rect(rx + 104, 192, 84, 84)}
        self.rod_labels = {"G": "GOL", "D": "DEF", "M": "MEIO", "A": "ATQ"}
        self.pause_rect = pygame.Rect(rx + 138, 12, 50, 50)
        self.ctrl_c, self.ctrl_r = (rx + 100, 372), 62
        self.kick_c, self.kick_r = (rx + 100, 566), 90
        self.reset()

    def reset(self):
        self.fingers = {}
        self.axis = 0
        self.actions = []
        self.stick_o = self.stick_p = None

    def pop_actions(self):
        a, self.actions = self.actions, []
        return a

    @staticmethod
    def _hit(c, r, x, y):
        return math.hypot(x - c[0], y - c[1]) <= r

    # ---------------------------------------------------------------- eventos
    def down(self, fid, x, y):
        if self.stick_zone.collidepoint(x, y):
            self.fingers[fid] = "stick"
            self.stick_o, self.stick_p = [x, y], [x, y]
            self.axis = 0
            return
        for kind, rc in self.rod_btns.items():
            if rc.collidepoint(x, y):
                self.actions.append("sel:" + kind)
                self.fingers[fid] = "btn"
                return
        if self.pause_rect.collidepoint(x, y):
            self.actions.append("pause")
            self.fingers[fid] = "btn"
        elif self._hit(self.ctrl_c, self.ctrl_r, x, y):
            self.actions.append("control")
            self.fingers[fid] = "btn"
        elif self._hit(self.kick_c, self.kick_r + 10, x, y):
            self.actions.append("kick_down")
            self.fingers[fid] = "kick"

    def move(self, fid, x, y):
        if self.fingers.get(fid) != "stick" or self.stick_o is None:
            return
        self.stick_p = [x, y]
        dy = y - self.stick_o[1]
        if abs(dy) > FOLLOW:                               # origem acompanha o dedo
            self.stick_o[1] = y - FOLLOW * (1 if dy > 0 else -1)
            dy = y - self.stick_o[1]
        self.axis = -1 if dy < -DEAD else (1 if dy > DEAD else 0)

    def up(self, fid):
        role = self.fingers.pop(fid, None)
        if role == "stick":
            self.axis = 0
            self.stick_o = self.stick_p = None
        elif role == "kick":
            self.actions.append("kick_up")

    # ----------------------------------------------------------------- desenho
    def _build_static(self):
        """Painéis e botões no estado "desligado", desenhados UMA vez (o resto é só o que muda)."""
        st = pygame.Surface((LW, LH))
        pygame.draw.rect(st, (14, 18, 26), (0, 0, PAD, HEIGHT))
        pygame.draw.rect(st, (14, 18, 26), (PAD + WIDTH, 0, PAD, HEIGHT))
        for kind, rc in self.rod_btns.items():
            pygame.draw.rect(st, (36, 46, 64), rc, border_radius=14)
            pygame.draw.rect(st, (90, 105, 140), rc, 3, border_radius=14)
            draw_text(st, self.rod_labels[kind], 26, WHITE, rc.center)
        pygame.draw.rect(st, (36, 46, 64), self.pause_rect, border_radius=10)
        pygame.draw.rect(st, (90, 105, 140), self.pause_rect, 3, border_radius=10)
        for dx in (-7, 7):
            pygame.draw.rect(st, WHITE, (self.pause_rect.centerx + dx - 4, self.pause_rect.centery - 12, 8, 24))
        self._draw_ctrl(st, False)
        self._draw_kick(st, False, TEAM_COLORS[0])
        idle = pygame.Surface((PAD, HEIGHT))
        idle.blit(st, (0, 0), (0, 0, PAD, HEIGHT))
        cx, cy = PAD // 2, HEIGHT // 2
        pygame.draw.circle(idle, (28, 36, 52), (cx, cy), 72)
        pygame.draw.polygon(idle, (90, 105, 140), [(cx, cy - 60), (cx - 20, cy - 30), (cx + 20, cy - 30)])
        pygame.draw.polygon(idle, (90, 105, 140), [(cx, cy + 60), (cx - 20, cy + 30), (cx + 20, cy + 30)])
        draw_text(idle, "ARRASTE", 24, (150, 160, 180), (cx, cy + 110), shadow=False)
        draw_text(idle, "mover / mirar", 20, (110, 120, 140), (cx, cy + 134), shadow=False)
        try:
            st, idle = st.convert(), idle.convert()
        except Exception:
            pass
        self._static, self._idle = st, idle

    def _draw_ctrl(self, surf, holding):
        c = self.ctrl_c
        pygame.draw.circle(surf, (200, 140, 30) if holding else (36, 46, 64), c, self.ctrl_r)
        pygame.draw.circle(surf, WHITE if holding else (90, 105, 140), c, self.ctrl_r, 3)
        draw_text(surf, "SOLTAR" if holding else "CONTROLE", 24, WHITE, c)

    def _draw_kick(self, surf, pressed, col):
        k = self.kick_c
        pygame.draw.circle(surf, col if pressed else (36, 46, 64), k, self.kick_r)
        pygame.draw.circle(surf, WHITE if pressed else (90, 105, 140), k, self.kick_r, 4)
        draw_text(surf, "CHUTE", 34, WHITE, k)
        draw_text(surf, "segure e solte", 20, (170, 180, 200), (k[0], k[1] + 28), shadow=False)

    def draw(self, surf, match=None, team=0):
        if getattr(self, "_static", None) is None:
            self._build_static()
        # painéis prontos (só as duas laterais; o centro é o campo)
        surf.blit(self._static, (0, 0), (0, 0, PAD, HEIGHT))
        surf.blit(self._static, (PAD + WIDTH, 0), (PAD + WIDTH, 0, PAD, HEIGHT))
        col = TEAM_COLORS[team]
        if self.stick_o:                                   # analógico ativo
            ox, oy = int(self.stick_o[0]), int(self.stick_o[1])
            pygame.draw.circle(surf, (40, 50, 70), (ox, oy), 72)
            pygame.draw.circle(surf, (90, 105, 140), (ox, oy), 72, 3)
            ky = max(oy - 60, min(oy + 60, int(self.stick_p[1])))
            pygame.draw.circle(surf, col, (ox, ky), 34)
        else:
            surf.blit(self._idle, (0, 0))
        sel = match.selected(team).kind if match else None
        if sel in self.rod_btns:                           # só a haste escolhida muda de aparência
            rc = self.rod_btns[sel]
            pygame.draw.rect(surf, col, rc, border_radius=14)
            pygame.draw.rect(surf, WHITE, rc, 3, border_radius=14)
            draw_text(surf, self.rod_labels[sel], 26, WHITE, rc.center)
        if match and match.ctrl[team]:
            self._draw_ctrl(surf, True)
        if "kick" in self.fingers.values():
            self._draw_kick(surf, True, col)
