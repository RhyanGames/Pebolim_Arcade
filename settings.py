"""Constantes e configurações globais do Pebolim Arcade."""
import os
import sys

WIDTH, HEIGHT = 1000, 700

# ---- Celular / toque ----
# Detecta Android automaticamente. No PC dá para testar com:  python main.py --touch  (o mouse vira o dedo)
ANDROID = "ANDROID_ARGUMENT" in os.environ or ("ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ)
MOBILE = ANDROID or ("--touch" in sys.argv) or os.environ.get("PEBOLIM_TOUCH") == "1"
PAD = 200 if MOBILE else 0                 # painéis de controle dos lados do campo (só no modo toque)
LW, LH = WIDTH + 2 * PAD, HEIGHT           # tamanho total da tela lógica
FPS = 120
TITLE = "Pebolim Arcade"
VERSION = "0.1.3"
CREDIT = "By Rhyan (EsnorQGames)"


def resource_path(rel):
    """Caminho de um arquivo do jogo (funciona no .exe do PyInstaller, no APK e rodando o .py)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ---- Campo (visão de cima; gols nas laterais esquerda e direita) ----
FIELD_X, FIELD_Y, FIELD_W, FIELD_H = 60, 110, 880, 470
CY = FIELD_Y + FIELD_H / 2
GOAL_H = 170          # abertura do gol
GOAL_DEPTH = 34       # profundidade da rede

# ---- Medidas ----
BALL_R = 10
FIG_W = 16            # espessura do boneco (eixo X)
FIG_H = 34            # largura do boneco (eixo Y)
GOALIE_H = 50
REACH = 24            # quanto o pé avança no chute
SHOULDER_W = 12       # boneco "chutou" (formato T): largura dos ombros no eixo X
SHOULDER_H = 0.90     # altura dos ombros (fração da altura do boneco)
FOOT_H = 0.55         # altura do pé estendido (fração da altura do boneco)
T_THRESHOLD = 6       # a partir de quantos px o pé é considerado estendido

# Tipos de haste: nº de bonecos, espaçamento, altura, curso máximo (None = automático)
ROD_TYPES = {
    "G": dict(name="Goleiro",    n=1, spacing=0,   h=GOALIE_H, travel=80),
    "D": dict(name="Defesa",     n=2, spacing=160, h=FIG_H,    travel=None),
    "M": dict(name="Meio-campo", n=5, spacing=84,  h=FIG_H,    travel=None),
    "A": dict(name="Ataque",     n=3, spacing=130, h=FIG_H,    travel=None),
}
# Ordem das 8 hastes da esquerda para a direita: (time, tipo). Time 0 = esquerda, 1 = direita.
ROD_LAYOUT = [(0, "G"), (0, "D"), (1, "A"), (0, "M"),
              (1, "M"), (0, "A"), (1, "D"), (1, "G")]

ROD_SPEED = 430.0     # px/s
ROD_ACCEL = 4200.0

# ---- Barra de força ----
CHARGE_SPEED = 1.5               # unidades/s (a barra vai e volta enquanto o botão está pressionado)
ZONE_WEAK, ZONE_STRONG = 0.30, 0.70
KICK_SPEED = (360.0, 640.0, 980.0)   # fraco, normal, forte (px/s)
LEVEL_NAMES = ("FRACO", "NORMAL", "FORTE")
LEVEL_COLORS = ((80, 210, 255), (80, 220, 100), (240, 60, 60))

# ---- Chute (um único giro por ação) ----
T_SWING = 0.11        # tempo da batida para frente
T_RETURN = 0.22       # tempo de volta
KICK_COOLDOWN = 0.10  # espera antes de poder carregar outro chute

# ---- Física da bola ----
BALL_FRICTION = 0.45
BALL_MAX = 1150.0
WALL_BOUNCE = 0.80
SUBSTEPS = 4              # máximo de passos de física por quadro
SUBSTEP_PX = 6.0          # passos adaptativos: ~1 passo a cada 6 px que a bola anda
SUBSTEPS_MIN = 2
BALL_RESTITUTION = 0.15   # quique da bola nos bonecos (baixo: a bola "morre" no boneco)
IDLE_NUDGE_TIME = 3.0     # bola parada por tanto tempo (s) = ela se mexe sozinha
IDLE_NUDGE_SPEED = 300.0  # velocidade do empurrãozinho
IDLE_SPEED = 25.0         # abaixo disso (px/s) a bola é considerada parada

# ---- "Cola": a bola gruda no boneco quando encosta devagar e vai junto com a haste ----
GLUE_MAX_REL = 430.0      # só gruda se bater no boneco com velocidade até essa (px/s)
GLUE_FREE_SPEED = 170.0   # mexer a haste mais devagar que isso nunca solta a bola
GLUE_SLIP_TIME = 0.15     # mexendo a haste na velocidade máxima, a bola escapa em ~0,25 s (mexer devagar = ela acompanha)
GLUE_MAX_TIME = 6.0       # no máximo tanto tempo grudada (depois é empurrada para frente)
GLUE_COOLDOWN = 0.45      # depois de soltar, não gruda de novo por esse tempo (s)

# ---- Regras ----
EARLY_CLINCH = True   # encerra a partida se um jogador já garantiu a maioria das rodadas

GOALIE_INSET = 20     # distância do goleiro até a linha de fundo (px)

# ---- Campo curvado (cuia): a bola é puxada de leve para o centro e nunca fica parada nas bordas ----
CURVE_KX = 0.17       # aceleração (px/s² por px de distância do centro) no eixo X
CURVE_KY = 0.28       # idem no eixo Y

# ---- Controle de bola (C = Player 1 | SHIFT = Player 2) ----
CONTROL_MAX_SPEED = 450.0   # só dá para controlar se a bola estiver de lenta até média
CONTROL_FRONT = 44.0        # alcance da área de controle à frente do boneco (px)
CONTROL_PAD = 12.0          # folga da área acima e abaixo do boneco (px)
CONTROL_AIM_MAX = 50.0      # ângulo máximo da mira (graus para cima/baixo)
CONTROL_AIM_SPEED = 110.0   # velocidade da mira (graus/s)
CONTROL_MAX_TIME = 5.0      # tempo máximo segurando a bola (s); o time adversário fica parado nesse tempo
CONTROL_COOLDOWN = 0.6      # espera para controlar de novo depois de soltar (s)

# ---- Troca automática de haste ----
AUTO_ZONES = True     # a bola entra na área de uma haste -> o controle vai para ela
# Limites das áreas (fração da largura do campo, do gol do time até o gol adversário):
# goleiro | defesa | meio-campo | ataque.  O time da direita usa o espelho.
# Depois do último limite o controle fica no ataque.
ZONE_BOUNDS = (0.0, 0.1875, 0.375, 0.625, 0.865)

# ---- IA: níveis de dificuldade (escolhidos no menu) ----
AI_GAIN = 22.0
# 'switch' = tempo (s) que a IA leva para trocar de haste, como um jogador de verdade (ela controla 1 haste por vez)
AI_LEVELS = (
    dict(name="Fácil",   reaction=0.20, speed=0.55, error=30.0, lead=0.03, kick_chance=0.10, weights=(5, 4, 1),
         control=0.15, hold=(0.60, 1.20), switch=0.55),
    dict(name="Normal",  reaction=0.09, speed=0.80, error=14.0, lead=0.07, kick_chance=0.25, weights=(2, 5, 3),
         control=0.35, hold=(0.35, 0.80), switch=0.25),
    dict(name="Difícil", reaction=0.03, speed=1.00, error=3.0,  lead=0.12, kick_chance=0.60, weights=(1, 3, 6),
         control=0.60, hold=(0.20, 0.50), switch=0.08),
)
AI_DEFAULT_LEVEL = 1

# ---- Cores ----
BG = (20, 28, 40)
WHITE = (255, 255, 255)
LIGHT = (200, 210, 225)
GRAY = (140, 150, 165)
YELLOW = (255, 214, 64)
GRASS = (36, 140, 64)
GRASS2 = (42, 152, 70)
WOOD = (122, 78, 40)
WOOD_DARK = (74, 46, 24)
STEEL = (150, 156, 168)
TEAM_COLORS = ((84, 104, 250), (255, 52, 52))      # Player 1 azul, Player 2 / IA vermelho
TEAM_DARK = ((30, 40, 150), (150, 20, 20))
HEAD_COLOR = (255, 187, 90)          # cabeça (laranja)
KICK_POSE_MIN = 6.0                  # a partir de quantos px o pé avançado troca a cápsula pelo desenho de chute

# ---- Online ----
NET_PORT = 5555
# Servidor relay para jogar online entre internets diferentes (veja relay_server.py e o README).
# Coloque aqui o endereço onde você hospedou o relay:
#   Render/web:   "wss://meu-relay.onrender.com"
#   TCP puro:     "meu-servidor.exemplo.com:5555"
# Vazio = o jogo usa só o modo direto (IP:porta, mesma rede ou VPN).
RELAY_SERVER = os.environ.get("wss://pebolim-arcade.onrender.com", "")
NET_TIMEOUT = 5.0     # segundos sem receber nada = desconectado
