# styem-autoresearch

Loop de melhoria contínua de instaladores de conteúdo — Styem.

Inspirado no [autoresearch do Karpathy](https://github.com/karpathy/autoresearch): um arquivo evolui a cada ciclo, guiado por dados reais.

## Como funciona

```
Segunda: produção semanal via /content-swarm (usa instaladores de clientes/ativos/)
        ↓
Durante a semana: posts publicados
        ↓
Sexta: Cristian cola métricas no performance/[cliente].tsv (2 min do LinkedIn Analytics)
        ↓
Sexta 18h: GitHub Action roda, analisa, abre PR com melhorias no instalador
        ↓
Final de semana: Cristian revisa e aprova o PR
        ↓
Segunda: novo ciclo começa com instalador melhorado
```

## Arquivos que importam

- **`program.md`** — instrução mestre do agente de research (humano itera aqui)
- **`instaladores/[cliente]/`** — cópias dos instaladores para versionamento do loop
- **`performance/[cliente].tsv`** — histórico de resultados por post
- **`scripts/run_research.py`** — script que a GitHub Action executa

## Clientes

| Cliente | Squad | Plataforma principal |
|---|---|---|
| powerd | Cristian (Powerd) | LinkedIn |
| fernando-maeda | Fernando Maeda | LinkedIn |
| salva-tributo | Tiago Salvador | LinkedIn |
| sim-carreira | Thiago Sim Carreira | LinkedIn |

## Secrets necessários no GitHub

- `ANTHROPIC_API_KEY` — para chamar Claude API via GitHub Actions

## Rodando manualmente

Na aba Actions do GitHub → "Weekly AutoResearch" → "Run workflow" → escolher cliente e semana.

Ou localmente via skill `/auto-research` no Claude Code.
