"""Rede do modo online (TCP + mensagens JSON, uma por linha). Só usa a biblioteca padrão.

Dois jeitos de jogar:
  * Sala por CÓDIGO (qualquer internet): os dois jogadores conectam no servidor relay (relay_server.py).
  * Endereço direto ip:porta (mesma rede / VPN): Listener (host) + Connector (cliente).
"""
import base64
import json
import os
import queue
import re
import socket
import struct
import threading
import time

from settings import NET_TIMEOUT

WAKE_TIMEOUT = 80.0          # servidores gratuitos "dormem": a 1ª conexão pode demorar quase 1 min


class Peer:
    """Uma conexão: uma thread lê as mensagens, o jogo consulta com poll()."""

    def __init__(self, sock):
        self.sock = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        sock.settimeout(None)
        self.q = queue.Queue()
        self.alive = True
        self.last_rx = time.time()
        self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = b""
        try:
            while self.alive:
                data = self.sock.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line:
                        try:
                            self.q.put(json.loads(line))
                            self.last_rx = time.time()
                        except ValueError:
                            pass
        except OSError:
            pass
        self.alive = False

    def send(self, obj):
        if not self.alive:
            return False
        try:
            with self.lock:
                self.sock.sendall((json.dumps(obj, separators=(",", ":")) + "\n").encode())
            return True
        except OSError:
            self.alive = False
            return False

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def timed_out(self):
        return (not self.alive) or (time.time() - self.last_rx > NET_TIMEOUT)

    def close(self):
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ----------------------------------------------------------------------------- direto (ip:porta)
class Listener:
    """Host direto: espera UM jogador entrar (mesma rede, VPN ou porta liberada)."""

    def __init__(self, port):
        self.error = None
        self.peer = None
        self.code = ""
        self.status = ""
        self._stop = False
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.srv.bind(("0.0.0.0", port))
            self.srv.listen(1)
            self.srv.settimeout(0.3)
        except OSError as ex:
            self.error = f"Não foi possível abrir a porta {port}: {ex}"
            return
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop and self.peer is None:
            try:
                conn, _addr = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.peer = Peer(conn)

    def close(self):
        self._stop = True
        try:
            self.srv.close()
        except OSError:
            pass


class Connector:
    """Cliente direto: conecta em segundo plano (para o jogo não travar)."""

    def __init__(self, addr, default_port):
        self.peer = None
        self.error = None
        self.done = False
        self.status = ""
        host, port = addr.strip(), default_port
        if ":" in host:
            host, p = host.rsplit(":", 1)
            try:
                port = int(p)
            except ValueError:
                self.error, self.done = "Endereço inválido (use ip:porta)", True
                return
        if not host:
            self.error, self.done = "Digite o código ou o endereço do host", True
            return
        threading.Thread(target=self._run, args=(host, port), daemon=True).start()

    def _run(self, host, port):
        try:
            sock = socket.create_connection((host, port), timeout=6)
            self.peer = Peer(sock)
        except OSError as ex:
            self.error = f"Não conectou: {ex}"
        self.done = True


# ----------------------------------------------------------------------------- sala por código (relay)
def is_room_code(text):
    """Código de sala = 4 a 8 letras/números (nada de '.' ou ':' como num endereço)."""
    return re.fullmatch(r"[A-Za-z0-9]{4,8}", text.strip()) is not None


class LineReader:
    """Lê uma linha por vez SEM ler nada além dela (o resto do fluxo é do jogo)."""

    def __init__(self, sock):
        self.sock, self.buf = sock, bytearray()

    def readline(self):
        while True:
            b = self.sock.recv(1)
            if not b:
                raise ConnectionError("conexão fechada")
            if b == b"\n":
                line, self.buf = bytes(self.buf), bytearray()
                return line
            self.buf += b
            if len(self.buf) > 4096:
                raise ConnectionError("resposta inválida")


def parse_relay(server):
    """'wss://x.onrender.com' -> WebSocket seguro | 'x.com:5555' -> TCP puro. Retorna (host, porta, ws, tls)."""
    s = server.strip()
    ws = tls = False
    port = 5555
    for prefix, is_tls, p in (("wss://", True, 443), ("https://", True, 443), ("ws://", False, 80), ("http://", False, 80)):
        if s.lower().startswith(prefix):
            s, ws, tls, port = s[len(prefix):], True, is_tls, p
            break
    s = s.split("/")[0]
    host = s
    if ":" in s:
        host, p = s.rsplit(":", 1)
        port = int(p)
    if not host:
        raise ValueError("vazio")
    return host, port, ws, tls


class WSSock:
    """Um WebSocket (cliente) com cara de socket: sendall/recv/settimeout/shutdown/close.
    Cada sendall vira uma mensagem; recv devolve os bytes das mensagens como um fluxo contínuo."""

    def __init__(self, raw, leftover=b""):
        self.raw = raw
        self.rawbuf = bytearray(leftover)
        self.buf = bytearray()
        self.closed = False
        self.wlock = threading.Lock()

    def settimeout(self, t):
        self.raw.settimeout(t)

    def setsockopt(self, *a):
        try:
            self.raw.setsockopt(*a)
        except OSError:
            pass

    def _send_frame(self, op, data):
        n = len(data)
        mask = os.urandom(4)
        if n < 126:
            hdr = bytes([0x80 | op, 0x80 | n])
        elif n < 65536:
            hdr = bytes([0x80 | op, 0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr = bytes([0x80 | op, 0x80 | 127]) + struct.pack(">Q", n)
        body = b""
        if n:
            key = (mask * (n // 4 + 1))[:n]
            body = (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")
        with self.wlock:
            self.raw.sendall(hdr + mask + body)

    def sendall(self, data):
        self._send_frame(2, bytes(data))

    def _need(self, n):
        while len(self.rawbuf) < n:                 # um timeout aqui não perde nada: o buffer é mantido
            chunk = self.raw.recv(65536)
            if not chunk:
                raise ConnectionError("conexão fechada")
            self.rawbuf += chunk

    def _next_frame(self):
        self._need(2)
        op, ln = self.rawbuf[0] & 0x0F, self.rawbuf[1] & 0x7F
        masked, off = self.rawbuf[1] & 0x80, 2
        if ln == 126:
            self._need(4)
            ln, off = struct.unpack(">H", bytes(self.rawbuf[2:4]))[0], 4
        elif ln == 127:
            self._need(10)
            ln, off = struct.unpack(">Q", bytes(self.rawbuf[2:10]))[0], 10
        mk = 4 if masked else 0
        self._need(off + mk + ln)
        data = bytes(self.rawbuf[off + mk:off + mk + ln])
        if masked and ln:
            key = (bytes(self.rawbuf[off:off + 4]) * (ln // 4 + 1))[:ln]
            data = (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(ln, "big")
        del self.rawbuf[:off + mk + ln]
        return op, data

    def recv(self, n):
        while not self.buf:
            if self.closed:
                return b""
            try:
                op, data = self._next_frame()
            except ConnectionError:
                self.closed = True
                return b""
            if op in (0, 1, 2):
                self.buf += data
            elif op == 8:
                self.closed = True
                return b""
            elif op == 9:
                self._send_frame(10, data)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def shutdown(self, how):
        self.raw.shutdown(how)

    def close(self):
        try:
            self._send_frame(8, b"")
        except OSError:
            pass
        try:
            self.raw.close()
        except OSError:
            pass


def _tcp_or_tls(host, port, tls):
    if not tls:
        return socket.create_connection((host, port), timeout=15)
    try:
        import ssl
    except ImportError:
        raise ConnectionError("Este aparelho não tem suporte a conexão segura (ssl).")
    for verify in (True, False):                    # Android pode não ter os certificados: tenta sem verificar
        sock = socket.create_connection((host, port), timeout=15)
        try:
            ctx = ssl.create_default_context() if verify else ssl._create_unverified_context()
            return ctx.wrap_socket(sock, server_hostname=host)
        except ssl.SSLError:
            sock.close()
            if not verify:
                raise
        except OSError:
            sock.close()
            raise


def ws_open(host, port, tls):
    """Conecta e faz o handshake WebSocket. Levanta OSError se o servidor ainda não está pronto."""
    sock = _tcp_or_tls(host, port, tls)
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET / HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk or len(data) > 8192:
                raise OSError("handshake falhou")
            data += chunk
        head, _, rest = data.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0] + b" ":
            raise OSError("servidor ainda não está pronto")
        return WSSock(sock, rest)
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise


def _relay_connect(server, status=None, stop=None):
    """Conecta no relay (WebSocket ou TCP). Servidores grátis 'dormem': tenta de novo por até ~80 s."""
    try:
        host, port, ws, tls = parse_relay(server)
    except ValueError:
        raise ConnectionError("Endereço do servidor online inválido.")
    if not ws:
        try:
            return socket.create_connection((host, port), timeout=WAKE_TIMEOUT)
        except socket.gaierror:
            raise ConnectionError("Não achei o servidor online. Confira a internet.")
        except OSError:
            raise ConnectionError("Não consegui conectar ao servidor online.")
    deadline = time.time() + WAKE_TIMEOUT
    while True:
        try:
            return ws_open(host, port, tls)
        except socket.gaierror:
            raise ConnectionError("Não achei o servidor online. Confira a internet.")
        except (ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError):
            pass                                    # servidor ainda acordando: tenta de novo
        except ConnectionError:
            raise                                   # erro definitivo (ex.: sem suporte a ssl)
        except OSError:
            pass                                    # handshake ainda não pronto / timeout: tenta de novo
        if (stop and stop()) or time.time() > deadline:
            raise ConnectionError("O servidor online não respondeu.")
        if status:
            status("Acordando o servidor... (pode levar até 1 min)")
        time.sleep(3)


class RelayHost:
    """Cria uma sala no relay e espera o outro jogador (mesma interface do Listener)."""

    def __init__(self, server):
        self.error = None
        self.peer = None
        self.code = ""
        self.status = "Conectando ao servidor... (na 1ª vez pode demorar até 1 min)"
        self._stop = False
        self._sock = None
        threading.Thread(target=self._run, args=(server,), daemon=True).start()

    def _set_status(self, text):
        if not self.code:
            self.status = text

    def _run(self, server):
        try:
            sock = self._sock = _relay_connect(server, self._set_status, lambda: self._stop)
            if self._stop:
                sock.close()
                return
            sock.settimeout(WAKE_TIMEOUT)
            sock.sendall(b'{"op":"host"}\n')
            rd = LineReader(sock)
            msg = json.loads(rd.readline())
            if not msg.get("ok"):
                self.error = msg.get("err", "O servidor recusou a sala.")
                return
            self.code = str(msg["code"])
            self.status = "Aguardando o outro jogador..."
            sock.settimeout(60)
            while not self._stop:
                try:
                    msg = json.loads(rd.readline())
                except socket.timeout:
                    self.error = "Perdi a conexão com o servidor."
                    return
                if msg.get("op") == "paired":
                    self.peer = Peer(sock)
                    return
                if msg.get("ok") is False:
                    self.error = msg.get("err", "Sala encerrada.")
                    return
        except ConnectionError as ex:
            if not self._stop:
                self.error = str(ex) if str(ex) != "conexão fechada" else "O servidor encerrou a sala."
        except (OSError, ValueError):
            if not self._stop:
                self.error = "Falha na conexão com o servidor online."

    def close(self):
        self._stop = True
        if self.peer is None and self._sock is not None:      # se já pareou, o Peer é dono do socket
            try:
                self._sock.shutdown(socket.SHUT_RDWR)         # acorda a thread que está lendo
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass


class RelayJoin:
    """Entra numa sala pelo código (mesma interface do Connector)."""

    def __init__(self, server, code):
        self.peer = None
        self.error = None
        self.done = False
        self.status = "Conectando ao servidor... (na 1ª vez pode demorar até 1 min)"
        threading.Thread(target=self._run, args=(server, code.strip().upper()), daemon=True).start()

    def _set_status(self, text):
        self.status = text

    def _run(self, server, code):
        try:
            sock = _relay_connect(server, self._set_status)
            sock.settimeout(WAKE_TIMEOUT)
            sock.sendall((json.dumps({"op": "join", "code": code}) + "\n").encode())
            msg = json.loads(LineReader(sock).readline())
            if msg.get("ok"):
                self.peer = Peer(sock)
            else:
                sock.close()
                self.error = msg.get("err", "Não foi possível entrar na sala.")
        except ConnectionError as ex:
            self.error = str(ex) if str(ex) != "conexão fechada" else "O servidor fechou a conexão."
        except socket.timeout:
            self.error = "O servidor demorou demais para responder."
        except (OSError, ValueError):
            self.error = "Falha na conexão com o servidor online."
        self.done = True


def local_ip():
    """IP da rede local (o que o amigo usa se estiver no mesmo Wi-Fi / VPN)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))     # não envia nada; só descobre a interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
