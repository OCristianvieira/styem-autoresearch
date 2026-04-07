"""
scrape_metrics.py — Coleta métricas do LinkedIn via Apify e atualiza Notion

Uso:
  python scripts/scrape_metrics.py --cliente powerd
  python scripts/scrape_metrics.py --cliente powerd --max-posts 30

Requer variáveis de ambiente:
  APIFY_TOKEN     — token da API do Apify
  NOTION_TOKEN    — token de integração do Notion
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# IDs das databases Notion
NOTION_DBS = {
    "powerd":        {"perf": "33b6588e-18c1-8181-a423-dc9273e0e9a8"},
    "fernando-maeda": {"perf": "33b6588e-18c1-8181-a423-dc9273e0e9a8"},
    "salva-tributo":  {"perf": "33b6588e-18c1-8181-a423-dc9273e0e9a8"},
    "sim-carreira":   {"perf": "33b6588e-18c1-8181-a423-dc9273e0e9a8"},
}

LINKEDIN_PROFILES = {
    "powerd":         "https://www.linkedin.com/in/cristianvieira-oficial/",
    "fernando-maeda": "https://www.linkedin.com/in/fernandomaeda/",
    "salva-tributo":  "https://www.linkedin.com/in/tiago-salvador/",
    "sim-carreira":   "https://www.linkedin.com/in/thiago-simcarreira/",
}

def apify_request(path, data=None, method="GET"):
    token = os.environ.get("APIFY_TOKEN", "")
    url = f"https://api.apify.com/v2{path}?token={token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                  headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def notion_request(path, data=None, method="POST"):
    token = os.environ.get("NOTION_TOKEN", "")
    url = f"https://api.notion.com/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def classify_hook(content):
    """Classifica tipo de hook baseado no texto do post."""
    content_lower = content.lower()[:200]
    if any(w in content_lower for w in ["internamente", "internally", "equipe da", "time da", "dentro da"]):
        return "insider"
    if any(w in content_lower for w in ["todo ceo", "todo mundo", "maioria", "ainda usa", "errado"]):
        return "contrarian"
    if any(w in content_lower for w in ["comenta ", "comenta aqui", "me manda no direct"]):
        return "cta_keyword"
    if any(w in content_lower for w in ["como ", "passo", "fase", "método", "aprendi", "ensinei"]):
        return "how_to"
    if any(w in content_lower for w in ["acabou de", "vazou", "lançou", "novo modelo", "bateu"]):
        return "newsjack"
    if any(w in content_lower for w in ["r$", "club", "acesso", "lista de espera"]):
        return "oferta"
    if any(w in content_lower for w in ["humor", "verdade ou mentira", "meme"]):
        return "humor"
    return "reveal"

def classify_format(item):
    if item.get("postVideo"):
        return "post+video"
    if item.get("document"):
        return "post+doc"
    if item.get("postImages") and len(item.get("postImages", [])) > 3:
        return "carrossel"
    return "post"

def post_exists_in_notion(db_id, linkedin_url):
    """Verifica se o post já existe no Notion pela URL."""
    data = {
        "filter": {
            "property": "LinkedIn URL",
            "url": {"equals": linkedin_url}
        }
    }
    r = notion_request(f"databases/{db_id}/query", data)
    return len(r.get("results", [])) > 0

def update_notion_post(db_id, linkedin_url, likes, comments, shares):
    """Atualiza métricas de um post existente."""
    data = {
        "filter": {
            "property": "LinkedIn URL",
            "url": {"equals": linkedin_url}
        }
    }
    r = notion_request(f"databases/{db_id}/query", data)
    if not r.get("results"):
        return False
    page_id = r["results"][0]["id"]
    notion_request(f"pages/{page_id}", {
        "properties": {
            "Likes": {"number": likes},
            "Comentários": {"number": comments},
            "Compartilhamentos": {"number": shares},
        }
    }, method="PATCH")
    return True

def create_notion_post(db_id, cliente, item):
    """Cria novo post no Notion."""
    eng = item.get("engagement", {})
    likes = eng.get("likes", 0)
    comments = eng.get("comments", 0)
    shares = eng.get("shares", 0)
    content = item.get("content", "")
    hook_type = classify_hook(content)
    fmt = classify_format(item)
    posted_at = item.get("postedAt", {}).get("date", datetime.now().isoformat())[:10]
    linkedin_url = item.get("linkedinUrl", "")
    title = content[:80].replace("\n", " ") if content else "Post sem texto"
    total_eng = likes + comments + shares
    impressions = item.get("engagement", {}).get("impressions", 0)
    taxa = f"{(total_eng/impressions*100):.1f}%" if impressions > 0 else "N/A"
    result = "keep" if likes >= 15 else "discard"

    data = {
        "parent": {"database_id": db_id},
        "properties": {
            "Post": {"title": [{"text": {"content": title}}]},
            "Cliente": {"select": {"name": cliente.replace("-", " ").title()}},
            "Plataforma": {"select": {"name": "LinkedIn"}},
            "Tipo de Hook": {"select": {"name": hook_type}},
            "Formato": {"select": {"name": fmt}},
            "Likes": {"number": likes},
            "Comentários": {"number": comments},
            "Compartilhamentos": {"number": shares},
            "Status": {"select": {"name": result}},
            "LinkedIn URL": {"url": linkedin_url},
            "Semana": {"rich_text": [{"text": {"content": "auto"}}]},
            "Data": {"date": {"start": posted_at}},
        }
    }
    notion_request("pages", data)
    return {"title": title, "likes": likes, "comments": comments, "shares": shares, "hook": hook_type}

def update_tsv(cliente, items):
    """Atualiza o performance.tsv com novos posts."""
    tsv_path = REPO_ROOT / "performance" / f"{cliente}.tsv"
    existing_urls = set()

    if tsv_path.exists():
        with open(tsv_path) as f:
            for line in f:
                parts = line.split("\t")
                # URL está nas notas ou no texto — verificar por conteúdo
                existing_urls.update(parts)

    new_lines = []
    hoje = datetime.now().strftime("%Y-%m-%d")

    for item in items:
        eng = item.get("engagement", {})
        likes = eng.get("likes", 0)
        comments = eng.get("comments", 0)
        shares = eng.get("shares", 0)
        content = item.get("content", "")[:60].replace("\t", " ").replace("\n", " ")
        hook_type = classify_hook(item.get("content", ""))
        fmt = classify_format(item)
        posted_at = item.get("postedAt", {}).get("date", hoje)[:10]
        total_eng = likes + comments + shares
        result = "keep" if likes >= 15 else "discard"
        new_lines.append(
            f"auto\t{posted_at}\tlinkedin\t{hook_type}\t{fmt}\tauto\t0\t{likes}\t{comments}\t{shares}\tN/A\t{result}\t{content}"
        )

    if new_lines:
        with open(tsv_path, "a") as f:
            f.write("\n".join(new_lines) + "\n")
        print(f"  TSV atualizado: {len(new_lines)} novos posts")

def run_apify_scraper(profile_url, max_posts):
    """Roda o scraper do Apify e retorna os itens."""
    print(f"  Rodando scraper Apify para {profile_url}...")

    # Iniciar run
    run = apify_request(
        "/acts/harvestapi~linkedin-profile-posts/runs",
        data={
            "targetUrls": [profile_url],
            "maxPosts": max_posts,
            "includeReposts": False,
            "scrapeReactions": False,
            "scrapeComments": False
        },
        method="POST"
    )
    run_id = run["data"]["id"]
    print(f"  Run iniciado: {run_id}")

    # Aguardar conclusão
    for _ in range(60):
        time.sleep(5)
        status = apify_request(f"/actor-runs/{run_id}")
        state = status["data"]["status"]
        if state == "SUCCEEDED":
            break
        elif state in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  ERRO: run terminou com status {state}")
            return []
        print(f"  Aguardando... ({state})")

    # Buscar dataset
    dataset_id = status["data"]["defaultDatasetId"]
    items_r = apify_request(f"/datasets/{dataset_id}/items?limit={max_posts}")
    return items_r.get("items", [])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", default="powerd", choices=list(LINKEDIN_PROFILES.keys()))
    parser.add_argument("--max-posts", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="Não salva no Notion/TSV")
    args = parser.parse_args()

    cliente = args.cliente
    profile_url = LINKEDIN_PROFILES[cliente]
    db_id = NOTION_DBS[cliente]["perf"]

    print(f"\n[scrape_metrics] Cliente: {cliente} | Perfil: {profile_url}")

    # Verificar tokens
    if not os.environ.get("APIFY_TOKEN"):
        print("ERRO: APIFY_TOKEN não definido. Adicione ao .env ou variável de ambiente.")
        sys.exit(1)
    if not os.environ.get("NOTION_TOKEN"):
        print("ERRO: NOTION_TOKEN não definido.")
        sys.exit(1)

    # Rodar scraper
    items = run_apify_scraper(profile_url, args.max_posts)
    print(f"\n  {len(items)} posts coletados.")

    if not items or args.dry_run:
        if args.dry_run:
            print("  [dry-run] Nada salvo.")
        return

    # Processar cada post
    novos = 0
    atualizados = 0
    for item in items:
        url = item.get("linkedinUrl", "")
        eng = item.get("engagement", {})
        likes = eng.get("likes", 0)
        comments = eng.get("comments", 0)
        shares = eng.get("shares", 0)

        if post_exists_in_notion(db_id, url):
            if update_notion_post(db_id, url, likes, comments, shares):
                atualizados += 1
        else:
            result = create_notion_post(db_id, cliente, item)
            print(f"  + {result['likes']}L {result['comments']}C | {result['hook']} | {result['title'][:50]}")
            novos += 1

    # Atualizar TSV
    update_tsv(cliente, items)

    print(f"\n  ✅ Notion: {novos} novos, {atualizados} atualizados")
    print(f"  ✅ TSV atualizado")
    print(f"  Concluído: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

if __name__ == "__main__":
    main()
