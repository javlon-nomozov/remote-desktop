"""Tarmoq transporti: to'g'ridan-to'g'ri (StreamServer) va relay (RelayHost, unique kod)."""
from .relay_client import RelayHost
from .stream_server import StreamServer

__all__ = ["StreamServer", "RelayHost"]
