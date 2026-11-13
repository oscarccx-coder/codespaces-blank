"""Small shared validation helpers; imports no optional AI dependencies."""
import ipaddress
import socket
from urllib.parse import urlsplit


def public_url(value, *, resolve=True):
    value = str(value).strip()
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('A public HTTP(S) URL without credentials is required')
    host = parts.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise PermissionError('Private destinations are blocked')
    try: addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)] if resolve else []
    if any(not addr.is_global for addr in addresses):
        raise PermissionError('Private destinations are blocked')
    return value


def local_endpoint(value):
    parts = urlsplit(str(value))
    if parts.scheme not in {'http', 'https'} or parts.hostname not in {'localhost', '127.0.0.1', '::1'} or parts.username or parts.password:
        raise PermissionError('Select a loopback local model endpoint')
    return str(value).rstrip('/')
