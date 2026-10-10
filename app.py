"""Pebolim Arcade - o jogo em si. O ponto de entrada é o main.py (que mostra erros na tela)."""
import sys
import pygame

pygame.mixer.pre_init(22050, -16, 1, 512)
pygame.init()

from settings import *
from ui import draw_text, dim, Button
from menu import Menu
from game import Match
from sound import Sound
from net import Listener, Connector, RelayHost, RelayJoin, is_room_code, local_ip
import clip
from touch import TouchControls

UP_KEYS = (pygame.K_w, pygame.K_UP)
DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)
# teclas -> ações enviadas ao host (o cliente online joga com W/S, A/D, ESPAÇO, C ou setas)
ACT_KEYS = {pygame.K_a: "left", pygame.K_LEFT: "left", pygame.K_d: "right", pygame.K_RIGHT: "right",
            pygame.K_c: "control", pygame.K_LSHIFT: "control", pygame.K_RSHIFT: "control",
            pygame.K_1: "sel:G", pygame.K_2: "sel:D", pygame.K_3: "sel:M", pygame.K_4: "sel:A"}
KICK_KEYS = (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_RCTRL)


class App:
    def __init__(self):
        try:                                        # ícone da janela (PC)
            pygame.display.set_icon(pygame.image.load(resource_path("assets/icon_64.png")))
        except Exception:
            pass
        self.window = None
        self.manual_scale = False
        self._scaled = None
        if MOBILE:      # tela lógica LWxLH (painéis de toque + campo); SCALED ajusta ao tamanho do celular
            flags = pygame.SCALED | (pygame.FULLSCREEN if ANDROID else 0)
            try:
                self.screen = pygame.display.set_mode((LW, LH), flags)
            except Exception:
                self.screen = pygame.display.set_mode((0, 0))        # tamanho nativo do aparelho
            if self.screen.get_size() != (LW, LH):
                # SCALED não funcionou: desenha numa tela lógica e escala "na mão" para a janela
                self.window = self.screen
                self.screen = pygame.Surface((LW, LH))
                self.manual_scale = True
            self.view = self.screen.subsurface(pygame.Rect(PAD, 0, WIDTH, HEIGHT))
            self.touch = TouchControls()
        else:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            self.view = self.screen
            self.touch = None
        self._text_input = False
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.sound = Sound()
        self.menu = Menu()
        self.state = "menu"                 # menu | lobby | game | over
        self.role = "local"                 # local | host | client
        self.match = None
        self.config = None
        self.paused = False
        self.peer = self.listener = self.connector = None
        self.msg, self.msg_t = "", 0.0
        self.lobby_t = 0.0
        self.my_ip = ""
        self.code_rect = pygame.Rect(0, 0, 0, 0)    # área clicável do código/endereço (copiar)
        self.copied_t = 0.0
        self.copy_ok = True
        self.join_wait = 0.0
        self.btn_continue = Button((350, 300, 300, 58), "CONTINUAR", (40, 160, 80))
        self.btn_pause_menu = Button((350, 375, 300, 58), "VOLTAR AO MENU", (170, 70, 70))
        self.btn_replay = Button((330, 470, 340, 60), "REJOGAR", (40, 160, 80))
        self.btn_menu = Button((330, 550, 340, 60), "VOLTAR AO MENU", (60, 110, 210))
        self.btn_cancel = Button((350, 560, 300, 60), "CANCELAR", (170, 70, 70))

    # ---------------------------------------------------------------- fluxo
    def start_match(self):
        m = self.menu
        self.msg = ""
        if m.mode in (0, 1):
            self.role = "local"
            self.config = ("ia" if m.mode == 0 else "pvp", m.rounds, m.points, m.diff)
            self.match = self.setup_touch(Match(*self.config, sound=self.sound), 0)
            self.state, self.paused = "game", False
        elif m.mode == 2:
            self.role = "host"
            self.config = (m.rounds, m.points)
            if RELAY_SERVER:                            # sala por código (qualquer internet)
                self.listener = RelayHost(RELAY_SERVER)
            else:                                       # sem servidor: modo direto ip:porta
                self.listener = Listener(NET_PORT)
                if self.listener.error:
                    self.leave(self.listener.error)
                    return
                self.my_ip = local_ip()
            self.state, self.lobby_t, self.copied_t = "lobby", 0.0, 0.0
        else:
            code = m.addr.strip()
            if not code:
                self.msg, self.msg_t = "Digite o código da sala (ou cole com COLAR).", 5.0
                return
            if is_room_code(code):
                if not RELAY_SERVER:
                    self.msg, self.msg_t = "Código de sala precisa do servidor online (veja o README).", 6.0
                    return
                self.connector = RelayJoin(RELAY_SERVER, code)
            else:
                self.connector = Connector(code, NET_PORT)
            self.role = "client"
            self.state, self.lobby_t, self.join_wait = "lobby", 0.0, 0.0

    def setup_touch(self, mt, team):
        """Celular: o time `team` é controlado pelos botões da tela (não pelo teclado)."""
        if MOBILE:
            mt.local = [False, False]
            mt.hints = False
            mt.key_names = (["CONTROLE", "CONTROLE"], ["ARRASTE", "ARRASTE"], ["CHUTE", "CHUTE"])
            self.touch.reset()
        return mt

    def make_host_match(self):
        rounds, points = self.config
        mt = Match("pvp", rounds, points, sound=self.sound)
        mt.local = [True, False]            # o Player 2 é o jogador remoto
        mt.view_team = 0
        mt.merge_keys(0)                    # host joga com WASD ou setas
        mt.names = ("Player 1 (VOCÊ)", "Player 2")
        return self.setup_touch(mt, 0)

    def make_view_match(self, rounds, points):
        mt = Match("pvp", rounds, points, sound=self.sound)
        mt.local = [False, False]           # o cliente só desenha o que o host manda
        mt.view_team = 1
        mt.names = ("Player 1", "Player 2 (VOCÊ)")
        mt.key_names = (["C", "C"], ["W/S", "W/S"], ["ESPAÇO", "ESPAÇO"])
        return self.setup_touch(mt, 1)

    def leave(self, message=""):
        """Volta ao menu fechando qualquer conexão."""
        if self.peer:
            self.peer.send({"t": "bye"})
            self.peer.close()
        if self.listener:
            self.listener.close()
        self.peer = self.listener = self.connector = None
        self.role = "local"
        self.state, self.paused = "menu", False
        self.msg, self.msg_t = message, 6.0

    # --------------------------------------------------------------- eventos
    def handle(self, e):
        if self.state == "menu":
            if self.menu.handle_event(e) == "start":
                self.start_match()
        elif self.state == "lobby":
            if self.btn_cancel.clicked(e) or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                self.leave()
            elif (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.role == "host"
                  and self.code_rect.collidepoint(e.pos)):
                self.copy_ok = clip.copy(self.listener.code or f"{self.my_ip}:{NET_PORT}")
                self.copied_t = 2.5
        elif self.state == "game":
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_p):
                self.paused = not self.paused
            elif self.paused:
                if self.btn_continue.clicked(e):
                    self.paused = False
                elif self.btn_pause_menu.clicked(e):
                    self.leave() if self.role != "local" else self.to_menu()
            elif self.role == "client":
                self.client_event(e)
            else:
                self.match.handle_event(e)
        elif self.state == "over":
            if self.role != "client" and (self.btn_replay.clicked(e) or
                                          (e.type == pygame.KEYDOWN and e.key == pygame.K_r)):
                self.rematch()
            elif self.btn_menu.clicked(e) or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                self.leave() if self.role != "local" else self.to_menu()

    def to_menu(self):
        self.state, self.paused = "menu", False

    def rematch(self):
        if self.role == "host":
            self.match = self.make_host_match()
            self.peer.send({"t": "start", "rounds": self.config[0], "points": self.config[1]})
        else:
            self.match = self.setup_touch(Match(*self.config, sound=self.sound), 0)
        self.state = "game"

    def letterbox(self):
        """(escala, desvio x, desvio y) da tela lógica dentro da janela (sem SCALED)."""
        ww, wh = self.window.get_size()
        sc = min(ww / LW, wh / LH)
        return sc, (ww - LW * sc) / 2, (wh - LH * sc) / 2

    def to_logical(self, pos):
        if not self.manual_scale:
            return pos
        sc, ox, oy = self.letterbox()
        return (pos[0] - ox) / sc, (pos[1] - oy) / sc

    def finger_pos(self, e):
        """Posição normalizada do dedo -> coordenadas lógicas (LWxLH), considerando as faixas pretas."""
        ww, wh = pygame.display.get_window_size()
        sc = min(ww / LW, wh / LH)
        return (e.x * ww - (ww - LW * sc) / 2) / sc, (e.y * wh - (wh - LH * sc) / 2) / sc

    def mobile_event(self, e):
        """Converte toques em controles. Retorna o evento a repassar ao jogo (ou None)."""
        t = e.type
        playing = self.state == "game" and not self.paused
        if t in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            if playing:
                x, y = self.finger_pos(e)
                fid = e.finger_id
                (self.touch.down if t == pygame.FINGERDOWN else
                 self.touch.move if t == pygame.FINGERMOTION else
                 (lambda f, *_: self.touch.up(f)))(fid, x, y)
            return None
        if t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if playing and not getattr(e, "touch", False):     # mouse faz o papel de um dedo (teste no PC)
                x, y = self.to_logical(e.pos)
                if t == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.touch.down("mouse", x, y)
                elif t == pygame.MOUSEMOTION and e.buttons[0]:
                    self.touch.move("mouse", x, y)
                elif t == pygame.MOUSEBUTTONUP and e.button == 1:
                    self.touch.up("mouse")
            d = dict(e.dict)
            lx, ly = self.to_logical(e.pos)
            d["pos"] = (lx - PAD, ly)                         # menus/botões usam coordenadas do campo
            return pygame.event.Event(t, d)
        return e

    def apply_touch(self):
        """Aplica ao jogo o que os botões da tela pediram neste quadro."""
        if not MOBILE:
            return
        if not (self.state == "game" and not self.paused):
            self.touch.reset()
            return
        for a in self.touch.pop_actions():
            if a == "pause":
                self.paused = True
                self.touch.reset()
                return
            if self.role == "client":
                self.peer.send({"t": "act", "a": a})
            else:
                self.match.do_action(0, a)
        if self.role != "client":
            self.match.set_axis(0, self.touch.axis)

    def client_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in KICK_KEYS:
                self.peer.send({"t": "act", "a": "kick_down"})
            elif e.key in ACT_KEYS:
                self.peer.send({"t": "act", "a": ACT_KEYS[e.key]})
        elif e.type == pygame.KEYUP and e.key in KICK_KEYS:
            self.peer.send({"t": "act", "a": "kick_up"})

    # ------------------------------------------------------------ atualização
    def update(self, dt):
        self.msg_t = max(0.0, self.msg_t - dt)
        self.copied_t = max(0.0, self.copied_t - dt)
        self.apply_touch()
        if MOBILE:                                 # teclado virtual só quando o campo de endereço está em foco
            want = self.state == "menu" and self.menu.editing_text
            if want != self._text_input:
                (pygame.key.start_text_input if want else pygame.key.stop_text_input)()
                self._text_input = want
        if self.state == "lobby":
            self.update_lobby(dt)
        elif self.state in ("game", "over") and self.role == "host":
            self.update_host(dt)
        elif self.state in ("game", "over") and self.role == "client":
            self.update_client(dt)
        elif self.state == "game" and not self.paused:
            self.match.update(dt, pygame.key.get_pressed())
            if self.match.finished:
                self.state = "over"
                self.sound.play("win")

    def update_lobby(self, dt):
        self.lobby_t += dt
        if self.role == "host":
            if self.listener.error:
                self.leave(self.listener.error)
                return
            if self.listener.peer is not None:
                self.peer = self.listener.peer
                self.listener.close()
                self.listener = None
                self.match = self.make_host_match()
                self.peer.send({"t": "start", "rounds": self.config[0], "points": self.config[1]})
                self.state, self.paused = "game", False
        else:
            if self.connector.done and self.connector.error:
                self.leave(self.connector.error)
            elif self.connector.done:
                self.peer = self.peer or self.connector.peer
                self.join_wait += dt
                for msg in self.peer.poll():
                    if msg.get("t") == "start":
                        self.match = self.make_view_match(int(msg.get("rounds", 3)), int(msg.get("points", 3)))
                        self.state, self.paused = "game", False
                        return
                if self.peer.timed_out() or self.join_wait > 15:
                    self.leave("O host não respondeu.")

    def update_host(self, dt):
        for msg in self.peer.poll():
            t = msg.get("t")
            if t == "in":
                self.match.set_axis(1, msg.get("m", 0))
            elif t == "act":
                self.match.do_action(1, str(msg.get("a", "")))
            elif t == "bye":
                self.leave("O outro jogador saiu da partida.")
                return
        if self.state == "game":
            self.match.update(dt, pygame.key.get_pressed())
            if self.match.finished:
                self.state = "over"
                self.sound.play("win")
        if not self.peer.send(self.match.snapshot()) or self.peer.timed_out():
            self.leave("O outro jogador desconectou.")

    def update_client(self, dt):
        latest = None
        for msg in self.peer.poll():
            t = msg.get("t")
            if t == "snap":
                latest = msg
            elif t == "start":                      # revanche
                self.match = self.make_view_match(int(msg.get("rounds", 3)), int(msg.get("points", 3)))
                self.state, self.paused = "game", False
                latest = None
            elif t == "bye":
                self.leave("O host saiu da partida.")
                return
        if latest:
            self.match.apply_snapshot(latest)
            if self.match.finished and self.state == "game":
                self.state = "over"
                self.sound.play("win")
        keys = pygame.key.get_pressed()
        axis = (1 if any(keys[k] for k in DOWN_KEYS) else 0) - (1 if any(keys[k] for k in UP_KEYS) else 0)
        if MOBILE:
            axis = self.touch.axis
        self.peer.send({"t": "in", "m": axis})
        if self.peer.timed_out():
            self.leave("Conexão com o host perdida.")

    # ---------------------------------------------------------------- desenho
    def draw_lobby(self, s):
        s.fill(BG)
        dots = "." * (int(self.lobby_t * 2) % 4)
        if self.role == "host":
            draw_text(s, "AGUARDANDO O OUTRO JOGADOR" + dots, 52, YELLOW, (WIDTH // 2, 100))
            code = getattr(self.listener, "code", "")
            if RELAY_SERVER:
                if code:
                    draw_text(s, "CÓDIGO DA SALA", 34, LIGHT, (WIDTH // 2, 200))
                    r = draw_text(s, "  ".join(code), 130, WHITE, (WIDTH // 2, 290))
                    self.code_rect = r.inflate(60, 40)
                    pygame.draw.rect(s, YELLOW if self.copied_t > 0 else (80, 100, 140), self.code_rect, 3,
                                     border_radius=18)
                    if self.copied_t > 0:
                        msg, col = (("COPIADO!", (90, 220, 120)) if self.copy_ok
                                    else ("Não consegui copiar - anote o código", (255, 120, 120)))
                    else:
                        msg, col = "Toque no código para copiar", GRAY
                    draw_text(s, msg, 28, col, (WIDTH // 2, 385))
                    for i, t in enumerate(["Passe o código para o amigo.",
                                           "Ele escolhe 'Online: entrar na sala' e digita o código.",
                                           "Funciona em qualquer internet (Wi-Fi, 4G, outro país)."]):
                        draw_text(s, t, 26, GRAY, (WIDTH // 2, 450 + i * 34))
                else:
                    draw_text(s, "Criando a sala" + dots, 48, WHITE, (WIDTH // 2, 260))
                    draw_text(s, self.listener.status, 26, GRAY, (WIDTH // 2, 330))
            else:
                draw_text(s, "Seu endereço (rede local ou VPN):", 32, LIGHT, (WIDTH // 2, 200))
                r = draw_text(s, f"{self.my_ip}:{NET_PORT}", 80, WHITE, (WIDTH // 2, 270))
                self.code_rect = r.inflate(60, 30)
                pygame.draw.rect(s, YELLOW if self.copied_t > 0 else (80, 100, 140), self.code_rect, 3, border_radius=18)
                draw_text(s, "COPIADO!" if (self.copied_t > 0 and self.copy_ok) else "Toque no endereço para copiar",
                          26, (90, 220, 120) if self.copied_t > 0 else GRAY, (WIDTH // 2, 345))
                lines = ["Servidor online não configurado: só funciona no mesmo Wi-Fi ou com VPN",
                         "(Radmin, ZeroTier, Tailscale) / porta TCP liberada no roteador.",
                         "Para jogar em qualquer internet com código de sala, configure o relay (README).",
                         "Se o Windows perguntar sobre o Firewall, clique em Permitir."]
                for i, t in enumerate(lines):
                    draw_text(s, t, 24, GRAY, (WIDTH // 2, 410 + i * 32))
        else:
            draw_text(s, "ENTRANDO NA SALA" + dots, 60, YELLOW, (WIDTH // 2, 230))
            draw_text(s, self.menu.addr, 70, WHITE, (WIDTH // 2, 320))
            status = self.connector.status if not self.connector.done else "Aguardando o host iniciar a partida."
            draw_text(s, status, 26, GRAY, (WIDTH // 2, 400))
        self.btn_cancel.draw(s)

    def draw(self):
        if MOBILE:
            playing = self.state == "game" and not self.paused
            if not playing:                          # em jogo os painéis/campo cobrem tudo: não precisa limpar
                self.screen.fill(self.menu.pad_color if self.state == "menu" else BG)
            self.draw_view(self.view)
            if playing:
                self.touch.draw(self.screen, self.match, 1 if self.role == "client" else 0)
            if self.manual_scale:
                sc, ox, oy = self.letterbox()
                size = (max(1, int(LW * sc)), max(1, int(LH * sc)))
                if self._scaled is None or self._scaled.get_size() != size:
                    self._scaled = pygame.Surface(size)          # reaproveitado a cada quadro
                    self.window.fill((0, 0, 0))
                pygame.transform.scale(self.screen, size, self._scaled)
                self.window.blit(self._scaled, (int(ox), int(oy)))
        else:
            self.draw_view(self.screen)

    def draw_view(self, s):
        if self.state == "menu":
            self.menu.draw(s)
            if self.msg and self.msg_t > 0:
                draw_text(s, self.msg, 28, (255, 120, 120), (WIDTH // 2, 640))
            return
        if self.state == "lobby":
            self.draw_lobby(s)
            return
        self.match.draw(s)
        if self.state == "game" and self.paused:
            dim(s)
            draw_text(s, "PAUSADO" if self.role == "local" else "MENU", 100, YELLOW, (WIDTH // 2, 210))
            if self.role != "local":
                draw_text(s, "(o jogo online continua rodando)", 28, GRAY, (WIDTH // 2, 262))
            self.btn_continue.draw(s)
            self.btn_pause_menu.text = "VOLTAR AO MENU" if self.role == "local" else "SAIR DA PARTIDA"
            self.btn_pause_menu.draw(s)
        elif self.state == "over":
            dim(s, 200)
            mt = self.match
            draw_text(s, "FIM DE JOGO", 110, YELLOW, (WIDTH // 2, 150))
            draw_text(s, f"Vencedor: {mt.winner_name}", 70, WHITE, (WIDTH // 2, 270))
            draw_text(s, f"Placar de rodadas:  {mt.names[0]} {mt.round_wins[0]}  x  {mt.round_wins[1]} {mt.names[1]}",
                      40, LIGHT, (WIDTH // 2, 350))
            info = f"({mt.rounds_total} rodadas  |  {mt.points_to_win} pontos por rodada"
            if self.role == "local" and mt.mode == "ia":
                info += f"  |  IA {AI_LEVELS[mt.ai_level]['name']}"
            draw_text(s, info + ")", 28, GRAY, (WIDTH // 2, 400))
            if self.role == "client":
                draw_text(s, "Aguardando o host para jogar de novo...", 30, LIGHT, (WIDTH // 2, 500))
            else:
                self.btn_replay.draw(s)
            self.btn_menu.draw(s)

    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.leave()
                    pygame.quit()
                    sys.exit()
                if MOBILE:
                    e = self.mobile_event(e)
                    if e is None:
                        continue
                self.handle(e)
            self.update(dt)
            self.draw()
            pygame.display.flip()


def main():
    App().run()


if __name__ == "__main__":
    main()
