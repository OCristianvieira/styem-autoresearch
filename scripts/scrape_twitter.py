"""
scrape_twitter.py — Coleta tweets virais de IA das últimas 24h e salva no Notion como ideias

Uso:
  python scripts/scrape_twitter.py
  python scripts/scrape_twitter.py --dry-run    # imprime sem salvar no Notion
  python scripts/scrape_twitter.py --max 30     # número de tweets por busca (default: 20)

Requer variáveis de ambiente:
  APIFY_TOKEN   — token do Apify
  NOTION_TOKEN  — token do Notion

Busca tweets das últimas 24h nas categorias:
  - Urgência / breaking (novos modelos, lançamentos, vazamentos)
  - Ferramentas práticas de IA
  - Repositórios com potencial de lead magnet
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Carregar .env
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

# Buscas: (label, searchTerm, categoria)
# Filtra só tweets com bom engajamento (min_faves=50) para não poluir
SEARCHES = [
    (
        "breaking",
        '("new model" OR "just released" OR "just launched" OR "leaked" OR "just dropped") (AI OR "artificial intelligence" OR Claude OR GPT OR Gemini OR "open source") min_faves:100 -filter:replies lang:en',
        "urgencia"
    ),
    (
        "ferramentas",
        '("AI tool" OR "just built" OR "you can now" OR "free tool" OR "open source tool") (AI OR automation OR agent OR workflow) min_faves:80 -filter:replies lang:en',
        "ferramenta"
    ),
    (
        "repositórios",
        '(github OR repo OR repository) (AI OR "machine learning" OR agent OR LLM) ("star" OR "fork" OR "just released") min_faves:100 -filter:replies lang:en',
        "repositorio"
    ),
    (
        "deals",
        '("for free" OR "free access" OR "lifetime deal" OR "limited time" OR "open beta") (AI OR GPT OR Claude OR Gemini) min_faves:80 -filter:replies lang:en',
        "deal"
    ),
]

MIN_LIKES_TO_SAVE = 50  # Só salva no Notion se tiver pelo menos X likes


def apify_request(path, data=None, method="GET"):
    token = os.environ.get("APIFY_TOKEN", "")
    url = f"https://api.apify.com/v2{path}?token={token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json"} if body else {}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
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


def run_twitter_scraper(search_term, max_items):
    """Roda o scraper do Apify e retorna tweets."""
    # Data de 24h atrás em formato UTC
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d_%H:%M:%S_UTC")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S_UTC")

    full_query = f"{search_term} since:{since} until:{until}"

    run = apify_request(
        "/acts/kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest/runs",
        data={
            "twitterContent": full_query,
            "maxItems": max_items,
            "queryType": "Top",
            "lang": "en",
        },
        method="POST"
    )

    run_id = run["data"]["id"]

    # Aguardar conclusão
    for _ in range(60):
        time.sleep(5)
        status = apify_request(f"/actor-runs/{run_id}")
        state = status["data"]["status"]
        if state == "SUCCEEDED":
            break
        elif state in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"    ERRO: run terminou com status {state}")
            return []
        print(f"    Aguardando... ({state})")

    dataset_id = status["data"]["defaultDatasetId"]
    result = apify_request(f"/datasets/{dataset_id}/items?limit={max_items}")
    return result.get("items", [])


def tweet_already_saved(tweet_url):
    """Verifica se o tweet já existe no Notion."""
    data = {
        "filter": {
            "property": "LinkedIn URL",
            "url": {"equals": tweet_url}
        }
    }
    r = notion_request(f"databases/{CALENDARIO_DB}/query", data)
    return len(r.get("results", [])) > 0


def save_idea_to_notion(tweet, categoria):
    """Salva tweet como ideia no Calendário Editorial do Notion."""
    text = tweet.get("text", "")
    author = tweet.get("author", {}).get("userName", "") or tweet.get("userName", "")
    likes = tweet.get("likeCount", 0) or tweet.get("favorite_count", 0) or 0
    retweets = tweet.get("retweetCount", 0) or tweet.get("retweet_count", 0) or 0
    tweet_url = tweet.get("url", "") or tweet.get("tweetUrl", "")

    titulo = f"[{categoria.upper()}] @{author}: {text[:60].replace(chr(10), ' ')}"

    angulo = f"Tweet viral com {likes} likes e {retweets} RTs. Adaptar para o posicionamento Powerd/IA nos negócios."

    data = {
        "parent": {"database_id": CALENDARIO_DB},
        "properties": {
            "Título": {"title": [{"text": {"content": titulo}}]},
            "Status": {"status": {"name": "Ideia"}},
            "LinkedIn URL": {"url": tweet_url if tweet_url else None},
            "Data": {"date": {"start": datetime.now().isoformat()[:10]}},
            "Notas": {"rich_text": [{"text": {"content": f"{text[:300]}\n\n---\nÂngulo sugerido: {angulo}"}}]},
        }
    }

    # Remover URL se vazia (Notion não aceita url nulo)
    if not tweet_url:
        del data["properties"]["LinkedIn URL"]

    notion_request("pages", data)
    return titulo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Não salva no Notion")
    parser.add_argument("--max", type=int, default=20, help="Tweets por busca (default: 20)")
    args = parser.parse_args()

    if not os.environ.get("APIFY_TOKEN"):
        print("ERRO: APIFY_TOKEN não definido.")
        sys.exit(1)
    if not os.environ.get("NOTION_TOKEN") and not args.dry_run:
        print("ERRO: NOTION_TOKEN não definido.")
        sys.exit(1)

    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n[scrape_twitter] {hoje} — coletando sinais de IA das últimas 24h\n")

    total_salvos = 0
    total_ignorados = 0

    for label, search_term, categoria in SEARCHES:
        print(f"  [{label}] Buscando...")

        try:
            tweets = run_twitter_scraper(search_term, args.max)
        except Exception as e:
            print(f"    ERRO: {e}")
            continue

        print(f"    {len(tweets)} tweets coletados")

        # Filtrar por engajamento mínimo e ordenar por likes
        tweets_filtrados = [
            t for t in tweets
            if (t.get("likeCount", 0) or t.get("favorite_count", 0) or 0) >= MIN_LIKES_TO_SAVE
        ]
        tweets_filtrados.sort(
            key=lambda t: (t.get("likeCount", 0) or t.get("favorite_count", 0) or 0),
            reverse=True
        )

        # Pegar top 5 por categoria
        for tweet in tweets_filtrados[:5]:
            likes = tweet.get("likeCount", 0) or tweet.get("favorite_count", 0) or 0
            author = tweet.get("author", {}).get("userName", "") or tweet.get("userName", "")
            text = tweet.get("text", "")[:80].replace("\n", " ")
            tweet_url = tweet.get("url", "") or tweet.get("tweetUrl", "")

            if args.dry_run:
                print(f"    [{likes}L] @{author}: {text}...")
                total_salvos += 1
                continue

            # Verificar duplicata
            if tweet_url and tweet_already_saved(tweet_url):
                total_ignorados += 1
                continue

            try:
                titulo = save_idea_to_notion(tweet, categoria)
                print(f"    + [{likes}L] {titulo[:70]}")
                total_salvos += 1
            except Exception as e:
                print(f"    ERRO ao salvar: {e}")
                total_ignorados += 1

        print()

    if args.dry_run:
        print(f"[dry-run] {total_salvos} tweets encontrados. Nada salvo no Notion.")
    else:
        print(f"✅ {total_salvos} ideias salvas no Notion | {total_ignorados} ignoradas (duplicatas ou erro)")
        print(f"Acesse o Notion para revisar e aprovar as ideias.")


if __name__ == "__main__":
    main()
