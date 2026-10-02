"""
Local Mobile Server for ZeroMeta PWA with Automatic HTTPS Tunnel.
Serves the mobile web app with a secure HTTPS link and QR Code
so Android Chrome accepts it with 100% security, green padlock,
and allows native 1-tap app installation.
"""
import os
import sys
import time
import socket
import http.server
import socketserver
import subprocess
import re

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False


def get_local_ip():
    """Finds the local network / Wi-Fi IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


_server_instance = None
_server_thread = None
_server_url = None
_server_port = 8080
_https_url = None
_cf_process = None


def get_server_url():
    global _server_url
    return _server_url


def ensure_background_server(port=8080) -> str:
    """Starts the local server in a background daemon thread."""
    global _server_instance, _server_thread, _server_url, _server_port
    if _server_url:
        return _server_url

    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mobile_pwa')
    if not os.path.exists(web_dir):
        return None

    local_ip = get_local_ip()
    socketserver.TCPServer.allow_reuse_address = True

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)
        def end_headers(self):
            self.send_header('Service-Worker-Allowed', '/')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            super().end_headers()
        def log_message(self, format, *args):
            pass

    for p in range(port, port + 15):
        try:
            httpd = socketserver.TCPServer(("", p), QuietHandler)
            _server_instance = httpd
            _server_port = p
            _server_url = f"http://{local_ip}:{p}"
            break
        except OSError:
            continue
    else:
        return None

    import threading
    _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
    _server_thread.start()
    return _server_url


def get_secure_https_url(port=None) -> str:
    """Creates a secure HTTPS tunnel via Cloudflare Tunnel for trusted Android Chrome SSL."""
    global _https_url, _cf_process, _server_port
    if _https_url:
        return _https_url

    p = port or _server_port or 8080
    cf_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cloudflared.exe')

    if not os.path.exists(cf_exe):
        return None

    try:
        proc = subprocess.Popen(
            [cf_exe, 'tunnel', '--url', f'http://127.0.0.1:{p}'],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        _cf_process = proc

        start = time.time()
        for line in proc.stderr:
            match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
            if match:
                _https_url = match.group(0)
                break
            if time.time() - start > 12:
                break
    except Exception as e:
        print("[Aviso] Erro ao iniciar túnel HTTPS:", e)

    return _https_url


def start_server(port=8080):
    local_url = ensure_background_server(port)
    if not local_url:
        print("[ERRO] Não foi possível iniciar o servidor local.")
        return

    print("Iniciando túnel seguro HTTPS para o Android...")
    https_url = get_secure_https_url(_server_port)

    active_url = https_url or local_url

    print("=" * 65)
    print("  🛡️  ZEROMETA AI - SERVIDOR MOBILE (ANDROID)")
    print("=" * 65)

    if https_url:
        print(f"\n🔒 CONEXÃO CRIPTOGRAFADA E SEGURA (HTTPS ATIVO):")
        print(f"👉 {https_url}")
        print("\n(O Chrome do celular NÃO mostrará aviso de segurança e permitirá a instalação)")
    else:
        print(f"\nConexão local: {local_url}")

    print("\nAponte a câmera do seu Android para o QR Code abaixo:\n")

    if HAS_QR:
        qr = qrcode.QRCode(border=1)
        qr.add_data(active_url)
        qr.make(fit=True)
        try:
            qr.print_ascii(invert=True)
        except Exception:
            pass

    print("\n" + "=" * 65)
    print(f"🔗 LINK SEGURO: {active_url}")
    print("=" * 65)
    print("\n💡 DICA NO ANDROID:")
    print("• Ao abrir no Chrome, toque no menu de 3 pontinhos e selecione:")
    print("  'Instalar aplicativo' ou 'Adicionar à tela inicial'.")
    print("• O app ficará instalado no seu celular e funcionará 100% OFFLINE!\n")
    print("Pressione Ctrl+C para encerrar o servidor quando terminar.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServidor mobile encerrado.")
        if _cf_process:
            try:
                _cf_process.terminate()
            except Exception:
                pass


if __name__ == '__main__':
    start_server()
