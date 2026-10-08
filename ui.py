"""Utilidades de interface: fontes, texto e botões."""
import pygame
from settings import *

_fonts = {}


def font(size):
    f = _fonts.get(size)
    if f is None:
        f = pygame.font.Font(None, size)     # fonte embutida do pygame (empacota bem no .exe)
        _fonts[size] = f
    return f


def draw_text(surf, text, size, color, pos, anchor="center", shadow=True):
    f = font(size)
    img = f.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    if shadow:
        surf.blit(f.render(text, True, (0, 0, 0)), rect.move(2, 2))
    surf.blit(img, rect)
    return rect


def dim(surf, alpha=170):
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((0, 0, 0, alpha))
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
