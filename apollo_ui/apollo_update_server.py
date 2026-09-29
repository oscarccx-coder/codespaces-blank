from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import argparse
import functools


def serve(root, host="0.0.0.0", port=8765):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer((host, int(port)), handler)
    print(f"Apollo update server: http://{host}:{port}")
    print(f"Serving: {root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve signed Apollo releases over LAN/HTTP.")
    parser.add_argument("--root", default="storage/updates/server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.root, args.host, args.port)
