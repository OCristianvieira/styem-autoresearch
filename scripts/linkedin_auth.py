"""
linkedin_auth.py — Autenticação OAuth do LinkedIn (roda UMA VEZ)

Uso:
  python scripts/linkedin_auth.py

Abre o navegador, você autoriza o app, e salva o access_token no .env.
Após isso, use linkedin_post.py para publicar.
"""

import os
import sys
import json
import webbrowser
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "w_member_social openid profile"

ENV_PATH = Path(__file__).parent.parent.parent / "styem primario" / ".env"
# Fallback para quando rodar do repo
if not ENV_PATH.exists():
    ENV_PATH = Path.home() / "styem primario" / ".env"

# Carregar .env
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Autorizado! Pode fechar esta aba.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>Erro: code nao recebido.</h2>")

    def log_message(self, format, *args):
        pass  # silenciar logs do servidor

def get_access_token(code):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()

    req = urllib.request.Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def save_token_to_env(token):
    """Adiciona ou atualiza LINKEDIN_ACCESS_TOKEN no .env"""
    env_path = ENV_PATH
    if not env_path.exists():
        print(f"AVISO: .env não encontrado em {env_path}")
        print(f"Token: {token}")
        return

    content = env_path.read_text()
    line = f"LINKEDIN_ACCESS_TOKEN={token}"

    if "LINKEDIN_ACCESS_TOKEN=" in content:
        lines = content.splitlines()
        lines = [line if l.startswith("LINKEDIN_ACCESS_TOKEN=") else l for l in lines]
        env_path.write_text("\n".join(lines) + "\n")
    else:
        with open(env_path, "a") as f:
            f.write(f"\n{line}\n")

    print(f"✅ Token salvo em {env_path}")

def main():
    # Montar URL de autorização
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": "styem_auth"
    })
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{params}"

    print("\n[LinkedIn Auth]")
    print("Abrindo navegador para autorização...")
    print(f"\nSe não abrir automaticamente, acesse:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Iniciar servidor local para capturar callback
    print("Aguardando callback em http://localhost:8080/callback ...")
    server = HTTPServer(("localhost", 8080), CallbackHandler)

    # Aguarda até receber o code (ignora requests sem code, ex: favicon)
    while not auth_code:
        server.handle_request()

    if not auth_code:
        print("ERRO: Não foi possível capturar o código de autorização.")
        sys.exit(1)

    print(f"✓ Código recebido. Trocando por access token...")

    token_data = get_access_token(auth_code)
    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in", 0)

    if not access_token:
        print(f"ERRO: {token_data}")
        sys.exit(1)

    print(f"✓ Access token obtido. Expira em {expires_in // 86400} dias.")
    save_token_to_env(access_token)
    print("\n✅ Autenticação concluída. Agora use linkedin_post.py para publicar.")

if __name__ == "__main__":
    main()
