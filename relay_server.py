"""Servidor RELAY do Pebolim Arcade (roda na internet, NÃO no celular nem no jogo).

Ele só faz uma coisa: quando alguém cria uma sala, gera um código (ex.: 6A991L); quando
outro jogador digita o código, o servidor liga os dois e repassa os dados entre eles.
Assim os dois podem estar em internets diferentes, sem abrir porta no roteador.

Aceita dois tipos de conexão na MESMA porta:
  * WebSocket (ws:// ou wss://)  -> Render, Fly, qualquer hospedagem web
  * TCP puro                     -> VPS, Railway (TCP Proxy), seu PC

Uso:      python relay_server.py            (porta 5555, ou a variável de ambiente PORT)
Só usa a biblioteca padrão do Python 3.8+.
"""
import asyncio
import base64
import hashlib
import json
import os
import random
import struct
import time

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # sem 0/O/1/I para não confundir
CODE_LEN = 6
MAX_ROOMS = 2000
ROOM_MAX_WAIT = 900          # segundos que uma sala espera o segundo jogador
HANDSHAKE_TIMEOUT = 15
WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

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


class WSStream:
    """Uma conexão WebSocket com a mesma interface (read/readline/write/drain/close) de um stream TCP.
    Os bytes das mensagens WebSocket são tratados como um fluxo contínuo."""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.buf = bytearray()
        self.eof = False

    async def _frame(self):
        """Próxima mensagem de dados (bytes) ou None se a conexão fechou."""
        try:
            while True:
                b0, b1 = await self.reader.readexactly(2)
                op, ln, masked = b0 & 0x0F, b1 & 0x7F, b1 & 0x80
                if ln == 126:
                    ln = struct.unpack(">H", await self.reader.readexactly(2))[0]
                elif ln == 127:
                    ln = struct.unpack(">Q", await self.reader.readexactly(8))[0]
                if ln > (1 << 20):
                    return None
                mask = await self.reader.readexactly(4) if masked else b""
                data = await self.reader.readexactly(ln) if ln else b""
                if masked and ln:
                    key = (mask * (ln // 4 + 1))[:ln]
                    data = (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(ln, "big")
                if op == 8:                       # close
                    return None
                if op == 9:                       # ping -> pong
                    self._send(10, data)
                    await self.writer.drain()
                    continue
                if op == 10:                      # pong
                    continue
                return data
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            return None

    def _send(self, op, data):
        n = len(data)
        if n < 126:
            hdr = bytes([0x80 | op, n])
        elif n < 65536:
            hdr = bytes([0x80 | op, 126]) + struct.pack(">H", n)
        else:
            hdr = bytes([0x80 | op, 127]) + struct.pack(">Q", n)
        self.writer.write(hdr + data)

    async def read(self, n=65536):
        while not self.buf and not self.eof:
            p = await self._frame()
            if p is None:
                self.eof = True
            else:
                self.buf += p
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    async def readline(self):
        while b"\n" not in self.buf and not self.eof:
            p = await self._frame()
            if p is None:
                self.eof = True
            else:
                self.buf += p
        i = self.buf.find(b"\n")
        end = len(self.buf) if i < 0 else i + 1
        out = bytes(self.buf[:end])
        del self.buf[:end]
        return out

    def write(self, data):
        self._send(2, bytes(data))

    async def drain(self):
        await self.writer.drain()

    def close(self):
        try:
            self.writer.write(b"\x88\x00")
            self.writer.close()
        except Exception:
            pass

    def get_extra_info(self, name, default=None):
        return self.writer.get_extra_info(name, default)


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


async def read_http_headers(reader):
    headers = {}
    while True:
        line = await asyncio.wait_for(reader.readline(), HANDSHAKE_TIMEOUT)
        if line in (b"\r\n", b"\n", b""):
            return headers
        k, _, v = line.decode("latin-1").partition(":")
        headers[k.strip().lower()] = v.strip()


async def handle(reader, writer):
    nodelay(writer)
    r = w = None
    try:
        line = await asyncio.wait_for(reader.readline(), HANDSHAKE_TIMEOUT)
        r, w = reader, writer
        if line[:4] in (b"GET ", b"HEAD", b"POST"):
            headers = await read_http_headers(reader)
            key = headers.get("sec-websocket-key")
            if "websocket" in headers.get("upgrade", "").lower() and key:
                accept = base64.b64encode(hashlib.sha1(key.encode() + WS_GUID).digest()).decode()
                writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                              "Connection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
                await writer.drain()
                r = w = WSStream(reader, writer)
                line = await asyncio.wait_for(r.readline(), HANDSHAKE_TIMEOUT)
            else:                                        # health-check / navegador: responde "ok"
                body = b"Pebolim relay ok"
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                             + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
                await writer.drain()
                return
        msg = json.loads(line)
        op = msg.get("op")
        if op == "host":
            await do_host(r, w)
        elif op == "join":
            await do_join(r, w, msg.get("code", ""))
        else:
            await send(w, {"ok": False, "err": "Pedido inválido."})
    except Exception:
        pass
    finally:
        close(w or writer)


async def main():
    port = int(os.environ.get("PORT", "5555"))
    server = await asyncio.start_server(handle, "0.0.0.0", port)
    log(f"Relay do Pebolim Arcade ouvindo na porta {port} (WebSocket e TCP)")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
