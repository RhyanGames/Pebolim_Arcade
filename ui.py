"""Utilidades de interface: fontes, texto e botões."""
import pygame
from settings import *

_fonts = {}


_SYSTEM_FONTS = ("/system/fonts/Roboto-Regular.ttf", "/system/fonts/DroidSans.ttf",
                 "/system/fonts/NotoSans-Regular.ttf")


def font(size):
    f = _fonts.get(size)
    if f is None:
        try:
            f = pygame.font.Font(None, size)     # fonte embutida do pygame (empacota bem no .exe)
        except Exception:                        # Android: se a fonte embutida não vier no APK
            f = None
            for path in _SYSTEM_FONTS:
                try:
                    f = pygame.font.Font(path, int(size * 0.75))
                    break
                except Exception:
                    continue
            if f is None:
                f = pygame.font.SysFont(None, size)
        _fonts[size] = f
    return f


_text_cache = {}
_dim_cache = {}


def draw_text(surf, text, size, color, pos, anchor="center", shadow=True):
    """Texto com cache: cada (texto, tamanho, cor) é renderizado uma vez só (render de fonte é caro no celular)."""
    key = (text, size, color, shadow)
    spr = _text_cache.get(key)
    if spr is None:
        f = font(size)
        img = f.render(text, True, color)
        if shadow:
            w, h = img.get_size()
            spr = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
            spr.blit(f.render(text, True, (0, 0, 0)), (2, 2))
            spr.blit(img, (0, 0))
        else:
            spr = img
        try:
            spr = spr.convert_alpha()
        except Exception:
            pass
        if len(_text_cache) > 400:          # textos que mudam sempre (ex.: digitando) não enchem a memória
            _text_cache.clear()
        _text_cache[key] = spr
    w, h = spr.get_size()
    if shadow:
        w, h = w - 2, h - 2
    rect = pygame.Rect(0, 0, w, h)
    setattr(rect, anchor, pos)
    surf.blit(spr, rect.topleft)
    return rect


def dim(surf, alpha=170):
    ov = _dim_cache.get(alpha)
    if ov is None:
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, alpha))
        try:
            ov = ov.convert_alpha()
        except Exception:
            pass
        _dim_cache[alpha] = ov
    surf.blit(ov, (0, 0))


class Button:
    def __init__(self, rect, text, color=(60, 120, 220), size=38):
        self.rect = pygame.Rect(rect)
        self.text, self.color, self.size = text, color, size

    def draw(self, surf, focused=False):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        col = tuple(min(255, c + 35) for c in self.color) if (hover or focused) else self.color
        pygame.draw.rect(surf, (0, 0, 0), self.rect.move(0, 5), border_radius=14)
        pygame.draw.rect(surf, col, self.rect, border_radius=14)
        pygame.draw.rect(surf, WHITE if focused else (0, 0, 0), self.rect, 2, border_radius=14)
        draw_text(surf, self.text, self.size, WHITE, self.rect.center)

    def clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.rect.collidepoint(event.pos))
