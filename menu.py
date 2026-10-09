"""Menu principal / Tela de configuração da sala."""
import pygame
from settings import *
from ui import draw_text, Button

MODES = ("Player vs IA", "Player vs Player", "Online: criar sala", "Online: entrar na sala")
DIFF_COLORS = ((90, 220, 120), (255, 214, 64), (255, 90, 90))

ALLOWED_CHARS = "0123456789.:abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-"

ROW_TOP = 192        # y da primeira linha
ROW_STEP = 82        # distância entre linhas


class Menu:
    def __init__(self):
        self.mode, self.rounds, self.points = 0, 3, 3
        self.diff = AI_DEFAULT_LEVEL
        self.addr = f"127.0.0.1:{NET_PORT}"
        self.allowed = [0, 2, 3] if MOBILE else [0, 1, 2, 3]     # no celular não há Player vs Player local
        self.focus = 0
        self.labels = {"mode": "MODO DE JOGO",
                       "diff": "DIFICULDADE DA IA",
                       "addr": "ENDEREÇO DO HOST (ip:porta)",
                       "rounds": "QUANTIDADE DE RODADAS (1 a 10)",
                       "points": "PONTOS MÁXIMOS POR RODADA (2 a 5)"}

    # ---------------------------------------------------------------- layout
    @property
    def rows(self):
        """A dificuldade só aparece no modo Player vs IA."""
        if self.mode == 0:
            return ["mode", "diff", "rounds", "points"]
        if self.mode == 3:                       # quem entra usa as regras do host
            return ["mode", "addr"]
        return ["mode", "rounds", "points"]

    @property
    def start_label(self):
        return ("INICIAR JOGO", "INICIAR JOGO", "CRIAR SALA", "ENTRAR NA SALA")[self.mode]

    def layout(self):
        rows = self.rows
        sel = []
        for i in range(len(rows)):
            y = ROW_TOP + ROW_STEP * i
            sel.append((pygame.Rect(280, y + 28, 50, 44),
                        pygame.Rect(340, y + 28, 320, 44),
                        pygame.Rect(670, y + 28, 50, 44)))
        start_y = ROW_TOP + ROW_STEP * len(rows) + 8
        start = pygame.Rect(350, start_y, 300, 62)
        panel = pygame.Rect(250, 170, 500, start.bottom + 24 - 170)
        return sel, start, panel

    # ---------------------------------------------------------------- lógica
    def adjust(self, row, delta):
        kind = self.rows[row]
        if kind == "mode":
            k = self.allowed.index(self.mode)
            self.mode = self.allowed[(k + delta) % len(self.allowed)]
            self.focus = min(self.focus, len(self.rows))
        elif kind == "diff":
            self.diff = max(0, min(len(AI_LEVELS) - 1, self.diff + delta))
        elif kind == "rounds":
            self.rounds = max(1, min(10, self.rounds + delta))
        elif kind == "points":
            self.points = max(2, min(5, self.points + delta))

    def value_text(self, kind):
        if kind == "mode":
            return MODES[self.mode]
        if kind == "diff":
            return AI_LEVELS[self.diff]["name"]
        if kind == "addr":
            return self.addr + ("|" if (pygame.time.get_ticks() // 450) % 2 == 0 else "")
        if kind == "rounds":
            return f"{self.rounds} rodada" + ("s" if self.rounds > 1 else "")
        return f"{self.points} pontos"

    def limits(self, kind):
        """(pode diminuir, pode aumentar)"""
        if kind == "diff":
            return self.diff > 0, self.diff < len(AI_LEVELS) - 1
        if kind == "rounds":
            return self.rounds > 1, self.rounds < 10
        if kind == "points":
            return self.points > 2, self.points < 5
        return True, True

    @property
    def editing_text(self):
        return self.focus < len(self.rows) and self.rows[self.focus] == "addr"

    def handle_event(self, e):
        """Retorna 'start' quando o jogo deve começar."""
        n = len(self.rows)
        if e.type == pygame.TEXTINPUT:             # teclado virtual do celular
            if MOBILE and self.editing_text:
                for ch in e.text:
                    if ch in ALLOWED_CHARS and len(self.addr) < 40:
                        self.addr += ch
            return None
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            sel, start, _panel = self.layout()
            if start.collidepoint(e.pos):
                return "start"
            for i, (l, box, r) in enumerate(sel):
                if l.collidepoint(e.pos):
                    self.focus = i
                    self.adjust(i, -1)
                    break
                if self.rows[i] == "addr":
                    self.focus = i
                    break
                if r.collidepoint(e.pos) or (self.rows[i] == "mode" and box.collidepoint(e.pos)):
                    self.focus = i
                    self.adjust(i, +1)
                    break
        elif e.type == pygame.KEYDOWN:
            on_addr = self.focus < n and self.rows[self.focus] == "addr"
            if on_addr and e.key not in (pygame.K_UP, pygame.K_DOWN, pygame.K_RETURN, pygame.K_KP_ENTER):
                if e.key == pygame.K_BACKSPACE:
                    self.addr = self.addr[:-1]
                elif e.key == pygame.K_v and (e.mod & pygame.KMOD_CTRL):
                    try:
                        pygame.scrap.init()
                        txt = pygame.scrap.get(pygame.SCRAP_TEXT)
                        if txt:
                            self.addr = (self.addr + txt.decode(errors="ignore").strip("\x00 \r\n"))[:40]
                    except Exception:
                        pass
                elif (not MOBILE) and e.unicode and e.unicode in ALLOWED_CHARS and len(self.addr) < 40:
                    self.addr += e.unicode
                return None
            if e.key == pygame.K_UP:
                self.focus = (self.focus - 1) % (n + 1)
            elif e.key == pygame.K_DOWN:
                self.focus = (self.focus + 1) % (n + 1)
            elif e.key == pygame.K_LEFT and self.focus < n:
                self.adjust(self.focus, -1)
            elif e.key == pygame.K_RIGHT and self.focus < n:
                self.adjust(self.focus, +1)
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return "start"
        return None

    # ---------------------------------------------------------------- desenho
    def _arrow(self, surf, rect, text, enabled):
        hover = rect.collidepoint(pygame.mouse.get_pos()) and enabled
        col = (90, 140, 240) if hover else ((60, 100, 190) if enabled else (50, 56, 70))
        pygame.draw.rect(surf, col, rect, border_radius=10)
        draw_text(surf, text, 40, WHITE if enabled else GRAY, rect.center, shadow=enabled)

    def draw(self, surf):
        surf.fill(BG)
        for r, a in ((330, 14), (230, 18), (130, 22)):
            pygame.draw.circle(surf, (28 + a, 40 + a, 56 + a), (WIDTH // 2, 340), r, 3)
        draw_text(surf, "PEBOLIM ARCADE", 104, YELLOW, (WIDTH // 2, 72))
        draw_text(surf, "Configuração da Sala", 36, LIGHT, (WIDTH // 2, 142))
        sel, start, panel = self.layout()
        pygame.draw.rect(surf, (0, 0, 0), panel.move(0, 6), border_radius=22)
        pygame.draw.rect(surf, (30, 40, 58), panel, border_radius=22)
        pygame.draw.rect(surf, (80, 100, 140), panel, 3, border_radius=22)
        for i, kind in enumerate(self.rows):
            l, box, r = sel[i]
            draw_text(surf, self.labels[kind], 26, LIGHT, (box.centerx, l.y - 12))
            pygame.draw.rect(surf, (18, 24, 36), box, border_radius=10)
            pygame.draw.rect(surf, YELLOW if self.focus == i else (80, 100, 140), box, 3, border_radius=10)
            color = DIFF_COLORS[self.diff] if kind == "diff" else WHITE
            draw_text(surf, self.value_text(kind), 30 if kind == "addr" else 36, color, box.center)
            if kind == "addr":
                continue
            can_l, can_r = self.limits(kind)
            self._arrow(surf, l, "<", can_l)
            self._arrow(surf, r, ">", can_r)
        Button(start, self.start_label, (40, 160, 80)).draw(surf, focused=(self.focus == len(self.rows)))
        hint = ("Toque nas setas para ajustar" if MOBILE else
                "Mouse ou setas para ajustar  |  ENTER inicia  |  Máx. 1 giro por chute (sem roletão)")
        draw_text(surf, hint, 22, GRAY, (WIDTH // 2, 668))
