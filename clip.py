"""Copiar / colar texto (área de transferência) em Windows, Linux e Android, sem dependências extras."""
import ctypes
import subprocess
import sys

_lib = None


def _sdl():
    """A biblioteca SDL2 que o pygame já carregou (tem a função de clipboard)."""
    global _lib
    if _lib is None:
        _lib = False
        for name in ("SDL2.dll", "libSDL2-2.0.so.0", "libSDL2.so", "libSDL2-2.0.0.dylib", "SDL2"):
            try:
                _lib = ctypes.CDLL(name)
                break
            except OSError:
                continue
    return _lib or None


def copy(text):
    """Copia o texto. Retorna True se algum método funcionou."""
    lib = _sdl()
    if lib is not None:
        try:
            lib.SDL_SetClipboardText.argtypes = [ctypes.c_char_p]
            lib.SDL_SetClipboardText.restype = ctypes.c_int
            if lib.SDL_SetClipboardText(text.encode("utf-8")) == 0:
                return True
        except Exception:
            pass
    try:
        import pygame
        pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
        return True
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            subprocess.run(["clip"], input=text.encode("utf-8"), check=True, creationflags=0x08000000)
            return True
        except Exception:
            pass
    return False


def paste():
    """Texto da área de transferência ('' se não der)."""
    lib = _sdl()
    if lib is not None:
        try:
            lib.SDL_GetClipboardText.argtypes = []
            lib.SDL_GetClipboardText.restype = ctypes.c_void_p
            ptr = lib.SDL_GetClipboardText()
            if ptr:
                txt = ctypes.string_at(ptr).decode("utf-8", errors="ignore")
                try:
                    lib.SDL_free.argtypes = [ctypes.c_void_p]
                    lib.SDL_free(ptr)
                except Exception:
                    pass
                return txt
        except Exception:
            pass
    try:
        import pygame
        pygame.scrap.init()
        raw = pygame.scrap.get(pygame.SCRAP_TEXT)
        if raw:
            return raw.decode("utf-8", errors="ignore").strip("\x00")
    except Exception:
        pass
    return ""
