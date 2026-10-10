"""Partida de pebolim: regras, física, entrada dos jogadores e renderização."""
import math
import random
import pygame

from settings import *
from entities import Ball, Rod, IDLE, CHARGING, SWING, RETURN, level_from_charge
from ai import AIController
from ui import draw_text

SHADOW = (22, 84, 44)
HEAD = HEAD_COLOR                 # cor da cabeça (definida em settings.py)
HEAD_DARK = (205, 130, 40)


def make_keys(mode):
    p1 = dict(up={pygame.K_w}, down={pygame.K_s}, left={pygame.K_a}, right={pygame.K_d},
              kick={pygame.K_SPACE}, control={pygame.K_c},
              direct={pygame.K_1: "G", pygame.K_2: "D", pygame.K_3: "M", pygame.K_4: "A"})
    p2 = dict(up={pygame.K_UP}, down={pygame.K_DOWN}, left={pygame.K_LEFT}, right={pygame.K_RIGHT},
              kick={pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_RCTRL},
              control={pygame.K_RSHIFT}, direct={})
    if mode == "ia":      # contra a IA, o jogador também pode usar as setas + ENTER
        for k in ("up", "down", "left", "right", "kick"):
            p1[k] = p1[k] | p2[k]
        p1["control"] = p1["control"] | {pygame.K_LSHIFT, pygame.K_RSHIFT}
        return [p1, None]
    return [p1, p2]


class Match:
    def __init__(self, mode, rounds, points, ai_level=AI_DEFAULT_LEVEL, sound=None):
        self.mode = mode
        self.ai_level = ai_level                      # "ia" ou "pvp"
        self.sound = sound
        self.rounds_total = rounds
        self.points_to_win = points
        self.names = ("Player 1", "IA" if mode == "ia" else "Player 2")
        self.human = [True, mode == "pvp"]
        self.keys = make_keys(mode)

        self.rods = [Rod(team, kind, self._rod_x(i, team, kind))
                     for i, (team, kind) in enumerate(ROD_LAYOUT)]
        # hastes de cada time ordenadas da esquerda p/ direita
        self.team_rods = [[r for r in self.rods if r.team == t] for t in (0, 1)]
        self.by_kind = [{r.kind: r for r in self.team_rods[t]} for t in (0, 1)]
        self.sel_idx = [2, 1]                 # começa no meio-campo
        self.charging = [None, None]
        self.ball = Ball()
        self.ais = [AIController(self.team_rods[t], ai_level, self) for t in (0, 1) if not self.human[t]]
        self.ctrl = [None, None]               # bola dominada: {rod, i, aim, t, rel}
        self.ctrl_cd = [0.0, 0.0]
        self.local = [True, True]              # times controlados por este computador (online: só um)
        self.axis = [None, None]               # entrada vertical vinda da rede (-1, 0, 1)
        self.hints = True                      # dicas de teclado no rodapé (desligadas no celular)
        self.view_team = None                  # online: de qual time é a visão (esconde mira/dicas do outro)
        self.events = []                       # sons para enviar ao cliente online
        self.key_names = (["C", "SHIFT"], ["W/S", "SETAS"], ["ESPAÇO", "ENTER"]) if mode == "pvp" else \
                         (["C", ""], ["W/S ou SETAS", ""], ["ESPAÇO", ""])

        self.scores = [0, 0]
        self.round_wins = [0, 0]
        self.round_no = 1
        self.tiebreak = False
        self.finished = False
        self.last_scorer = 0
        self.round_winner = 0
        self.phase = "serve"                  # serve | play | goal | round_end
        self.timer = 0.0
        self._touch_cd = self._wall_cd = 0.0
        self._last_count = None

        self._sprites = {}
        self._hud_key = self._hud_surf = None
        self._round_ov = None
        self.table = self._build_table()
        self.zones = [self._build_zones(t) for t in (0, 1)]
        self.zone_surfs = []
        for t in (0, 1):
            lst = []
            for x0, x1, _rod in self.zones[t]:
                z = pygame.Surface((int(x1 - x0), FIELD_H), pygame.SRCALPHA)
                z.fill((*TEAM_COLORS[t], 38))
                z = z.convert_alpha() if pygame.display.get_surface() else z
                lst.append(z)
            self.zone_surfs.append(lst)
        self.bands = []
        for t in (0, 1):
            s = pygame.Surface((32, FIELD_H), pygame.SRCALPHA)
            s.fill((*TEAM_COLORS[t], 55))
            s = s.convert_alpha() if pygame.display.get_surface() else s
            self.bands.append(s)
        self.reset_table(server=0, countdown=3.45)

    # ------------------------------------------------------------------ util
    @property
    def winner_name(self):
        return self.names[0 if self.round_wins[0] > self.round_wins[1] else 1]

    def sfx(self, name):
        if len(self.events) < 20:
            self.events.append(name)
        if self.sound:
            self.sound.play(name)

    def seen(self, t):
        """Mostra dicas/mira do time t? (online: só do próprio jogador)"""
        return self.human[t] and (self.view_team is None or self.view_team == t)

    def merge_keys(self, t):
        """Faz o time t aceitar também o outro conjunto de teclas (setas + ENTER + SHIFT)."""
        a, b = make_keys("pvp")
        for k in ("up", "down", "left", "right", "kick", "control"):
            self.keys[t][k] = a[k] | b[k]
        self.keys[t]["direct"] = a["direct"]

    def selected(self, t):
        return self.team_rods[t][self.sel_idx[t]]

    # ------------------------------------------------------------- fluxo
    def reset_table(self, server, countdown=2.45):
        """Reposiciona hastes e coloca a bola na haste do MEIO-CAMPO de quem saca."""
        for r in self.rods:
            r.reset()
        self.charging = [None, None]
        self.ctrl = [None, None]
        self.ctrl_cd = [0.0, 0.0]
        self.in_zone = [None, None]
        self.server = server
        srod = self.by_kind[server]["M"]
        self.ball.place(srod.x + srod.dir * (FIG_W / 2 + BALL_R + 5), CY)
        self.phase = "serve"
        self.timer = countdown
        self._last_count = None

    def on_goal(self, team):
        self.scores[team] += 1
        self.last_scorer = team
        self.phase = "goal"
        self.timer = 1.8
        self.sfx("goal")

    def after_goal(self):
        if max(self.scores) >= self.points_to_win:
            w = 0 if self.scores[0] > self.scores[1] else 1
            self.round_wins[w] += 1
            self.round_winner = w
            self.phase = "round_end"
            self.timer = 2.8
        else:
            self.reset_table(server=1 - self.last_scorer)   # quem levou o gol saca

    def match_decided(self):
        w0, w1 = self.round_wins
        remaining = self.rounds_total - self.round_no
        if remaining <= 0:
            return w0 != w1
        return EARLY_CLINCH and abs(w0 - w1) > remaining

    def after_round_end(self):
        if self.match_decided():
            self.finished = True
            return
        if self.round_no >= self.rounds_total:      # empate no fim: rodada de desempate
            self.rounds_total += 1
            self.tiebreak = True
        self.round_no += 1
        self.scores = [0, 0]
        self.reset_table(server=(self.round_no - 1) % 2, countdown=3.45)

    # ----------------------------------------------------------- entrada
    def handle_event(self, e):
        """Teclado local -> ações."""
        if e.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return
        for t in (0, 1):
            ks = self.keys[t]
            if ks is None or not self.human[t] or not self.local[t]:
                continue
            act = None
            if e.key in ks["kick"]:
                act = "kick_down" if e.type == pygame.KEYDOWN else "kick_up"
            elif e.type == pygame.KEYDOWN:
                if e.key in ks["left"]:
                    act = "left"
                elif e.key in ks["right"]:
                    act = "right"
                elif e.key in ks["control"]:
                    act = "control"
                elif e.key in ks["direct"]:
                    act = "sel:" + ks["direct"][e.key]
            if act:
                self.do_action(t, act)

    def do_action(self, t, act):
        """Ações dos jogadores (teclado local ou rede): left/right/sel:X/control/kick_down/kick_up."""
        holding = self.ctrl[t] is not None          # segurando a bola: não troca de haste
        if act == "left" and not holding:
            self.sel_idx[t] = max(0, self.sel_idx[t] - 1)
        elif act == "right" and not holding:
            self.sel_idx[t] = min(3, self.sel_idx[t] + 1)
        elif act.startswith("sel:") and not holding:
            kind = act[4:]
            if kind in ("G", "D", "M", "A"):
                self.sel_idx[t] = next(i for i, r in enumerate(self.team_rods[t]) if r.kind == kind)
        elif act == "control" and self.phase == "play":
            if holding:
                if self.charging[t] is None:
                    self.drop_control(t)
            else:
                self.try_control(t)
        elif act == "kick_down" and self.phase == "play" and not self.frozen(t):
            rod = self.ctrl[t]["rod"] if holding else self.selected(t)
            if self.charging[t] is None and rod.start_charge():
                self.charging[t] = rod
        elif act == "kick_up" and self.charging[t] is not None:
            self.charging[t].release()
            self.charging[t] = None

    def set_axis(self, t, m):
        self.axis[t] = max(-1, min(1, int(m)))

    # ------------------------------------------------------------ rede
    def snapshot(self):
        """Estado compacto para enviar ao cliente online."""
        b = self.ball
        ctrl = []
        for c in self.ctrl:
            ctrl.append(None if c is None else [self.rods.index(c["rod"]), c["i"], round(c["aim"], 3),
                                                round(c["t"], 2), round(c["rel"], 1)])
        snap = {"t": "snap", "ph": self.phase, "tm": round(self.timer, 2), "sc": self.scores,
                "rw": self.round_wins, "rn": self.round_no, "rt": self.rounds_total, "tb": self.tiebreak,
                "sv": self.server, "ls": self.last_scorer, "rwn": self.round_winner, "fin": self.finished,
                "b": [round(b.x, 1), round(b.y, 1), round(b.vx), round(b.vy)],
                "r": [[round(r.offset, 1), round(r.foot, 1), r.state, round(r.charge, 2), round(r.cool, 2)]
                      for r in self.rods],
                "sel": self.sel_idx, "iz": self.in_zone, "cd": [round(x, 2) for x in self.ctrl_cd],
                "ctrl": ctrl,
                "chg": [None if r is None else self.rods.index(r) for r in self.charging],
                "ev": self.events}
        self.events = []
        return snap

    def apply_snapshot(self, s):
        """Cliente: copia o estado do host para desenhar."""
        self.phase, self.timer, self.scores = s["ph"], s["tm"], list(s["sc"])
        self.round_wins, self.round_no, self.rounds_total = list(s["rw"]), s["rn"], s["rt"]
        self.tiebreak, self.server, self.last_scorer = s["tb"], s["sv"], s["ls"]
        self.round_winner, self.finished = s["rwn"], s["fin"]
        b = self.ball
        b.x, b.y, b.vx, b.vy = s["b"]
        for r, (off, foot, st, ch, cool) in zip(self.rods, s["r"]):
            r.offset, r.foot, r.state, r.charge, r.cool = off, foot, st, ch, cool
        self.sel_idx, self.in_zone, self.ctrl_cd = list(s["sel"]), list(s["iz"]), list(s["cd"])
        self.ctrl = [None if c is None else {"rod": self.rods[c[0]], "i": c[1], "aim": c[2], "t": c[3], "rel": c[4]}
                     for c in s["ctrl"]]
        self.charging = [None if i is None else self.rods[i] for i in s["chg"]]
        for name in s.get("ev", []):
            if self.sound:
                self.sound.play(name)

    # --------------------------------------------------- controle de bola
    def frozen(self, t):
        """O time t fica parado enquanto o adversário está com a bola dominada."""
        return self.ctrl[1 - t] is not None

    def try_control(self, t, rod=None):
        """Domina a bola se ela estiver devagar (até velocidade média) na área do boneco."""
        if self.phase != "play" or any(self.ctrl) or self.ctrl_cd[t] > 0:
            return False
        rod = rod or self.selected(t)
        b = self.ball
        if rod.state != IDLE or rod.cool > 0 or self.charging[t] is not None:
            return False
        if b.speed > CONTROL_MAX_SPEED:
            return False
        i = rod.control_index(b)
        if i is None:
            return False
        half = rod.fig_h / 2
        rel = max(-half, min(half, b.y - (rod.base_y(i) + rod.offset)))
        self.ctrl[t] = {"rod": rod, "i": i, "aim": 0.0, "t": 0.0, "rel": rel}
        b.glue = None
        b.vx = b.vy = 0.0
        rod.move = 0.0
        self.sfx("touch")
        return True

    def drop_control(self, t):
        """Solta a bola sem chutar (empurrãozinho para frente)."""
        c = self.ctrl[t]
        if c is None:
            return
        self.ball.vx, self.ball.vy = c["rod"].dir * 90.0, 0.0
        self.ctrl[t] = None
        self.ctrl_cd[t] = CONTROL_COOLDOWN

    def held_pos(self):
        for c in self.ctrl:
            if c:
                rod = c["rod"]
                return (rod.x + rod.dir * (FIG_W / 2 + BALL_R + 3),
                        rod.base_y(c["i"]) + rod.offset + c["rel"])
        return None

    def update_control(self, dt):
        for t in (0, 1):
            self.ctrl_cd[t] = max(0.0, self.ctrl_cd[t] - dt)
            c = self.ctrl[t]
            if c is None:
                continue
            rod = c["rod"]
            rod.move = 0.0
            c["t"] += dt
            if rod.state == SWING:                  # o chute saiu: solta a bola na direção da mira
                rod.aim = c["aim"]
                self.ctrl[t] = None
                self.ctrl_cd[t] = CONTROL_COOLDOWN
            elif c["t"] > CONTROL_MAX_TIME and rod.state != CHARGING:
                self.drop_control(t)

    @staticmethod
    def _rod_x(i, team, kind):
        """Posição X da haste. Os goleiros ficam colados na linha de fundo."""
        if kind == "G":
            return FIELD_X + GOALIE_INSET if team == 0 else FIELD_X + FIELD_W - GOALIE_INSET
        return FIELD_X + FIELD_W * (i + 0.5) / 8

    def _build_zones(self, t):
        """Área de cada haste do time t, na ordem goleiro, defesa, meio-campo, ataque.
        Os limites vêm de ZONE_BOUNDS; o time da direita usa o espelho."""
        zones = []
        for k, kind in enumerate(("G", "D", "M", "A")):
            a, b = ZONE_BOUNDS[k], ZONE_BOUNDS[k + 1]
            if t == 1:
                a, b = 1 - b, 1 - a
            zones.append((FIELD_X + FIELD_W * a, FIELD_X + FIELD_W * b, self.by_kind[t][kind]))
        return zones

    def auto_zone(self):
        """Bola entrou na área de uma haste: o controle passa sozinho para ela.
        Nos espaços entre áreas a seleção não muda; dá para trocar manualmente."""
        if not AUTO_ZONES:
            return
        bx = self.ball.x
        for t in (0, 1):
            if not self.human[t]:
                continue
            cur = None
            for k, (x0, x1, _rod) in enumerate(self.zones[t]):
                if x0 <= bx < x1:
                    cur = k
                    break
            if cur is not None and cur != self.in_zone[t]:
                self.sel_idx[t] = self.team_rods[t].index(self.zones[t][cur][2])
            self.in_zone[t] = cur

    def apply_input(self, keys, dt):
        for t in (0, 1):
            if not self.human[t]:
                continue
            ks = self.keys[t]
            m = 0
            if not self.local[t]:
                m = self.axis[t] or 0
            else:
                if any(keys[k] for k in ks["up"]):
                    m -= 1
                if any(keys[k] for k in ks["down"]):
                    m += 1
            for r in self.team_rods[t]:
                r.move = 0
            if self.frozen(t):                      # adversário com a bola: fica parado
                continue
            c = self.ctrl[t]
            if c:                                   # segurando a bola: cima/baixo ajustam a mira
                lim = math.radians(CONTROL_AIM_MAX)
                c["aim"] = max(-lim, min(lim, c["aim"] + m * math.radians(CONTROL_AIM_SPEED) * dt))
            else:
                self.selected(t).move = m

    # ------------------------------------------------------------ física
    def collide_walls(self):
        b, r = self.ball, self.ball.r
        L, R = FIELD_X, FIELD_X + FIELD_W
        T, B = FIELD_Y, FIELD_Y + FIELD_H
        impact = 0.0
        if b.y - r < T:
            b.y = T + r
            impact = max(impact, abs(b.vy))
            b.vy = abs(b.vy) * WALL_BOUNCE
        elif b.y + r > B:
            b.y = B - r
            impact = max(impact, abs(b.vy))
            b.vy = -abs(b.vy) * WALL_BOUNCE
        for x_wall, sign in ((L, 1), (R, -1)):
            d = (b.x - x_wall) * sign             # > 0: dentro do campo
            gy1, gy2 = CY - GOAL_H / 2 + r, CY + GOAL_H / 2 - r
            if d - r < 0:
                in_mouth = gy1 <= b.y <= gy2
                if not in_mouth:
                    if d > 0:                     # bateu na trave / parede
                        b.x = x_wall + sign * r
                        impact = max(impact, abs(b.vx))
                        b.vx = sign * abs(b.vx) * WALL_BOUNCE
                    else:                         # já dentro da rede: paredes laterais do gol
                        b.y = max(gy1, min(gy2, b.y))
                        b.vy *= -0.4
            if d < -GOAL_DEPTH + r:               # fundo da rede
                b.x = x_wall - sign * GOAL_DEPTH + sign * r
                b.vx = sign * abs(b.vx) * 0.3
        return impact

    def _glue_step(self, sub):
        """Bola grudada: acompanha o boneco; se a haste mexer demais, ela escapa. True = continua grudada."""
        b = self.ball
        g = b.glue
        rod = g["rod"]
        if rod.state not in (IDLE, CHARGING):          # o boneco vai chutar: solta e a colisão do chute age
            b.unglue(0.0, 0.0, 0.0)
            return False
        g["t"] += sub
        if g["t"] > GLUE_MAX_TIME:                     # ficou tempo demais: empurrãozinho para frente
            b.unglue(rod.dir * 160.0, 0.0)
            return False
        speed = abs(rod.vy)
        if speed > GLUE_FREE_SPEED:
            g["slip"] += (speed - GLUE_FREE_SPEED) / (ROD_SPEED - GLUE_FREE_SPEED) * sub / GLUE_SLIP_TIME
        else:
            g["slip"] = max(0.0, g["slip"] - 1.5 * sub / GLUE_SLIP_TIME)
        if g["slip"] >= 1.0:                           # mexeu demais: a bola escapa (fica para trás)
            b.unglue(rod.dir * 70.0, rod.vy * 0.4)
            return False
        b.x, b.y = rod.glue_pos(g)
        b.vx, b.vy = 0.0, rod.vy
        return True

    def physics(self, dt, allow_goal):
        b = self.ball
        b.glue_cd = max(0.0, b.glue_cd - dt)
        steps = max(SUBSTEPS_MIN, min(SUBSTEPS, 1 + int(b.speed * dt / SUBSTEP_PX)))   # bola devagar = menos contas
        sub = dt / steps
        held = any(self.ctrl)
        fcx = FIELD_X + FIELD_W / 2
        x0, y0 = b.x, b.y
        for _ in range(steps):
            for r in self.rods:
                r.update(sub)
            if held:                                  # bola dominada: fica presa no pé do boneco
                b.x, b.y = self.held_pos()
                b.vx = b.vy = 0.0
                continue
            if b.glue is not None and self._glue_step(sub):
                grod = b.glue["rod"]
                px, py = b.x, b.y
                for r in self.rods:                   # um adversário encostou na bola grudada: rouba
                    if r is not grod and abs(b.x - r.x) < 60 and r.collide(b):
                        b.unglue(b.vx, b.vy)
                        self.sfx("touch")
                        break
                if b.glue is not None:
                    self.collide_walls()
                    if abs(b.x - px) > 0.5 or abs(b.y - py) > 0.5:      # parede empurrou: solta
                        b.unglue(b.vx, b.vy)
                continue
            if FIELD_X <= b.x <= FIELD_X + FIELD_W:   # campo curvado: puxa a bola para o centro
                b.vx -= CURVE_KX * (b.x - fcx) * sub
                b.vy -= CURVE_KY * (b.y - CY) * sub
            b.x += b.vx * sub
            b.y += b.vy * sub
            for r in self.rods:
                if abs(b.x - r.x) < 60:
                    h = r.collide(b)
                    if h == 2:
                        self.sfx("kick")
                    elif h == 1 and self._touch_cd <= 0:
                        self.sfx("touch")
                        self._touch_cd = 0.06
                    if b.glue is not None:            # acabou de grudar: não testa as outras hastes
                        break
            imp = self.collide_walls()
            if imp > 140 and self._wall_cd <= 0:
                self.sfx("wall")
                self._wall_cd = 0.08
            if allow_goal:
                if b.x < FIELD_X - b.r:
                    self.on_goal(1)
                    allow_goal = False
                elif b.x > FIELD_X + FIELD_W + b.r:
                    self.on_goal(0)
                    allow_goal = False
        if held:
            b.idle = 0.0
            return
        if b.glue is None:
            f = math.exp(-BALL_FRICTION * dt)
            b.vx *= f
            b.vy *= f
            sp = b.speed
            if sp > BALL_MAX:
                b.vx, b.vy = b.vx / sp * BALL_MAX, b.vy / sp * BALL_MAX
        if self.phase == "play":                  # bola parada por 5 s: ela se mexe sozinha
            moved = math.hypot(b.x - x0, b.y - y0) / dt if dt > 0 else 0.0
            b.idle = b.idle + dt if moved < IDLE_SPEED else 0.0
            if b.idle >= IDLE_NUDGE_TIME:
                self.nudge_ball()
        else:
            b.idle = 0.0

    def nudge_ball(self):
        """Empurrãozinho numa bola que ficou parada tempo demais."""
        b = self.ball
        b.idle = 0.0
        b.glue = None
        b.glue_cd = 0.8
        cx = FIELD_X + FIELD_W / 2
        if math.hypot(cx - b.x, CY - b.y) > 70:
            ang = math.atan2(CY - b.y, cx - b.x) + random.uniform(-0.6, 0.6)
        else:
            ang = random.uniform(0, 2 * math.pi)
        b.vx, b.vy = math.cos(ang) * IDLE_NUDGE_SPEED, math.sin(ang) * IDLE_NUDGE_SPEED
        self.sfx("touch")

    def update(self, dt, keys):
        self._touch_cd = max(0.0, self._touch_cd - dt)
        self._wall_cd = max(0.0, self._wall_cd - dt)
        if self.phase == "serve":
            self.timer -= dt
            n = math.ceil(self.timer - 0.45)
            if n != self._last_count:
                self._last_count = n
                self.sfx("beep" if n > 0 else "go")
            if self.timer <= 0:
                self.phase = "play"
            return
        if self.phase == "play":
            self.auto_zone()
        self.apply_input(keys, dt)
        if self.phase == "play":
            for ai in self.ais:
                ai.update(dt, self.ball)
        for t in (0, 1):                            # time parado enquanto o adversário controla a bola
            if self.frozen(t):
                for r in self.team_rods[t]:
                    r.move = 0.0
        self.update_control(dt)
        self.physics(dt, self.phase == "play")
        if self.phase in ("goal", "round_end"):
            self.timer -= dt
            if self.timer <= 0:
                if self.phase == "goal":
                    self.after_goal()
                else:
                    self.after_round_end()

    # --------------------------------------------------------- desenho
    def _build_table(self):
        s = pygame.Surface((WIDTH, HEIGHT))
        s.fill(BG)
        frame = pygame.Rect(FIELD_X - GOAL_DEPTH - 8, FIELD_Y - 22,
                            FIELD_W + 2 * (GOAL_DEPTH + 8), FIELD_H + 44)
        pygame.draw.rect(s, WOOD_DARK, frame.inflate(10, 10), border_radius=24)
        pygame.draw.rect(s, WOOD, frame, border_radius=20)
        field = pygame.Rect(FIELD_X, FIELD_Y, FIELD_W, FIELD_H)
        pygame.draw.rect(s, GRASS, field)
        stripe = FIELD_W // 16
        for i in range(0, 16, 2):
            pygame.draw.rect(s, GRASS2, (FIELD_X + i * stripe, FIELD_Y, stripe, FIELD_H))
        # campo em "cuia": bordas mais escuras, centro mais claro
        vig = pygame.Surface((FIELD_W, FIELD_H), pygame.SRCALPHA)
        steps, stp = 14, 6
        for k in range(steps):
            a = int(80 * (1 - k / steps) ** 2)
            pygame.draw.rect(vig, (0, 20, 10, a), vig.get_rect().inflate(-2 * k * stp, -2 * k * stp), stp + 1)
        s.blit(vig, (FIELD_X, FIELD_Y))
        # gols (rede)
        gy1 = int(CY - GOAL_H / 2)
        for gx in (FIELD_X - GOAL_DEPTH, FIELD_X + FIELD_W):
            g = pygame.Rect(gx, gy1, GOAL_DEPTH, GOAL_H)
            pygame.draw.rect(s, (24, 26, 32), g)
            for k in range(0, GOAL_DEPTH + 1, 8):
                pygame.draw.line(s, (90, 96, 110), (g.x + k, g.y), (g.x + k, g.bottom), 1)
            for k in range(0, GOAL_H + 1, 8):
                pygame.draw.line(s, (90, 96, 110), (g.x, g.y + k), (g.right, g.y + k), 1)
        # marcações
        w = 3
        pygame.draw.rect(s, WHITE, field, w)
        mx = FIELD_X + FIELD_W // 2
        pygame.draw.line(s, WHITE, (mx, FIELD_Y), (mx, FIELD_Y + FIELD_H), w)
        pygame.draw.circle(s, WHITE, (mx, int(CY)), 62, w)
        pygame.draw.circle(s, WHITE, (mx, int(CY)), 5)
        box_h = GOAL_H + 50
        pygame.draw.rect(s, WHITE, (FIELD_X, int(CY - box_h / 2), 70, box_h), w)
        pygame.draw.rect(s, WHITE, (FIELD_X + FIELD_W - 70, int(CY - box_h / 2), 70, box_h), w)
        for px in (FIELD_X, FIELD_X + FIELD_W):
            for py in (gy1, gy1 + GOAL_H):
                pygame.draw.circle(s, WHITE, (px, py), 6)
        for r in self.rods:                      # hastes e pinos: fixos, já ficam desenhados na mesa
            pygame.draw.line(s, (90, 94, 104), (r.x, FIELD_Y - 18), (r.x, FIELD_Y + FIELD_H + 18), 8)
            pygame.draw.line(s, STEEL, (r.x, FIELD_Y - 18), (r.x, FIELD_Y + FIELD_H + 18), 5)
            ky = FIELD_Y + FIELD_H + 12 if r.team == 0 else FIELD_Y - 12
            pygame.draw.circle(s, TEAM_COLORS[r.team], (int(r.x), ky), 9)
            pygame.draw.circle(s, TEAM_DARK[r.team], (int(r.x), ky), 9, 2)
        try:
            s = s.convert()                      # mesmo formato da tela = blit rápido
        except Exception:
            pass
        return s

    def draw_rod_line(self, surf, r):
        """A haste em si já está na mesa; aqui só o anel da haste selecionada."""
        if self.seen(r.team) and r is self.selected(r.team):
            ky = FIELD_Y + FIELD_H + 12 if r.team == 0 else FIELD_Y - 12
            pygame.draw.circle(surf, WHITE, (int(r.x), ky), 13, 3)

    @staticmethod
    def _rect(cx, cy, w, h):
        rc = pygame.Rect(0, 0, max(1, int(round(w))), max(1, int(round(h))))
        rc.center = (int(round(cx)), int(round(cy)))
        return rc

    def _capsule(self, team, w, h):
        """Boneco parado (sombra + corpo + cabeça) desenhado uma vez e guardado."""
        key = (team, w, h)
        spr = self._sprites.get(key)
        if spr is None:
            col, dark = TEAM_COLORS[team], TEAM_DARK[team]
            spr = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
            body = pygame.Rect(2, 2, w, h)
            rad = int(w // 2)
            pygame.draw.rect(spr, SHADOW, body.move(3, 4), border_radius=rad)
            pygame.draw.rect(spr, col, body, border_radius=rad)
            pygame.draw.rect(spr, dark, body, 2, border_radius=rad)
            head = self._rect(body.centerx, body.centery, 15, 14)
            pygame.draw.ellipse(spr, HEAD, head)
            pygame.draw.ellipse(spr, HEAD_DARK, head, 2)
            try:
                spr = spr.convert_alpha()
            except Exception:
                pass
            self._sprites[key] = spr
        return spr

    def draw_figures(self, surf, r):
        """Parado: cápsula com a cabeça no centro.  Chutando: formato em T (ombros + pé)."""
        col, dark = TEAM_COLORS[r.team], TEAM_DARK[r.team]
        for i in range(r.n):
            parts = r.parts(i)
            y = r.base_y(i) + r.offset
            if len(parts) == 1:
                cx, cy, w, h = parts[0]
                body = self._rect(cx, cy, w, h)
                surf.blit(self._capsule(r.team, body.w, body.h), (body.x - 2, body.y - 2))
                continue
            else:
                (scx, scy, sw, sh), (fcx, fcy, fw, fh) = parts
                sb, fb = self._rect(scx, scy, sw, sh), self._rect(fcx, fcy, fw, fh)
                if fcx > r.x:      # pé para a direita
                    kw = dict(border_top_right_radius=8, border_bottom_right_radius=8)
                else:              # pé para a esquerda
                    kw = dict(border_top_left_radius=8, border_bottom_left_radius=8)
                pygame.draw.rect(surf, SHADOW, sb.move(3, 4))
                pygame.draw.rect(surf, SHADOW, fb.move(3, 4), **kw)
                pygame.draw.rect(surf, col, sb)
                pygame.draw.rect(surf, col, fb, **kw)
                pygame.draw.rect(surf, dark, sb, 2)
                pygame.draw.rect(surf, dark, fb, 2, **kw)
                pygame.draw.rect(surf, col, self._rect(scx, scy, max(1, sw - 4), sh - 4))   # emenda ombro/pé
                head_c = (r.x, y)
            head = self._rect(head_c[0], head_c[1], 15, 14)
            pygame.draw.ellipse(surf, HEAD, head)
            pygame.draw.ellipse(surf, HEAD_DARK, head, 2)

    def draw_ball(self, surf):
        b = self.ball
        x, y = int(b.x), int(b.y)
        spr = self._sprites.get("ball")
        if spr is None:
            R = b.r
            spr = pygame.Surface((2 * R + 6, 2 * R + 6), pygame.SRCALPHA)
            c = (R + 1, R + 1)
            pygame.draw.circle(spr, SHADOW, (c[0] + 3, c[1] + 4), R)
            pygame.draw.circle(spr, WHITE, c, R)
            pygame.draw.circle(spr, (30, 30, 30), c, R, 2)
            try:
                spr = spr.convert_alpha()
            except Exception:
                pass
            self._sprites["ball"] = spr
        surf.blit(spr, (x - b.r - 1, y - b.r - 1))
        ang = (b.x + b.y) / 6.0
        pygame.draw.circle(surf, (40, 40, 40), (int(x + math.cos(ang) * 5), int(y + math.sin(ang) * 5)), 3)

    def draw_control(self, surf):
        """Área de controle (quando dá para dominar a bola) e mira (quando está dominada)."""
        if self.phase != "play":
            return
        b = self.ball
        held = next((c for c in self.ctrl if c), None)
        if held:
            rod = held["rod"]
            t = rod.team
            ang = held["aim"]
            if self.seen(t):                         # a mira da IA fica escondida do jogador
                dx, dy = rod.dir * math.cos(ang), math.sin(ang)
                mx = math.radians(CONTROL_AIM_MAX)
                for a in (-mx, 0.0, mx):              # leque de direções possíveis
                    fx, fy = rod.dir * math.cos(a), math.sin(a)
                    pygame.draw.line(surf, (255, 255, 255), (b.x, b.y), (b.x + fx * 60, b.y + fy * 60), 1)
                end = (b.x + dx * 100, b.y + dy * 100)
                pygame.draw.line(surf, WHITE, (b.x, b.y), end, 4)
                px, py = -dy, dx
                tip = [end, (end[0] - dx * 15 + px * 8, end[1] - dy * 15 + py * 8),
                       (end[0] - dx * 15 - px * 8, end[1] - dy * 15 - py * 8)]
                pygame.draw.polygon(surf, WHITE, tip)
            if self.seen(1 - t):
                draw_text(surf, "PARADO! O adversário está com a bola", 28, YELLOW,
                          (WIDTH // 2, FIELD_Y + 24))
            rem = max(0.0, 1 - held["t"] / CONTROL_MAX_TIME)       # tempo restante segurando
            pygame.draw.rect(surf, (0, 0, 0), (b.x - 21, b.y - 24, 42, 6))
            pygame.draw.rect(surf, TEAM_COLORS[t], (b.x - 20, b.y - 23, int(40 * rem), 4))
            if self.seen(t):
                ak, kk, ck = self.key_names[1][t], self.key_names[2][t], self.key_names[0][t]
                draw_text(surf, f"{ak} MIRA   |   {kk} CHUTA (segure p/ força)   |   {ck} SOLTA", 22, WHITE,
                          (WIDTH // 2, FIELD_Y + FIELD_H - 16))
            return
        for t in (0, 1):
            if not self.seen(t) or self.ctrl_cd[t] > 0:
                continue
            rod = self.selected(t)
            if rod.state != IDLE or rod.cool > 0 or b.speed > CONTROL_MAX_SPEED:
                continue
            i = rod.control_index(b)
            if i is None:
                continue
            x, y, w, h = rod.control_rect(i)
            pygame.draw.rect(surf, TEAM_COLORS[t], (int(x), int(y), int(w), int(h)), 2, border_radius=6)
            draw_text(surf, f"[{self.key_names[0][t]}] CONTROLAR", 22, WHITE, (b.x, b.y - 26))

    def bar_rod(self, t):
        if self.seen(t):
            return self.charging[t] or self.selected(t)
        for r in self.team_rods[t]:
            if r.state == CHARGING:
                return r
        return None

    def draw_power_bar(self, surf, rect, t):
        rod = self.bar_rod(t)
        value = rod.charge if rod else 0.0
        active = rod is not None and rod.state == CHARGING
        pygame.draw.rect(surf, (10, 12, 18), rect.inflate(10, 10), border_radius=10)
        bounds = [(0.0, ZONE_WEAK), (ZONE_WEAK, ZONE_STRONG), (ZONE_STRONG, 1.0)]
        for lvl, (a, b) in enumerate(bounds):
            zx = rect.x + int(rect.w * a)
            zw = int(rect.w * b) - int(rect.w * a)
            col = LEVEL_COLORS[lvl]
            pygame.draw.rect(surf, tuple(c // 3 for c in col), (zx, rect.y, zw, rect.h))
            fill = max(0, min(zw, int(rect.w * value) - (zx - rect.x)))
            if fill > 0:
                pygame.draw.rect(surf, col, (zx, rect.y, fill, rect.h))
            draw_text(surf, LEVEL_NAMES[lvl], 20, WHITE, (zx + zw // 2, rect.centery), shadow=True)
        mx = rect.x + int(rect.w * value)
        pygame.draw.rect(surf, WHITE, (mx - 2, rect.y - 6, 4, rect.h + 12), border_radius=2)
        if active:
            lvl = level_from_charge(value)
            draw_text(surf, LEVEL_NAMES[lvl], 24, LEVEL_COLORS[lvl], (rect.right, rect.y - 16), "midright")

    def _hud_top(self):
        """Faixa de cima do placar: só é redesenhada quando placar/rodadas mudam."""
        key = (self.names, self.mode, self.ai_level, tuple(self.round_wins), self.round_no, self.tiebreak,
               self.rounds_total, tuple(self.scores), self.points_to_win)
        if key != self._hud_key:
            s = pygame.Surface((WIDTH, 90))
            pygame.draw.rect(s, (14, 18, 26), (0, 0, WIDTH, 86))
            pygame.draw.line(s, (60, 70, 90), (0, 86), (WIDTH, 86), 2)
            draw_text(s, self.names[0].upper(), 34, TEAM_COLORS[0], (30, 26), "midleft")
            name1 = self.names[1].upper()
            if self.mode == "ia":
                name1 += " - " + AI_LEVELS[self.ai_level]["name"].upper()
            draw_text(s, name1, 34, TEAM_COLORS[1], (WIDTH - 30, 26), "midright")
            draw_text(s, f"Rodadas ganhas: {self.round_wins[0]}", 24, LIGHT, (30, 60), "midleft")
            draw_text(s, f"Rodadas ganhas: {self.round_wins[1]}", 24, LIGHT, (WIDTH - 30, 60), "midright")
            label = "DESEMPATE" if self.tiebreak else f"RODADA {self.round_no} DE {self.rounds_total}"
            draw_text(s, label, 24, YELLOW, (WIDTH // 2, 14))
            draw_text(s, f"{self.scores[0]}  x  {self.scores[1]}", 64, WHITE, (WIDTH // 2, 48))
            draw_text(s, f"Primeiro a {self.points_to_win} pontos vence a rodada", 20, GRAY,
                      (WIDTH // 2, 77), shadow=False)
            try:
                s = s.convert()
            except Exception:
                pass
            self._hud_key, self._hud_surf = key, s
        return self._hud_surf

    def draw_hud(self, surf):
        surf.blit(self._hud_top(), (0, 0))
        # barras de força
        for t, x in ((0, 60), (1, 540)):
            rect = pygame.Rect(x, 636, 400, 24)
            rod = self.bar_rod(t)
            who = self.names[t].upper()
            extra = f"  |  Haste: {rod.name}" if (rod and self.seen(t)) else ""
            draw_text(surf, f"FORÇA DO CHUTE - {who}{extra}", 22, TEAM_COLORS[t], (x, 616), "midleft")
            self.draw_power_bar(surf, rect, t)
        if self.view_team is not None:
            h = "W/S mover | A/D haste | 1-4 | ESPAÇO chuta | C controla"
            h1, h2 = (h, "") if self.view_team == 0 else ("", h)
        elif self.mode == "ia":
            h1 = "W/S ou SETAS mover | A/D haste | ESPAÇO chuta | C controla"
            h2 = "Adversário controlado pela IA"
        else:
            h1 = "W/S mover | A/D haste | ESPAÇO chuta | C controla"
            h2 = "SETAS mover | ESQ/DIR haste | ENTER chuta | SHIFT controla"
        if self.hints:
            draw_text(surf, h1, 18, GRAY, (260, 684), shadow=False)
            draw_text(surf, h2, 18, GRAY, (740, 684), shadow=False)
            draw_text(surf, "ESC pausa", 18, GRAY, (WIDTH // 2, 684), shadow=False)

    def draw_overlays(self, surf):
        cx, cy = WIDTH // 2, FIELD_Y + FIELD_H // 2
        if self.phase == "serve":
            n = math.ceil(self.timer - 0.45)
            draw_text(surf, str(n) if n > 0 else "VAI!", 170, YELLOW, (cx, cy - 20))
            draw_text(surf, f"Saque: {self.names[self.server]}", 36, WHITE, (cx, cy + 90))
        elif self.phase == "goal":
            draw_text(surf, "GOOOL!", 150, TEAM_COLORS[self.last_scorer], (cx, cy - 20))
            draw_text(surf, f"Gol de {self.names[self.last_scorer]}", 40, WHITE, (cx, cy + 80))
        elif self.phase == "round_end":
            if self._round_ov is None:
                self._round_ov = pygame.Surface((WIDTH, 170), pygame.SRCALPHA)
                self._round_ov.fill((0, 0, 0, 180))
            surf.blit(self._round_ov, (0, cy - 85))
            w = self.round_winner
            draw_text(surf, f"{self.names[w]} venceu a rodada {self.round_no}!", 56, TEAM_COLORS[w], (cx, cy - 25))
            draw_text(surf, f"Rodadas: {self.round_wins[0]} x {self.round_wins[1]}", 38, WHITE, (cx, cy + 35))

    def draw(self, surf):
        surf.blit(self.table, (0, 0))
        for t in (0, 1):
            k = self.in_zone[t]
            if self.seen(t) and k is not None:
                surf.blit(self.zone_surfs[t][k], (int(self.zones[t][k][0]), FIELD_Y))
        for t in (0, 1):
            if self.seen(t):
                surf.blit(self.bands[t], (int(self.selected(t).x) - 16, FIELD_Y))
        for r in self.rods:
            self.draw_rod_line(surf, r)
        for r in self.rods:
            self.draw_figures(surf, r)
        self.draw_ball(surf)
        self.draw_control(surf)
        self.draw_hud(surf)
        self.draw_overlays(surf)
