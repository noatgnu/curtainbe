#!/usr/bin/env python3
"""Publishes curtainptm.local via mDNS using zeroconf."""
import socket
import time
from zeroconf import ServiceInfo, Zeroconf


def get_local_ip() -> str:
    """Return the machine's primary outbound IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    """Register and keep alive the curtainptm.local mDNS service record."""
    ip = get_local_ip()
    zc = Zeroconf()
    info = ServiceInfo(
        "_http._tcp.local.",
        "CurtainPTM._http._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=80,
        server="curtainptm.local.",
    )
    zc.register_service(info)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        zc.unregister_service(info)
        zc.close()


if __name__ == "__main__":
    main()
