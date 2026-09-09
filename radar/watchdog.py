"""Talk to systemd so a hung process gets restarted, not merely observed.

`Restart=always` only helps when the process *dies*. A poller stuck on a
half-open socket or a deadlocked thread is alive and useless. With
`Type=notify` and `WatchdogSec=` in the unit, systemd expects a heartbeat and
kills the service if one stops arriving. The heartbeat is sent from the poll
loop, so it stops precisely when polling does.

All of this is a no-op outside systemd (NOTIFY_SOCKET unset), so `./run.sh`
in a terminal behaves exactly as before.
"""

from __future__ import annotations

import os
import socket

_sock: socket.socket | None = None
_enabled = bool(os.environ.get("NOTIFY_SOCKET"))


def _send(message: str) -> bool:
    global _sock
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return False
    try:
        if _sock is None:
            _sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        # An abstract-namespace socket is announced with a leading '@'.
        target = "\0" + path[1:] if path.startswith("@") else path
        _sock.sendto(message.encode("utf-8"), target)
        return True
    except OSError:
        return False


def ready() -> None:
    _send("READY=1")


def heartbeat(status: str = "") -> None:
    msg = "WATCHDOG=1"
    if status:
        msg += "\nSTATUS=" + status.replace("\n", " ")[:200]
    _send(msg)


def status(text: str) -> None:
    _send("STATUS=" + text.replace("\n", " ")[:200])


def enabled() -> bool:
    return _enabled
