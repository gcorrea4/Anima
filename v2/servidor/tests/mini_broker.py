"""
Mini-broker MQTT 3.1.1 SÓ PARA TESTES (QoS 0/1 sem persistência, sem autenticação, sem retain).
Permite testar o fluxo ponta a ponta localmente, sem rede e sem instalar mosquitto.
Não use fora dos testes.
"""
import asyncio
import threading


def _rem_len(n):
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _casa(filtro, topico):
    f, t = filtro.split("/"), topico.split("/")
    for i, parte in enumerate(f):
        if parte == "#":
            return True
        if i >= len(t) or (parte != "+" and parte != t[i]):
            return False
    return len(f) == len(t)


class MiniBroker:
    def __init__(self, host="127.0.0.1"):
        self.host, self.port = host, 0
        self._clientes = []          # (writer, lista_filtros)
        self.filtros_ativos = set()  # para os testes saberem quando alguém assinou
        self.mensagens = []          # (topico, payload) tudo que passou pelo broker
        self._loop = asyncio.new_event_loop()
        self._pronto = threading.Event()
        self._thread = threading.Thread(target=self._rodar, daemon=True)

    def start(self):
        self._thread.start()
        self._pronto.wait(5)
        return self

    def stop(self):
        def parar():
            self._server.close()
            for w, _ in list(self._clientes):
                w.close()
            for t in asyncio.all_tasks(self._loop):
                t.cancel()
            self._loop.call_later(0.2, self._loop.stop)
        self._loop.call_soon_threadsafe(parar)
        self._thread.join(3)
        if not self._thread.is_alive() and not self._loop.is_running():
            self._loop.close()

    def _rodar(self):
        asyncio.set_event_loop(self._loop)
        self._server = self._loop.run_until_complete(asyncio.start_server(self._cliente, self.host, 0))
        self.port = self._server.sockets[0].getsockname()[1]
        self._pronto.set()
        self._loop.run_forever()

    async def _ler_pacote(self, r):
        b1 = (await r.readexactly(1))[0]
        mult, n = 1, 0
        while True:
            b = (await r.readexactly(1))[0]
            n += (b & 0x7F) * mult
            mult *= 128
            if not b & 0x80:
                break
        return b1, (await r.readexactly(n) if n else b"")

    async def _cliente(self, r, w):
        reg = (w, [])
        self._clientes.append(reg)
        try:
            while True:
                b1, corpo = await self._ler_pacote(r)
                tipo = b1 >> 4
                if tipo == 1:                      # CONNECT
                    w.write(b"\x20\x02\x00\x00")
                elif tipo == 3:                    # PUBLISH
                    qos = (b1 >> 1) & 3
                    tl = int.from_bytes(corpo[:2], "big")
                    topico = corpo[2:2 + tl].decode()
                    pos = 2 + tl
                    if qos:
                        w.write(b"\x40\x02" + corpo[pos:pos + 2])
                        pos += 2
                    payload = corpo[pos:]
                    self.mensagens.append((topico, payload))
                    pkt_corpo = len(topico.encode()).to_bytes(2, "big") + topico.encode() + payload
                    for cw, filtros in self._clientes:
                        if any(_casa(f, topico) for f in filtros):
                            cw.write(b"\x30" + _rem_len(len(pkt_corpo)) + pkt_corpo)
                elif tipo == 8:                    # SUBSCRIBE
                    pid, pos, n = corpo[:2], 2, 0
                    while pos < len(corpo):
                        tl = int.from_bytes(corpo[pos:pos + 2], "big")
                        f = corpo[pos + 2:pos + 2 + tl].decode()
                        reg[1].append(f)
                        self.filtros_ativos.add(f)
                        pos += 2 + tl + 1
                        n += 1
                    w.write(b"\x90" + _rem_len(2 + n) + pid + b"\x00" * n)
                elif tipo == 10:                   # UNSUBSCRIBE
                    w.write(b"\xb0\x02" + corpo[:2])
                elif tipo == 12:                   # PINGREQ
                    w.write(b"\xd0\x00")
                elif tipo == 14:                   # DISCONNECT
                    break
                await w.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._clientes.remove(reg)
            w.close()
