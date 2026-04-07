"""
linkedin_post.py — Publica posts aprovados do Notion no LinkedIn

Uso:
  python scripts/linkedin_post.py --dry-run       # simula sem publicar
  python scripts/linkedin_post.py                 # publica de fato
  python scripts/linkedin_post.py --today         # só posts com Data = hoje ou anterior

Requer variáveis de ambiente (no .env do styem primario):
  LINKEDIN_ACCESS_TOKEN  — obtido via linkedin_auth.py
  NOTION_TOKEN           — token de integração do Notion

Fluxo:
  1. Busca posts com Status = "Aprovado" no Calendário Editorial (Notion)
  2. Para cada post: faz upload de mídia se houver link Google Drive na prop "Mídia"
  3. Publica no LinkedIn via /rest/posts (com ou sem imagem/vídeo)
  4. Atualiza o registro no Notion: Status → "Publicado", salva URL do post

Mídia (opcional):
  - Na propriedade "Mídia" do post no Notion, cole o link de compartilhamento do Google Drive
  - O script converte para URL de download direto, baixa o arquivo e sobe pro LinkedIn
  - Suporta imagens (jpg, png, gif) e vídeos (mp4, mov)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import argparse
import re
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
CALENDARIO_DB = "33b6588e-18c1-81dd-9f1a-e991de7bd6eb"

NOTION_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
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


def linkedin_request(path, data=None, method="POST", extra_headers=None, raw_body=None):
    """Faz requisição autenticada à API do LinkedIn."""
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": "202504",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    if extra_headers:
        headers.update(extra_headers)

    if raw_body is not None:
        body = raw_body
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    else:
        body = None

    req = urllib.request.Request(
        f"https://api.linkedin.com{path}",
        data=body,
        method=method,
        headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            response_body = r.read()
            return r, response_body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise Exception(f"HTTP {e.code}: {err_body}")


def get_linkedin_author_urn():
    """Retorna o URN do usuário autenticado no LinkedIn."""
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {os.environ.get('LINKEDIN_ACCESS_TOKEN', '')}"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    sub = data.get("sub")
    if sub and sub.startswith("urn:li:"):
        return sub
    return f"urn:li:person:{sub}"


def fetch_approved_posts(only_today=False):
    """Busca posts com Status = 'Aprovado' no Calendário Editorial.

    Se only_today=True, filtra só posts cuja Data é hoje ou anterior
    (para uso pelo GitHub Action diário).
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if only_today:
        data = {
            "filter": {
                "and": [
                    {"property": "Status", "select": {"equals": "Aprovado"}},
                    {"property": "Data", "date": {"on_or_before": today}}
                ]
            },
            "sorts": [{"property": "Data", "direction": "ascending"}]
        }
    else:
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


def extract_media_url(page):
    """Extrai URL de mídia da propriedade 'Mídia' no Notion (link Google Drive ou URL direta)."""
    props = page.get("properties", {})

    for field in ["Mídia", "Media", "Imagem", "Vídeo", "Video"]:
        if field not in props:
            continue
        prop = props[field]

        # Propriedade tipo URL
        url = prop.get("url")
        if url:
            return url.strip()

        # Propriedade tipo rich_text (texto com URL colado)
        parts = prop.get("rich_text", [])
        text = "".join(p.get("plain_text", "") for p in parts).strip()
        if text:
            return text

    return None


def gdrive_to_download_url(url):
    """Converte link de compartilhamento do Google Drive para URL de download direto."""
    # Formato: https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"

    # Formato: https://drive.google.com/open?id=FILE_ID
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"

    # Já é URL direta
    return url


def download_media(url):
    """Baixa arquivo de mídia e retorna (bytes, content_type, filename)."""
    download_url = gdrive_to_download_url(url)

    req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        content_type = r.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        data = r.read()

    # Tentar inferir nome do arquivo pela URL ou content-type
    ext_map = {
        "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
        "image/webp": "webp", "video/mp4": "mp4", "video/quicktime": "mov"
    }
    ext = ext_map.get(content_type, "bin")
    filename = f"media.{ext}"

    return data, content_type, filename


def upload_image_to_linkedin(author_urn, image_data, content_type):
    """Faz upload de imagem no LinkedIn. Retorna o image URN."""
    # Passo 1: registrar o upload
    register_payload = {
        "initializeUploadRequest": {
            "owner": author_urn
        }
    }
    r, body = linkedin_request(
        "/rest/images?action=initializeUpload",
        data=register_payload,
        method="POST"
    )
    result = json.loads(body)
    upload_url = result["value"]["uploadUrl"]
    image_urn = result["value"]["image"]

    # Passo 2: enviar o arquivo binário
    upload_req = urllib.request.Request(
        upload_url,
        data=image_data,
        method="PUT",
        headers={"Content-Type": content_type}
    )
    with urllib.request.urlopen(upload_req, timeout=120):
        pass

    return image_urn


def upload_video_to_linkedin(author_urn, video_data, content_type):
    """Faz upload de vídeo no LinkedIn. Retorna o video URN."""
    file_size = len(video_data)

    # Passo 1: registrar o upload
    register_payload = {
        "initializeUploadRequest": {
            "owner": author_urn,
            "fileSizeBytes": file_size,
            "uploadCaptions": False,
            "uploadThumbnail": False
        }
    }
    r, body = linkedin_request(
        "/rest/videos?action=initializeUpload",
        data=register_payload,
        method="POST"
    )
    result = json.loads(body)
    upload_instructions = result["value"]["uploadInstructions"]
    video_urn = result["value"]["video"]

    # Passo 2: enviar o arquivo (pode ser multi-part para vídeos grandes)
    for instruction in upload_instructions:
        upload_url = instruction["uploadUrl"]
        first_byte = instruction.get("firstByte", 0)
        last_byte = instruction.get("lastByte", file_size - 1)
        chunk = video_data[first_byte:last_byte + 1]

        upload_req = urllib.request.Request(
            upload_url,
            data=chunk,
            method="PUT",
            headers={"Content-Type": content_type}
        )
        with urllib.request.urlopen(upload_req, timeout=300):
            pass

    # Passo 3: finalizar o upload
    finalize_payload = {
        "finalizeUploadRequest": {
            "video": video_urn,
            "uploadToken": result["value"].get("uploadToken", ""),
            "uploadedPartIds": [i.get("etag", "") for i in upload_instructions if i.get("etag")]
        }
    }
    linkedin_request(
        "/rest/videos?action=finalizeUpload",
        data=finalize_payload,
        method="POST"
    )

    # Aguardar processamento (até 60s)
    for _ in range(12):
        time.sleep(5)
        try:
            r, body = linkedin_request(f"/rest/videos/{urllib.parse.quote(video_urn, safe='')}", method="GET")
            status_data = json.loads(body)
            status = status_data.get("status")
            if status == "AVAILABLE":
                break
            if status in ("PROCESSING_FAILED",):
                raise Exception(f"Vídeo falhou no processamento: {status}")
        except Exception:
            pass

    return video_urn


def publish_to_linkedin(author_urn, text, media_url=None, dry_run=False):
    """Publica post no LinkedIn, com ou sem mídia. Retorna a URL do post."""

    media_urn = None
    media_type = None

    if media_url and not dry_run:
        print(f"    Baixando mídia: {media_url[:60]}...")
        try:
            media_data, content_type, filename = download_media(media_url)
            print(f"    Arquivo: {filename} ({len(media_data) // 1024}KB, {content_type})")

            if content_type.startswith("image/"):
                media_urn = upload_image_to_linkedin(author_urn, media_data, content_type)
                media_type = "image"
                print(f"    Imagem enviada: {media_urn}")
            elif content_type.startswith("video/"):
                media_urn = upload_video_to_linkedin(author_urn, media_data, content_type)
                media_type = "video"
                print(f"    Vídeo enviado: {media_urn}")
            else:
                print(f"    Tipo não suportado ({content_type}), publicando só texto.")
        except Exception as e:
            print(f"    Aviso: falha ao processar mídia ({e}). Publicando só texto.")

    # Montar payload
    rest_payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False
    }

    if media_urn and media_type == "image":
        rest_payload["content"] = {
            "media": {
                "id": media_urn
            }
        }
    elif media_urn and media_type == "video":
        rest_payload["content"] = {
            "media": {
                "id": media_urn
            }
        }

    if dry_run:
        has_media = f" + {media_type}" if media_url else ""
        print(f"\n[dry-run] Post{has_media}: {text[:120]}...")
        if media_url:
            print(f"    Mídia URL: {media_url[:80]}")
        return "https://www.linkedin.com/feed/ (dry-run)"

    body = json.dumps(rest_payload).encode()
    req = urllib.request.Request(
        "https://api.linkedin.com/rest/posts",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ.get('LINKEDIN_ACCESS_TOKEN', '')}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202504",
            "X-Restli-Protocol-Version": "2.0.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            post_id = r.headers.get("x-restli-id") or r.headers.get("X-RestLi-Id", "")
            if post_id:
                return f"https://www.linkedin.com/feed/update/{post_id}/"
            return "https://www.linkedin.com/feed/"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise Exception(f"HTTP {e.code}: {err_body}")


def mark_as_published(page_id, post_url):
    """Atualiza o registro no Notion: Status → Publicado, salva URL."""
    notion_request(f"pages/{page_id}", {
        "properties": {
            "Status": {"select": {"name": "Publicado"}},
            "LinkedIn URL": {"url": post_url},
            "Data de Publicação": {"date": {"start": datetime.now().isoformat()[:10]}}
        }
    }, method="PATCH")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Simula sem publicar no LinkedIn nem alterar o Notion")
    parser.add_argument("--today", action="store_true",
                        help="Publica só posts com Data = hoje ou anterior (usado pelo GitHub Action)")
    parser.add_argument("--one", action="store_true",
                        help="Publica só 1 post por execução (o mais antigo aprovado). Usar junto com --today.")
    args = parser.parse_args()

    # Validar tokens
    if not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        print("ERRO: LINKEDIN_ACCESS_TOKEN não encontrado.")
        print("Execute primeiro: python scripts/linkedin_auth.py")
        sys.exit(1)

    if not os.environ.get("NOTION_TOKEN"):
        print("ERRO: NOTION_TOKEN não encontrado no .env")
        sys.exit(1)

    modo_hoje = args.today
    print("\n[linkedin_post] Buscando posts aprovados no Notion...")
    if modo_hoje:
        print("  Modo: --today (só posts com Data = hoje ou anterior)")
    posts = fetch_approved_posts(only_today=modo_hoje)

    if not posts:
        print("Nenhum post com status 'Aprovado' encontrado.")
        return

    total = len(posts)
    if args.one:
        posts = posts[:1]
        print(f"Modo --one: publicando 1 de {total} aprovado(s) na fila.\n")
    else:
        print(f"{total} post(s) aprovado(s) encontrado(s).\n")

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
        media_url = extract_media_url(page)

        if not text:
            print(f"  ⚠ '{titulo}' — sem conteúdo de texto encontrado. Pulando.")
            erros += 1
            continue

        has_media = f" [+ mídia]" if media_url else ""
        print(f"  → '{titulo}' ({len(text)} chars){has_media}")

        if args.dry_run:
            publish_to_linkedin(author_urn, text, media_url=media_url, dry_run=True)
            print(f"    [dry-run] Não publicado.\n")
            continue

        try:
            post_url = publish_to_linkedin(author_urn, text, media_url=media_url, dry_run=False)
            mark_as_published(page_id, post_url)
            print(f"    Publicado: {post_url}\n")
            publicados += 1
        except Exception as e:
            print(f"    Erro: {e}\n")
            erros += 1

    if not args.dry_run:
        print(f"Concluído: {publicados} publicado(s), {erros} erro(s).")
    else:
        print(f"[dry-run] {len(posts)} post(s) simulado(s). Nada foi enviado.")


if __name__ == "__main__":
    main()
