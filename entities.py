"""Entidades do jogo: Bola e Haste (Rod)."""
import math
from settings import *

IDLE, CHARGING, SWING, RETURN = range(4)


def approach(cur, target, step):
    if cur < target:
        return min(cur + step, target)
    return max(cur - step, target)


def level_from_charge(v):
    """Converte o valor da barra (0..1) no nível do chute: 0 fraco, 1 normal, 2 forte."""
    if v < ZONE_WEAK:
        return 0
    if v < ZONE_STRONG:
        return 1
    return 2


class Ball:
    def __init__(self):
        self.r = BALL_R
        self.place(FIELD_X + FIELD_W / 2, CY)

    def place(self, x, y):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.idle = 0.0                 # tempo (s) praticamente parada
        self.glue = None                # {"rod", "i", "rel", "slip", "t"} quando grudada num boneco
        self.glue_cd = 0.0

    def unglue(self, vx=0.0, vy=0.0, cooldown=GLUE_COOLDOWN):
        """Solta a bola do boneco (a bola sai com a velocidade dada)."""
        if self.glue is not None:
            self.glue = None
            self.vx, self.vy = vx, vy
            self.glue_cd = cooldown

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)


class Rod:
    """Haste transversal: todos os bonecos se movem juntos na vertical.

    O chute é uma máquina de estados: IDLE -> CHARGING (segurando) -> SWING (1 batida)
    -> RETURN -> IDLE (+ cooldown). Só dá para iniciar outro chute com um NOVO aperto
    depois que o ciclo termina, o que impede o "roletão" (giro contínuo).
    """

    def __init__(self, team, kind, x):
        cfg = ROD_TYPES[kind]
        self.team, self.kind, self.x = team, kind, x
        self.name = cfg["name"]
        self.windup = (2.0, 5.0) if kind == "G" else (4.0, 16.0)   # recuo do pé ao carregar
        self.dir = 1 if team == 0 else -1          # sentido do ataque no eixo X
        self.n, self.spacing, self.fig_h = cfg["n"], cfg["spacing"], cfg["h"]
        max_off = FIELD_H / 2 - self.fig_h / 2 - 4 - (self.n - 1) / 2 * self.spacing
        if cfg["travel"]:
            max_off = min(max_off, cfg["travel"])
        self.max_off = max_off
        self.reset()

    def reset(self):
        self.offset = 0.0
        self.vy = 0.0
        self.move = 0.0                 # -1 sobe, +1 desce
        self.rest = -self.dir * 2.0
        self.foot = self.rest           # deslocamento do pé no eixo X
        self.foot_vx = 0.0
        self.state = IDLE
        self.t = 0.0
        self.cool = 0.0
        self.charge, self.charge_dir = 0.0, 1
        self.level = 1
        self.kick_applied = False
        self.swing_from = 0.0
        self.aim = None                 # ângulo (rad) do chute com bola controlada

    # ---------- geometria ----------
    def base_y(self, i):
        return CY + (i - (self.n - 1) / 2) * self.spacing

    def figures(self):
        """Centro (cx, cy, w, h) de cada boneco na pose parada (usado pela IA)."""
        return [(self.x + self.foot, self.base_y(i) + self.offset, FIG_W, self.fig_h)
                for i in range(self.n)]

    def ext(self):
        """Quanto o pé está à frente (+) ou atrás (-) do eixo da haste."""
        return self.foot * self.dir

    def is_extended(self):
        return self.state != IDLE and abs(self.ext()) > T_THRESHOLD

    def parts(self, i):
        """Retângulos (cx, cy, w, h) do boneco i.
        Parado: 1 cápsula.  Chutando (pé estendido): ombros + pé (formato T)."""
        y = self.base_y(i) + self.offset
        if not self.is_extended():
            return [(self.x + self.foot, y, FIG_W, self.fig_h)]
        e = self.ext()
        sg = self.dir if e > 0 else -self.dir
        foot_len = abs(e) + FIG_W / 2 - SHOULDER_W          # a frente do pé fica em |e| + FIG_W/2
        shoulders = (self.x + sg * SHOULDER_W / 2, y, SHOULDER_W, self.fig_h * SHOULDER_H)
        foot = (self.x + sg * (SHOULDER_W + foot_len / 2), y, foot_len, self.fig_h * FOOT_H)
        return [shoulders, foot]

    # ---------- controle de bola ----------
    def control_rect(self, i):
        """Área (x, y, w, h) em que o boneco i consegue dominar a bola (só à frente dele)."""
        y = self.base_y(i) + self.offset
        back, front = 10.0, CONTROL_FRONT
        x0 = min(self.x - self.dir * back, self.x + self.dir * front)
        half = self.fig_h / 2 + CONTROL_PAD
        return (x0, y - half, back + front, 2 * half)

    def control_index(self, ball):
        """Índice do boneco que pode dominar a bola, ou None."""
        for i in range(self.n):
            y = self.base_y(i) + self.offset
            ahead = (ball.x - self.x) * self.dir
            if 0 <= ahead <= CONTROL_FRONT and abs(ball.y - y) <= self.fig_h / 2 + CONTROL_PAD:
                return i
        return None

    def rects(self):
        out = []
        for i in range(self.n):
            out.extend(self.parts(i))
        return out

    # ---------- chute ----------
    def start_charge(self):
        if self.state == IDLE and self.cool <= 0:
            self.state = CHARGING
            self.charge, self.charge_dir = 0.0, 1
            return True
        return False

    def release(self):
        if self.state == CHARGING:
            self.level = level_from_charge(self.charge)
            self.state = SWING
            self.t = 0.0
            self.swing_from = self.foot
            self.kick_applied = False
            return True
        return False

    # ---------- atualização ----------
    def update(self, dt):
        # movimento vertical suave
        self.vy = approach(self.vy, self.move * ROD_SPEED, ROD_ACCEL * dt)
        new = self.offset + self.vy * dt
        if new > self.max_off:
            new, self.vy = self.max_off, 0.0
        elif new < -self.max_off:
            new, self.vy = -self.max_off, 0.0
        self.offset = new

        old_foot = self.foot
        if self.state == CHARGING:
            self.charge += self.charge_dir * CHARGE_SPEED * dt
            if self.charge >= 1.0:
                self.charge, self.charge_dir = 1.0, -1
            elif self.charge <= 0.0:
                self.charge, self.charge_dir = 0.0, 1
            self.foot = -self.dir * (self.windup[0] + self.windup[1] * self.charge)       # "puxa o pé para trás"
        elif self.state == SWING:
            self.t += dt
            p = min(self.t / T_SWING, 1.0)
            e = 1 - (1 - p) ** 2
            self.foot = self.swing_from + (self.dir * REACH - self.swing_from) * e
            if self.t >= T_SWING:
                self.state, self.t = RETURN, 0.0
                self.aim = None
        elif self.state == RETURN:
            self.t += dt
            p = min(self.t / T_RETURN, 1.0)
            self.foot = self.dir * REACH + (self.rest - self.dir * REACH) * p
            if self.t >= T_RETURN:
                self.state, self.cool = IDLE, KICK_COOLDOWN
        else:
            self.foot = approach(self.foot, self.rest, 150 * dt)
            self.cool = max(0.0, self.cool - dt)
            if self.cool <= 0:
                self.charge = 0.0
        self.foot_vx = (self.foot - old_foot) / dt if dt > 0 else 0.0

    # ---------- colisão com a bola ----------
    def collide(self, ball):
        """Retorna 0 (nada), 1 (toque) ou 2 (chute).
        Toque devagar na frente do boneco = a bola GRUDA (cola); senão ela quase não quica."""
        result = 0
        for i in range(self.n):
            for fx, fy, w, h in self.parts(i):
                left, right = fx - w / 2, fx + w / 2
                top, bot = fy - h / 2, fy + h / 2
                cx = max(left, min(ball.x, right))
                cy = max(top, min(ball.y, bot))
                dx, dy = ball.x - cx, ball.y - cy
                d2 = dx * dx + dy * dy
                if d2 >= ball.r * ball.r:
                    continue
                if d2 > 1e-9:
                    d = math.sqrt(d2)
                    nx, ny, pen = dx / d, dy / d, ball.r - d
                else:  # centro da bola dentro do retângulo
                    cands = [(ball.x - left, -1, 0), (right - ball.x, 1, 0),
                             (ball.y - top, 0, -1), (bot - ball.y, 0, 1)]
                    m = min(cands, key=lambda c: c[0])
                    nx, ny, pen = m[1], m[2], m[0] + ball.r
                ball.x += nx * pen
                ball.y += ny * pen

                if self.state == SWING and not self.kick_applied and nx * self.dir > 0.25:
                    sp = KICK_SPEED[self.level]
                    if self.aim is not None:        # bola controlada: o jogador escolheu a direção
                        ball.vx = self.dir * math.cos(self.aim) * sp
                        ball.vy = math.sin(self.aim) * sp
                    else:
                        rel = max(-1.0, min(1.0, (ball.y - fy) / (h / 2)))
                        vx = self.dir * sp
                        vy = rel * sp * 0.30 + self.vy * 0.5
                        n = math.hypot(vx, vy)
                        ball.vx, ball.vy = vx / n * sp, vy / n * sp
                    self.kick_applied = True
                    result = 2
                else:
                    rvx, rvy = ball.vx - self.foot_vx, ball.vy - self.vy
                    vn = rvx * nx + rvy * ny
                    if vn < 0:
                        if (ball.glue is None and ball.glue_cd <= 0 and self.state in (IDLE, CHARGING)
                                and nx * self.dir > 0.5 and -vn <= GLUE_MAX_REL):
                            # encostou devagar na frente do boneco: gruda
                            lim = self.fig_h / 2 - 2
                            rel = max(-lim, min(lim, ball.y - (self.base_y(i) + self.offset)))
                            ball.glue = {"rod": self, "i": i, "rel": rel, "slip": 0.0, "t": 0.0}
                            ball.vx = ball.vy = 0.0
                        else:
                            e = BALL_RESTITUTION
                            rvx -= (1 + e) * vn * nx
                            rvy -= (1 + e) * vn * ny
                            ball.vx, ball.vy = rvx + self.foot_vx, rvy + self.vy
                        result = max(result, 1)
        return result

    # ---------- cola ----------
    def glue_pos(self, g):
        """Posição da bola grudada: na frente do corpo do boneco."""
        return (self.x + self.foot + self.dir * (FIG_W / 2 + BALL_R - 1),
                self.base_y(g["i"]) + self.offset + g["rel"])
