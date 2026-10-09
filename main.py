"""Pebolim Arcade - ponto de entrada.  Execute:  python main.py

Se o jogo travar ao abrir (principalmente no celular), o erro aparece na tela e é salvo em
pebolim_erro.txt, em vez de o app simplesmente fechar."""
import os
import sys
import traceback


def save_error(text):
    """Grava o erro em arquivos (qualquer um que der certo) e no log do sistema."""
    paths = [os.path.join(os.environ.get("ANDROID_PRIVATE", ""), "pebolim_erro.txt"),
             "/sdcard/Download/pebolim_erro.txt",
             "/storage/emulated/0/Download/pebolim_erro.txt",
             "pebolim_erro.txt"]
    for p in paths:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
    try:
        print(text, file=sys.stderr, flush=True)
    except Exception:
        pass


def show_error(text):
    """Mostra o erro na tela até tocar/clicar (ou fechar a janela)."""
    save_error(text)
    try:
        import pygame
        pygame.init()
        screen = pygame.display.set_mode((0, 0))
        w, h = screen.get_size()
        font = None
        for cand in (None, "/system/fonts/Roboto-Regular.ttf", "/system/fonts/DroidSans.ttf"):
            try:
                font = pygame.font.Font(cand, max(18, h // 34))
                break
            except Exception:
                continue
        if font is None:
            font = pygame.font.SysFont(None, max(18, h // 34))
        cw = max(1, font.size("M")[0])
        cols = max(20, w // cw - 2)
        lines = ["O JOGO TEVE UM ERRO (tire uma foto desta tela). Toque para fechar.", ""]
        for raw in text.splitlines():
            while len(raw) > cols:
                lines.append(raw[:cols])
                raw = raw[cols:]
            lines.append(raw)
        maxl = max(5, h // font.get_linesize() - 1)
        lines = lines[:2] + lines[2:][-(maxl - 2):]          # mostra o FINAL do erro (a causa)
        clock = pygame.time.Clock()
        waited = 0.0
        while waited < 600:
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN) and waited > 1.0):
                    return
            screen.fill((120, 0, 0))
            for i, ln in enumerate(lines):
                screen.blit(font.render(ln, True, (255, 255, 255)), (8, 6 + i * font.get_linesize()))
            pygame.display.flip()
            waited += clock.tick(15) / 1000.0
    except Exception:
        pass


if __name__ == "__main__":
    try:
        import app
        app.main()
    except SystemExit:
        raise
    except BaseException:
        show_error(traceback.format_exc())
