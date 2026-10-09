"""Efeitos sonoros gerados por código (sem arquivos externos)."""
import array
import math
import random
import pygame


class Sound:
    def __init__(self):
        self.ok = False
        self.snd = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.rate, fmt, self.ch = pygame.mixer.get_init()
            if fmt != -16:
                return
            self.snd = {
                "touch": self._seq([(700, 0.035)], 0.25),
                "kick": self._seq([(140, 0.09)], 0.5, noise=0.35),
                "wall": self._seq([(420, 0.04)], 0.2),
                "beep": self._seq([(660, 0.12)], 0.3),
                "go": self._seq([(990, 0.25)], 0.35),
                "goal": self._seq([(523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.30)], 0.4),
                "win": self._seq([(523, 0.15), (659, 0.15), (784, 0.15), (1047, 0.15),
                                  (784, 0.12), (1047, 0.45)], 0.4),
            }
            self.ok = True
        except Exception:
            self.ok = False

    def _seq(self, notes, vol, noise=0.0):
        data = array.array("h")
        for freq, dur in notes:
            n = int(self.rate * dur)
            for i in range(n):
                env = (1 - i / n) ** 1.5
                s = math.sin(2 * math.pi * freq * i / self.rate)
                if noise:
                    s = s * (1 - noise) + random.uniform(-1, 1) * noise
                v = int(32767 * vol * env * s)
                for _ in range(self.ch):
                    data.append(v)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def play(self, name):
        if self.ok and name in self.snd:
            try:
                self.snd[name].play()
            except Exception:
                pass
