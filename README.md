# Pebolim Arcade (Python + Pygame)

## Rodar
    pip install -r requirements.txt
    python main.py

## Gerar o .exe (Windows)
    pip install pygame pyinstaller
    pyinstaller --onefile --noconsole --name PebolimArcade main.py
O executável fica em `dist\PebolimArcade.exe` (ou dê dois cliques em `build_exe.bat`).

## Controles
- Player 1: W/S mover haste | A/D trocar haste (ou 1-4) | ESPAÇO chutar (segure e solte)
- Player 2: SETAS cima/baixo mover | ESQ/DIR trocar haste | ENTER chutar
- Contra a IA o Player 1 também pode usar SETAS + ENTER
- ESC / P: pausa

Ajuste física, velocidade da IA e regras em `settings.py`.

## Controle de bola
Com a bola devagar (até velocidade média) dentro da área de controle do boneco (retângulo que acende):
- Player 1: C | Player 2: SHIFT direito (contra a IA, C ou SHIFT)
- Segurando a bola: W/S (ou SETAS) ajustam a mira, ESPAÇO/ENTER carrega e solta o chute (força), C/SHIFT solta sem chutar.
- Máximo de 5 s segurando. Enquanto isso o time adversário fica parado (não move nem chuta).
- Contra a IA, a mira da IA fica escondida.

## Campo curvado
O campo é uma "cuia": a bola é puxada de leve para o centro (CURVE_KX/CURVE_KY em settings.py).

## IA
A IA move uma haste por vez (a da área onde a bola está), com um tempo de reação para trocar que depende da dificuldade.

## Online (2 PCs)
1. Quem hospeda: menu > "Online: criar sala" > CRIAR SALA. A tela mostra o endereço (ip:porta).
2. Quem entra: menu > "Online: entrar na sala", digita o endereço e clica ENTRAR NA SALA.
3. Mesmo Wi-Fi: funciona direto. Pela internet, o jeito mais fácil é uma VPN (Radmin VPN, ZeroTier ou
   Tailscale): os dois entram na mesma rede e usam o IP da VPN do host. Alternativa: liberar a porta TCP 5555
   no roteador e passar o IP público.
4. O host é o Player 1 (azul) e quem entra é o Player 2 (vermelho). As regras (rodadas e pontos) são do host.
5. O Windows pode perguntar sobre o Firewall na primeira vez: clique em Permitir.
Quem entra joga com W/S, A/D, 1-4, ESPAÇO e C (ou setas, ENTER e SHIFT). A porta fica em NET_PORT (settings.py).

## Celular (Android)
O jogo detecta o Android sozinho e mostra controles na tela: analógico à esquerda (arraste para cima/baixo
move a haste e, segurando a bola, ajusta a mira), botões GOL/DEF/MEIO/ATQ, CONTROLE, CHUTE (segure e solte
para dar força) e pausa. Em modo toque não há Player vs Player local; use Player vs IA ou Online.

Testar no PC com a tela de celular:   python main.py --touch   (o mouse faz o papel de um dedo)

Gerar o APK (precisa de Linux ou WSL no Windows):
    pip install buildozer cython
    buildozer android debug
O APK sai em bin/. Copie para o celular e instale (permitir "fontes desconhecidas").
Alternativa rápida para testar sem gerar APK: app Pydroid 3 (instale o pygame pelo Pip dele e rode main.py).
iPhone: não é possível sem um Mac e conta de desenvolvedor da Apple.

## APK sem instalar nada no PC (GitHub Actions)
1. Crie uma conta grátis em github.com e um repositório novo (pode ser privado).
2. Envie o CONTEÚDO desta pasta (main.py, buildozer.spec, a pasta .github etc.) para a raiz do repositório.
3. Aba "Actions" > "Gerar APK" > "Run workflow". Espera uns 20 a 40 minutos.
4. Quando terminar, abra a execução e baixe o "pebolim-apk" na seção Artifacts.
Se falhar, o log completo fica na própria página; mande as últimas linhas do passo "Compilar o APK".

---

## Online com código de sala (qualquer internet)

Para jogar entre internets diferentes (ex.: você no Wi-Fi de casa, o amigo no 4G em outra cidade) o jogo
usa um **servidor relay** pequeno (`relay_server.py`). Ele só liga os dois jogadores pelo código da sala.
O relay precisa ficar **ligado numa máquina com endereço público** (você hospeda uma vez; todos usam).

1. Hospede o `relay_server.py` (porta TCP 5555, ou a variável `PORT`). Precisa aceitar **TCP puro**.
   - Teste rápido no seu PC: `python relay_server.py` + um túnel TCP (ex.: playit.gg) que dê um endereço público.
   - Fixo: uma VPS/VM pequena (qualquer nuvem) ou um serviço que aceite TCP e rode o `Dockerfile` desta pasta.
2. Abra `settings.py` e preencha uma linha:  `RELAY_SERVER = "seu-servidor.exemplo.com:5555"`
   (ou defina a variável de ambiente `PEBOLIM_RELAY`). Gere de novo o .exe / APK.
3. No jogo: **Online: criar sala** mostra um código (ex.: `6A991L`) — toque nele para copiar.
   O amigo escolhe **Online: entrar na sala**, digita (ou toca em **COLAR**) e entra.

Sem `RELAY_SERVER` preenchido, o jogo continua com o modo direto (`ip:porta`, mesma rede / VPN).
