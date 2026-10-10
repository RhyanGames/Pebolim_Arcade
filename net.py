"""Rede do modo online (TCP + mensagens JSON, uma por linha). Só usa a biblioteca padrão.

Dois jeitos de jogar:
  * Sala por CÓDIGO (qualquer internet): os dois jogadores conectam no servidor relay (relay_server.py).
  * Endereço direto ip:porta (mesma rede / VPN): Listener (host) + Connector (cliente).
"""
import json
import queue
import re
import socket
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


def parse_server(addr, default_port=5555):
    host, port = addr.strip(), default_port
    if ":" in host:
        host, p = host.rsplit(":", 1)
        port = int(p)
    return host, port


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


def _relay_connect(server):
    try:
        host, port = parse_server(server)
    except ValueError:
        raise ConnectionError("Endereço do servidor online inválido.")
    try:
        return socket.create_connection((host, port), timeout=WAKE_TIMEOUT)
    except socket.gaierror:
        raise ConnectionError("Não achei o servidor online. Confira a internet.")
    except OSError:
        raise ConnectionError("Não consegui conectar ao servidor online.")


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

    def _run(self, server):
        try:
            sock = self._sock = _relay_connect(server)
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

    def _run(self, server, code):
        try:
            sock = _relay_connect(server)
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
