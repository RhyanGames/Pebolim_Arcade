"""Rede do modo online (TCP + mensagens JSON, uma por linha). Só usa a biblioteca padrão."""
import json
import queue
import socket
import threading
import time

from settings import NET_TIMEOUT


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


class Listener:
    """Host: espera UM jogador entrar."""

    def __init__(self, port):
        self.error = None
        self.peer = None
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
    """Cliente: conecta em segundo plano (para o jogo não travar)."""

    def __init__(self, addr, default_port):
        self.peer = None
        self.error = None
        self.done = False
        host, port = addr.strip(), default_port
        if ":" in host:
            host, p = host.rsplit(":", 1)
            try:
                port = int(p)
            except ValueError:
                self.error, self.done = "Endereço inválido (use ip:porta)", True
                return
        if not host:
            self.error, self.done = "Digite o endereço do host", True
            return
        threading.Thread(target=self._run, args=(host, port), daemon=True).start()

    def _run(self, host, port):
        try:
            sock = socket.create_connection((host, port), timeout=6)
            self.peer = Peer(sock)
        except OSError as ex:
            self.error = f"Não conectou: {ex}"
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
