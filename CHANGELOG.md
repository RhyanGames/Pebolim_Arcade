# Histórico de versões — Pebolim Arcade

Regra de versão: `MAJOR.MINOR.PATCH` (ex.: v4.2.1)

- **MAJOR** (primeiro número): `0` = desenvolvimento inicial, tudo ainda pode mudar. Sobe só em mudança grande que quebra o que existia.
- **MINOR** (segundo): sobe quando entra **funcionalidade nova** (o PATCH volta a 0).
- **PATCH** (terceiro): sobe quando só há **correção de bug** (nada de novo).
- Se nada mudou no jogo, a versão **não muda**.

A versão aparece no canto do menu (ex.: `v0.2.0`) e vem de `VERSION` em `settings.py`
(o `buildozer.spec` também tem `version`, mantenha os dois iguais).

## 0.2.0 — online mais responsivo
- Novo: ping de cada jogador e "Atraso da partida" na tela online.
- Novo: predição no convidado: a haste própria se mexe na hora, e a troca de haste também.
- Novo: o chute do convidado (carregar/chutar) anima na hora; a bola continua sendo do host.
- Servidor de salas (`wss://pebolim-arcade.onrender.com`) e `relay.txt` opcional para trocar o endereço.

## 0.1.1 — base
- Online com código de sala curto (copiar/colar), entre internets diferentes.
- Menos travadas no celular (caches de desenho).
- Bola quica pouco, "cola" no boneco e se mexe sozinha se ficar parada 5 s.
- Menu com imagem, ícone e crédito "By Rhyan (EsnorQGames)".
