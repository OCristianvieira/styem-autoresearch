"""
linkedin_post.py — Publica posts aprovados do Notion no LinkedIn

Uso:
  python scripts/linkedin_post.py --dry-run       # simula sem publicar
  python scripts/linkedin_post.py                 # publica de fato

Requer variáveis de ambiente (no .env do styem primario):
  LINKEDIN_ACCESS_TOKEN  — obtido via linkedin_auth.py
  NOTION_TOKEN           — token de integração do Notion

Fluxo:
  1. Busca posts com Status = "Aprovado" no Calendário Editorial (Notion)
  2. Para cada post: publica no LinkedIn via API v2
  3. Atualiza o registro no Notion: Status → "Publicado", salva URL do post
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import argparse
from datetime import datetime
from pathlib import Path

# Carregar .env automaticamente
ENV_PATH = Path(__file__).parent.parent.parent.parent / "styem primario" / ".env"
if not ENV_PATH.exists():
    ENV_PATH = Path.home() / "styem primario" / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ID da database Calendário Editorial no Notion
CALENDARIO_DB = "33b6588e-18c1-81ac-a8ed-e9e7ca7b8eff"

NOTION_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

LINKEDIN_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('LINKEDIN_ACCESS_TOKEN', '')}",
    "Content-Type": "application/json",
    "X-Restli-Protocol-Version": "2.0.0"
}


def notion_request(path, data=None, method="POST"):
    url = f"https://api.notion.com/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        **NOTION_HEADERS,
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_linkedin_author_urn():
    """Retorna o URN do usuário autenticado no LinkedIn."""
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {os.environ.get('LINKEDIN_ACCESS_TOKEN', '')}"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    sub = data.get("sub")  # ex: "urn:li:person:XXXXXXXX" ou só o ID
    if sub and sub.startswith("urn:li:"):
        return sub
    return f"urn:li:person:{sub}"


def fetch_approved_posts():
    """Busca posts com Status = 'Aprovado' no Calendário Editorial."""
    data = {
        "filter": {
            "property": "Status",
            "select": {"equals": "Aprovado"}
        },
        "sorts": [{"property": "Data", "direction": "ascending"}]
    }
    r = notion_request(f"databases/{CALENDARIO_DB}/query", data)
    return r.get("results", [])


def extract_post_content(page):
    """Extrai o texto do post a partir das propriedades do Notion."""
    props = page.get("properties", {})

    for field in ["Texto do Post", "Copy", "Texto", "Conteúdo"]:
        if field in props:
            prop = props[field]
            parts = prop.get("rich_text", [])
            text = "".join(p.get("plain_text", "") for p in parts)
            if text.strip():
                return text.strip()

    return None


def get_scheduled_time(page):
    """Retorna datetime para publicação: data do Notion às 18h BRT (21h UTC).
    Se a data já passou ou não existe, retorna None (publicar imediatamente)."""
    props = page.get("properties", {})
    date_prop = props.get("Data", {}).get("date")
    if not date_prop:
        return None

    date_str = date_prop.get("start", "")[:10]  # "2026-04-08"
    if not date_str:
        return None

    # 18h BRT = 21h UTC
    scheduled = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=21, minute=0, second=0)
    now_utc = datetime.utcnow()

    # Se já passou, publicar imediatamente
    if scheduled <= now_utc:
        return None

    # LinkedIn espera Unix timestamp em milissegundos
    import calendar
    return calendar.timegm(scheduled.timetuple()) * 1000


def publish_to_linkedin(author_urn, text, scheduled_at_ms=None, dry_run=False):
    """Publica ou agenda um post no LinkedIn. Retorna a URL do post."""
    if scheduled_at_ms:
        lifecycle = "DRAFT"
        payload = {
            "author": author_urn,
            "lifecycleState": lifecycle,
            "scheduledPublishTime": scheduled_at_ms,
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
    else:
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

    if dry_run:
        modo = "AGENDADO" if scheduled_at_ms else "IMEDIATO"
        print(f"\n[dry-run] Modo: {modo}")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:500])
        return "https://www.linkedin.com/feed/ (dry-run)"

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/ugcPosts",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ.get('LINKEDIN_ACCESS_TOKEN', '')}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        post_id = r.headers.get("x-restli-id") or r.headers.get("X-RestLi-Id", "")
        # URL canônica do post
        if post_id:
            return f"https://www.linkedin.com/feed/update/{post_id}/"
        return "https://www.linkedin.com/feed/"


def mark_as_published(page_id, post_url):
    """Atualiza o registro no Notion: Status → Publicado, salva URL."""
    notion_request(f"pages/{page_id}", {
        "properties": {
            "Status": {"status": {"name": "Publicado"}},
            "LinkedIn URL": {"url": post_url},
            "Data de Publicação": {"date": {"start": datetime.now().isoformat()[:10]}}
        }
    }, method="PATCH")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Simula sem publicar no LinkedIn nem alterar o Notion")
    args = parser.parse_args()

    # Validar tokens
    if not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        print("ERRO: LINKEDIN_ACCESS_TOKEN não encontrado.")
        print("Execute primeiro: python scripts/linkedin_auth.py")
        sys.exit(1)

    if not os.environ.get("NOTION_TOKEN"):
        print("ERRO: NOTION_TOKEN não encontrado no .env")
        sys.exit(1)

    print("\n[linkedin_post] Buscando posts aprovados no Notion...")
    posts = fetch_approved_posts()

    if not posts:
        print("Nenhum post com status 'Aprovado' encontrado.")
        return

    print(f"{len(posts)} post(s) aprovado(s) encontrado(s).\n")

    # Buscar URN do autor uma vez
    if not args.dry_run:
        try:
            author_urn = get_linkedin_author_urn()
            print(f"Publicando como: {author_urn}\n")
        except Exception as e:
            print(f"ERRO ao obter autor LinkedIn: {e}")
            sys.exit(1)
    else:
        author_urn = "urn:li:person:DRY_RUN"

    publicados = 0
    erros = 0

    for page in posts:
        page_id = page["id"]
        props = page.get("properties", {})

        # Título para display
        titulo_prop = props.get("Título") or props.get("Post") or {}
        titulo_parts = titulo_prop.get("title", [])
        titulo = "".join(p.get("plain_text", "") for p in titulo_parts)[:60] or "(sem título)"

        text = extract_post_content(page)

        if not text:
            print(f"  ⚠ '{titulo}' — sem conteúdo de texto encontrado. Pulando.")
            erros += 1
            continue

        print(f"  → '{titulo}' ({len(text)} chars)")

        if args.dry_run:
            print(f"    Prévia: {text[:120]}...")
            print(f"    [dry-run] Não publicado.\n")
            continue

        try:
            scheduled_at_ms = get_scheduled_time(page)
            post_url = publish_to_linkedin(author_urn, text, scheduled_at_ms=scheduled_at_ms, dry_run=False)
            mark_as_published(page_id, post_url)
            if scheduled_at_ms:
                from datetime import timezone
                import calendar
                ts = scheduled_at_ms // 1000
                dt = datetime.utcfromtimestamp(ts)
                print(f"    📅 Agendado para {dt.strftime('%d/%m/%Y às 18h BRT')}: {post_url}\n")
            else:
                print(f"    ✅ Publicado imediatamente: {post_url}\n")
            publicados += 1
        except Exception as e:
            print(f"    ✗ Erro: {e}\n")
            erros += 1

    if not args.dry_run:
        print(f"Concluído: {publicados} publicado(s), {erros} erro(s).")
    else:
        print(f"[dry-run] {len(posts)} post(s) simulado(s). Nada foi enviado.")


if __name__ == "__main__":
    main()
