"""Menu principal / Tela de configuração da sala."""
import pygame
from settings import *
from ui import draw_text, Button
import clip

MODES = ("Player vs IA", "Player vs Player", "Online: criar sala", "Online: entrar na sala")
DIFF_COLORS = ((90, 220, 120), (255, 214, 64), (255, 90, 90))

ALLOWED_CHARS = "0123456789.:abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-"

ROW_TOP = 214        # y da primeira linha (logo da imagem ocupa o topo)
ROW_STEP = 72        # distância entre linhas


class Menu:
    def __init__(self):
        self.mode, self.rounds, self.points = 0, 3, 3
        self.diff = AI_DEFAULT_LEVEL
        self.addr = ""
        self.allowed = [0, 2, 3] if MOBILE else [0, 1, 2, 3]     # no celular não há Player vs Player local
        self.focus = 0
        self.bg = self._load_bg()
        self.pad_color = (12, 45, 81)                 # cor das laterais (celular) combinando com a imagem
        self._panel_cache = {}
        self.labels = {"mode": "MODO DE JOGO",
                       "diff": "DIFICULDADE DA IA",
                       "addr": "CÓDIGO DA SALA (ou ip:porta)",
                       "rounds": "QUANTIDADE DE RODADAS (1 a 10)",
                       "points": "PONTOS MÁXIMOS POR RODADA (2 a 5)"}

    @staticmethod
    def _load_bg():
        try:
            img = pygame.image.load(resource_path("assets/menu_bg.png"))
            try:
                return img.convert()
            except Exception:
                return img
        except Exception:
            return None                                # sem a imagem: fundo liso, o jogo funciona igual

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

    @property
    def note(self):
        """Aviso curto sobre o modo online (aparece abaixo do botão)."""
        if self.mode == 2:
            return ("Você recebe um CÓDIGO para passar ao amigo (qualquer internet)" if RELAY_SERVER
                    else "Servidor online não configurado: só mesma rede Wi-Fi / VPN")
        if self.mode == 3:
            return "Digite o código que o amigo passou"
        return ""

    def layout(self):
        rows = self.rows
        sel = []
        for i in range(len(rows)):
            y = ROW_TOP + ROW_STEP * i
            if rows[i] == "addr":          # caixa de texto + botão COLAR
                sel.append((pygame.Rect(0, 0, 0, 0), pygame.Rect(280, y + 26, 320, 42),
                            pygame.Rect(610, y + 26, 110, 42)))
                continue
            sel.append((pygame.Rect(280, y + 26, 48, 42),
                        pygame.Rect(336, y + 26, 328, 42),
                        pygame.Rect(672, y + 26, 48, 42)))
        start_y = ROW_TOP + ROW_STEP * len(rows) + 4
        start = pygame.Rect(350, start_y, 300, 56)
        bottom = start.bottom + (46 if self.note else 20)
        panel = pygame.Rect(240, ROW_TOP - 12, 520, bottom - (ROW_TOP - 12))
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

    def paste(self):
        txt = "".join(ch for ch in clip.paste().strip() if ch in ALLOWED_CHARS)
        if txt:
            self.addr = txt.upper()[:40]

    def value_text(self, kind):
        if kind == "mode":
            return MODES[self.mode]
        if kind == "diff":
            return AI_LEVELS[self.diff]["name"]
        if kind == "addr":
            cur = "|" if (pygame.time.get_ticks() // 450) % 2 == 0 else ""
            return (self.addr + cur) if self.addr or self.focus < len(self.rows) and self.rows[self.focus] == "addr" else "digite o código"
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
                        self.addr += ch.upper()
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
                    if r.collidepoint(e.pos):
                        self.focus = i
                        self.paste()
                        break
                    if box.collidepoint(e.pos):
                        self.focus = i
                        break
                    continue
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
                    self.paste()
                elif (not MOBILE) and e.unicode and e.unicode in ALLOWED_CHARS and len(self.addr) < 40:
                    self.addr += e.unicode.upper()
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
    def _arrow(self, surf, rect, text, enabled, size=40):
        hover = rect.collidepoint(pygame.mouse.get_pos()) and enabled
        col = (90, 140, 240) if hover else ((60, 100, 190) if enabled else (50, 56, 70))
        pygame.draw.rect(surf, col, rect, border_radius=10)
        draw_text(surf, text, size, WHITE if enabled else GRAY, rect.center, shadow=enabled)

    def _panel_surf(self, size):
        """Painel translúcido (criado uma vez por tamanho)."""
        p = self._panel_cache.get(size)
        if p is None:
            p = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(p, (10, 20, 38, 205), p.get_rect(), border_radius=22)
            pygame.draw.rect(p, (110, 140, 200, 230), p.get_rect(), 3, border_radius=22)
            try:
                p = p.convert_alpha()
            except Exception:
                pass
            self._panel_cache[size] = p
        return p

    def draw(self, surf):
        if self.bg is not None:
            surf.blit(self.bg, (0, 0))
        else:
            surf.fill(BG)
            draw_text(surf, "PEBOLIM ARCADE", 104, YELLOW, (WIDTH // 2, 100))
        sel, start, panel = self.layout()
        surf.blit(self._panel_surf((panel.w, panel.h)), panel.topleft)
        for i, kind in enumerate(self.rows):
            l, box, r = sel[i]
            draw_text(surf, self.labels[kind], 22, LIGHT, (box.centerx, box.y - 13))
            pygame.draw.rect(surf, (18, 24, 36), box, border_radius=10)
            pygame.draw.rect(surf, YELLOW if self.focus == i else (80, 100, 140), box, 3, border_radius=10)
            color = DIFF_COLORS[self.diff] if kind == "diff" else WHITE
            if kind == "addr" and not self.addr and not self.editing_text:
                color = GRAY
            draw_text(surf, self.value_text(kind), 28 if kind == "addr" else 32, color, box.center)
            if kind == "addr":
                self._arrow(surf, r, "COLAR", True, 22)
                continue
            can_l, can_r = self.limits(kind)
            self._arrow(surf, l, "<", can_l)
            self._arrow(surf, r, ">", can_r)
        Button(start, self.start_label, (40, 160, 80)).draw(surf, focused=(self.focus == len(self.rows)))
        if self.note:
            draw_text(surf, self.note, 20, YELLOW, (WIDTH // 2, start.bottom + 24))
        hint = ("Toque nas setas para ajustar" if MOBILE else
                "Mouse ou setas para ajustar  |  ENTER inicia")
        draw_text(surf, hint, 20, LIGHT, (16, HEIGHT - 14), "midleft")
        draw_text(surf, CREDIT, 20, WHITE, (WIDTH - 14, HEIGHT - 28), "midright")
        draw_text(surf, "v" + VERSION, 18, LIGHT, (WIDTH - 14, HEIGHT - 10), "midright")
