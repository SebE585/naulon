#!/usr/bin/env python3
"""Measure the byte cost of a TLS handshake, full and resumed.

A device that opens a TLS connection for every transmission pays a handshake
every time, and that handshake can dwarf the payload. The model refuses to
price such a device until these numbers exist, so here they are measured rather
than guessed.

No packet capture, no root, no telematics hardware: a TLS handshake is a TLS
handshake. `ssl.SSLContext.wrap_bio` drives it through two memory buffers, so
every byte crossing the wire can be counted exactly, against any public TLS
server. Anyone can rerun this.

    python scripts/measure_tls_handshake.py
"""

from __future__ import annotations

import argparse
import socket
import ssl
import statistics
from dataclasses import dataclass

# Public endpoints, deliberately varied: certificate chain size is the dominant
# term in a full handshake, and it differs a lot between issuers.
DEFAULT_HOSTS = [
    "www.rfc-editor.org",
    "datatracker.ietf.org",
    "www.iana.org",
    "example.com",
]
PORT = 443
TIMEOUT_S = 10

# One context for the whole run: a session harvested under one SSLContext
# cannot be resumed under another, so sharing it is what makes the resumed
# measurement possible at all.
CONTEXT = ssl.create_default_context()


@dataclass
class Handshake:
    host: str
    version: str
    sent: int
    received: int
    resumed: bool

    @property
    def total(self) -> int:
        return self.sent + self.received


def _pump(sock: socket.socket, sslobj: ssl.SSLObject,
          incoming: ssl.MemoryBIO, outgoing: ssl.MemoryBIO) -> tuple[int, int]:
    """Drive a handshake through memory buffers, counting bytes both ways."""
    sent = received = 0
    while True:
        try:
            sslobj.do_handshake()
            break
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            pass

        outbound = outgoing.read()
        if outbound:
            sock.sendall(outbound)
            sent += len(outbound)

        inbound = sock.recv(65536)
        if not inbound:
            raise ConnectionError("peer closed during handshake")
        received += len(inbound)
        incoming.write(inbound)

    # Anything the handshake still owes the peer (TLS 1.3 client Finished).
    outbound = outgoing.read()
    if outbound:
        sock.sendall(outbound)
        sent += len(outbound)
    return sent, received


def handshake(host: str, session: ssl.SSLSession | None = None) -> Handshake:
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = CONTEXT.wrap_bio(incoming, outgoing, server_hostname=host, session=session)

    with socket.create_connection((host, PORT), timeout=TIMEOUT_S) as sock:
        sent, received = _pump(sock, sslobj, incoming, outgoing)

        return Handshake(
            host, sslobj.version() or "?", sent, received, bool(sslobj.session_reused)
        )


def harvest_session(host: str) -> ssl.SSLSession | None:
    """Open an ordinary connection just to collect a resumable session.

    In TLS 1.3 the server sends its session ticket *after* the handshake
    completes, so a resumable session only exists once real application data
    has flowed. Doing this on a separate, unmeasured connection keeps the
    measurement itself clean.
    """
    try:
        with socket.create_connection((host, PORT), timeout=TIMEOUT_S) as raw:
            with CONTEXT.wrap_socket(raw, server_hostname=host) as tls:
                tls.sendall(
                    f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
                )
                tls.recv(65536)
                return tls.session
    except (ssl.SSLError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hosts", nargs="*", default=DEFAULT_HOSTS)
    args = parser.parse_args()

    full: list[Handshake] = []
    resumed: list[Handshake] = []

    print(f"{'host':<26}{'version':>10}{'sent':>8}{'recv':>8}{'total':>9}")
    print("-" * 61)
    for host in args.hosts:
        try:
            first = handshake(host)
        except Exception as exc:                                  # noqa: BLE001
            print(f"{host:<26}{'failed':>10}   {exc}")
            continue
        full.append(first)
        print(f"{first.host:<26}{first.version:>10}{first.sent:>8}{first.received:>8}{first.total:>9}")

        session = harvest_session(host)
        if session is None:
            continue
        try:
            second = handshake(host, session=session)
        except Exception:                                         # noqa: BLE001
            continue
        if second.resumed:
            resumed.append(second)
            print(f"{'  resumed':<26}{second.version:>10}{second.sent:>8}"
                  f"{second.received:>8}{second.total:>9}")

    print()
    if full:
        totals = [h.total for h in full]
        print(f"full handshake     median {int(statistics.median(totals)):>6} B"
              f"   range {min(totals)}-{max(totals)} B   n={len(totals)}")
    if resumed:
        totals = [h.total for h in resumed]
        print(f"resumed handshake  median {int(statistics.median(totals)):>6} B"
              f"   range {min(totals)}-{max(totals)} B   n={len(totals)}")
    else:
        print("resumed handshake  no sample obtained")

    print()
    print("The full handshake is dominated by the server's certificate chain, so")
    print("it varies by issuer far more than by client. A device that reconnects")
    print("for every transmission pays this every time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
