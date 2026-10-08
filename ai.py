"""IA: acompanha a bola, escolhe o boneco mais próximo e chuta com forças variadas.
A dificuldade (Fácil / Normal / Difícil) muda reação, velocidade, precisão e agressividade.
Quando a bola chega devagar, a IA também pode dominá-la, mirar e chutar."""
import math
import random
from settings import *
from entities import IDLE, CHARGING, level_from_charge


class AIController:
    def __init__(self, rods, level=AI_DEFAULT_LEVEL, match=None):
        self.p = AI_LEVELS[max(0, min(len(AI_LEVELS) - 1, level))]
        self.match = match
        self.rods = rods
        self.timer = 0.0
        self.target = {r: 0.0 for r in rods}
        self.want = {r: 1 for r in rods}
        self.hold = {r: 0.0 for r in rods}
        self.wait = {r: 0.0 for r in rods}
        self.rolled = {r: False for r in rods}
        self.active = next((r for r in rods if r.kind == "M"), rods[0])   # a IA só move UMA haste por vez
        self.pending = None
        self.switch_t = 0.0

    def _update_active(self, ball, dt):
        """Escolhe qual haste controlar (pela área da bola, como o jogador) com tempo de reação."""
        m = self.match
        if m is None:
            return
        c = m.ctrl[self.active.team]
        if c is not None:                       # segurando a bola: continua nesta haste
            self.active, self.pending = c["rod"], None
            return
        want = None
        for x0, x1, rod in m.zones[self.active.team]:
            if x0 <= ball.x < x1:
                want = rod
                break
        if want is None or want is self.active:
            self.pending = None
            return
        if self.pending is not want:
            self.pending, self.switch_t = want, self.p["switch"]
        self.switch_t -= dt
        if self.switch_t <= 0:
            self.active, self.pending = want, None

    def update(self, dt, ball):
        self.timer -= dt
        think = self.timer <= 0
        if think:
            self.timer = self.p["reaction"]
        self._update_active(ball, dt)
        sp = self.p["speed"]
        for r in self.rods:
            act = r is self.active
            if act:
                if think:
                    self.target[r] = self._target(r, ball)
                diff = self.target[r] - r.offset
                r.move = max(-sp, min(sp, diff / AI_GAIN))
            else:
                r.move = 0.0                    # as outras hastes ficam paradas
            self._kick(r, ball, dt, act)

    def _target(self, r, ball):
        ahead = (ball.x - r.x) * r.dir          # > 0: bola do lado do gol adversário
        if r.kind != "G" and ahead < -30:       # bola já passou desta haste
            return r.offset if abs(ball.x - r.x) < 80 else 0.0
        err = self.p["error"]
        by = ball.y + ball.vy * self.p["lead"] + random.uniform(-err, err)
        i = min(range(r.n), key=lambda k: abs(by - r.base_y(k)))
        need = by - r.base_y(i)
        return max(-r.max_off, min(r.max_off, need))

    # ---------------------------------------------------------- controle de bola
    def _aim(self, r, ball):
        m = self.match
        if r.kind in ("M", "A"):                # mira no lado do gol oposto ao goleiro adversário
            gk = m.by_kind[1 - r.team]["G"]
            gx = FIELD_X if r.dir < 0 else FIELD_X + FIELD_W
            ty = CY + (CY - (CY + gk.offset))
            lim = GOAL_H * 0.35
            ty = max(CY - lim, min(CY + lim, ty))
            ang = math.atan2(ty - ball.y, abs(gx - ball.x))
        else:                                   # defesa/goleiro: tira a bola para o lado
            ang = math.radians(random.choice((-35, 0, 35)))
        mx = math.radians(CONTROL_AIM_MAX)
        return max(-mx, min(mx, ang))

    def _control(self, r, ball, dt):
        """Retorna True enquanto a IA está segurando a bola com esta haste (esperando para chutar)."""
        m = self.match
        t = r.team
        c = m.ctrl[t]
        if c is not None and c["rod"] is r:
            if r.state == CHARGING:
                return False                    # a lógica normal solta o chute na força escolhida
            self.wait[r] -= dt
            if self.wait[r] <= 0 and r.state == IDLE:
                self.want[r] = random.choices([0, 1, 2], weights=self.p["weights"])[0]
                self.hold[r] = 0.0
                r.start_charge()
            return True
        near = ball.speed <= CONTROL_MAX_SPEED and r.control_index(ball) is not None
        if not near:
            self.rolled[r] = False
            return False
        if (not self.rolled[r] and r.state == IDLE and r.cool <= 0 and m.phase == "play"
                and m.ctrl_cd[t] <= 0 and not any(m.ctrl)):
            self.rolled[r] = True               # decide uma vez por chegada da bola
            if random.random() < self.p["control"] and m.try_control(t, r):
                m.ctrl[t]["aim"] = self._aim(r, ball)
                self.wait[r] = random.uniform(*self.p["hold"])
                return True
        return False

    def _kick(self, r, ball, dt, act=True):
        if r.state == CHARGING:                 # chute em andamento sempre termina (mesmo se trocou de haste)
            self.hold[r] += dt
            if level_from_charge(r.charge) == self.want[r] or self.hold[r] > 1.6:
                r.release()
            return
        if not act or r.state != IDLE or r.cool > 0:
            return
        if self.match is not None:
            if self.match.frozen(r.team):       # adversário com a bola: fica parado
                return
            if self._control(r, ball, dt):
                return
        for fx, fy, w, h in r.figures():
            front = (ball.x - fx) * r.dir
            if 0 < front < w / 2 + ball.r + 14 and abs(ball.y - fy) < h / 2 + ball.r * 0.6:
                if random.random() < self.p["kick_chance"]:
                    self.want[r] = random.choices([0, 1, 2], weights=self.p["weights"])[0]
                    self.hold[r] = 0.0
                    r.start_charge()
                return
