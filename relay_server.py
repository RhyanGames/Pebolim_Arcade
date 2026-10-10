"""Servidor RELAY do Pebolim Arcade (roda na internet, NÃO no celular nem no jogo).

Ele só faz uma coisa: quando alguém cria uma sala, gera um código (ex.: 6A991L); quando
outro jogador digita o código, o servidor liga os dois e repassa os dados entre eles.
Assim os dois podem estar em internets diferentes, sem abrir porta no roteador.

Uso:      python relay_server.py            (porta 5555, ou a variável de ambiente PORT)
Só usa a biblioteca padrão do Python 3.8+.
"""
import asyncio
import json
import os
import random
import time

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # sem 0/O/1/I para não confundir
CODE_LEN = 6
MAX_ROOMS = 2000
ROOM_MAX_WAIT = 900          # segundos que uma sala espera o segundo jogador
HANDSHAKE_TIMEOUT = 15

rooms = {}                   # código -> dict(fut=Future, t=hora de criação)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def nodelay(writer):
    try:
        import socket
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass


async def send(writer, obj):
    writer.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())
    await writer.drain()


def close(writer):
    try:
        writer.close()
    except Exception:
        pass


async def pipe(src, dst):
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass


def new_code():
    for _ in range(50):
        code = "".join(random.choice(ALPHABET) for _ in range(CODE_LEN))
        if code not in rooms:
            return code
    return None


async def do_host(reader, writer):
    if len(rooms) >= MAX_ROOMS:
        await send(writer, {"ok": False, "err": "Servidor cheio, tente de novo em instantes."})
        return
    code = new_code()
    if code is None:
        await send(writer, {"ok": False, "err": "Não foi possível criar a sala."})
        return
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    rooms[code] = {"fut": fut, "t": time.time()}
    log("sala criada", code, "| salas:", len(rooms))
    try:
        await send(writer, {"ok": True, "code": code})
        eof = asyncio.ensure_future(reader.read(1))      # detecta se o host desistiu
        try:
            while not fut.done():
                done, _ = await asyncio.wait({fut, eof}, timeout=20, return_when=asyncio.FIRST_COMPLETED)
                if eof in done:
                    if not eof.result():
                        return                           # host saiu
                    eof = asyncio.ensure_future(reader.read(1))
                elif not done:
                    if time.time() - rooms[code]["t"] > ROOM_MAX_WAIT:
                        await send(writer, {"ok": False, "err": "Sala expirou."})
                        return
                    await send(writer, {"op": "wait"})   # mantém a conexão viva
        finally:
            if not eof.done():
                eof.cancel()
        jr, jw, finished = fut.result()
        await send(writer, {"op": "paired"})
        log("pareados", code)
        a = asyncio.ensure_future(pipe(reader, jw))
        b = asyncio.ensure_future(pipe(jr, writer))
        await asyncio.wait({a, b}, return_when=asyncio.FIRST_COMPLETED)
        a.cancel()
        b.cancel()
        close(jw)
        finished.set()
        log("fim", code)
    except Exception as ex:
        log("erro host", code, ex)
    finally:
        rooms.pop(code, None)


async def do_join(reader, writer, code):
    code = str(code).strip().upper()
    room = rooms.pop(code, None)
    if room is None or room["fut"].done():
        await send(writer, {"ok": False, "err": "Sala não encontrada. Confira o código."})
        return
    await send(writer, {"ok": True})
    finished = asyncio.Event()
    room["fut"].set_result((reader, writer, finished))
    await finished.wait()                                # o host cuida da ligação


async def handle(reader, writer):
    nodelay(writer)
    try:
        line = await asyncio.wait_for(reader.readline(), HANDSHAKE_TIMEOUT)
        if line[:4] in (b"GET ", b"HEAD", b"POST"):      # health-check de hospedagem (HTTP)
            body = b"Pebolim relay ok"
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
            return
        msg = json.loads(line)
        op = msg.get("op")
        if op == "host":
            await do_host(reader, writer)
        elif op == "join":
            await do_join(reader, writer, msg.get("code", ""))
        else:
            await send(writer, {"ok": False, "err": "Pedido inválido."})
    except Exception:
        pass
    finally:
        close(writer)


async def main():
    port = int(os.environ.get("PORT", "5555"))
    server = await asyncio.start_server(handle, "0.0.0.0", port)
    log(f"Relay do Pebolim Arcade ouvindo na porta {port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
