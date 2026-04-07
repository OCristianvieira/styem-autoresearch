"""
AutoResearch — Styem
Lê program.md + performance TSV + instalador, chama Claude API,
aplica mudanças no instalador e registra no TSV.
"""

import os
import sys
import anthropic
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent
CLIENTE = os.environ.get("CLIENTE", "powerd")
SEMANA = os.environ.get("SEMANA", "auto")

def load_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[arquivo não encontrado: {path}]"

def detect_semana_from_tsv(tsv_content: str) -> str:
    """Detecta a semana mais recente no TSV."""
    lines = [l for l in tsv_content.strip().splitlines() if l and not l.startswith("semana")]
    if not lines:
        return "s01"
    last = lines[-1].split("\t")
    if last:
        return last[0]
    return "s01"

def main():
    print(f"[AutoResearch] Cliente: {CLIENTE} | Semana: {SEMANA}")

    # Carregar arquivos
    program_md = load_file(REPO_ROOT / "program.md")
    tsv_path = REPO_ROOT / "performance" / f"{CLIENTE}.tsv"
    tsv_content = load_file(tsv_path)
    instalador_path = REPO_ROOT / "instaladores" / CLIENTE / "instalador_linkedin.md"
    instalador_content = load_file(instalador_path)

    semana_atual = SEMANA if SEMANA != "auto" else detect_semana_from_tsv(tsv_content)
    hoje = datetime.now().strftime("%Y-%m-%d")

    print(f"[AutoResearch] Semana detectada: {semana_atual}")

    # Verificar se há dados suficientes
    linhas_dados = [l for l in tsv_content.strip().splitlines() if l and not l.startswith("semana") and "hypothesis" not in l]
    if len(linhas_dados) < 3:
        print(f"[AutoResearch] AVISO: apenas {len(linhas_dados)} posts no TSV. Precisamos de pelo menos 3 para análise confiável.")
        if len(linhas_dados) == 0:
            print("[AutoResearch] TSV vazio. Pulando ciclo — adicione métricas ao performance.tsv primeiro.")
            sys.exit(0)

    # Montar prompt para Claude
    prompt = f"""Você é o agente de AutoResearch do Styem.

Leia o program.md abaixo para entender suas instruções:

<program_md>
{program_md}
</program_md>

---

Cliente atual: {CLIENTE}
Semana atual: {semana_atual}
Data: {hoje}

---

Dados de performance:

<performance_tsv>
{tsv_content}
</performance_tsv>

---

Instalador atual (instalador_linkedin.md):

<instalador>
{instalador_content}
</instalador>

---

Execute o loop de research conforme o program.md.

Ao final, responda em formato JSON com esta estrutura EXATA:

{{
  "analise": "Resumo da análise em 2-3 parágrafos",
  "padrao_identificado": "O padrão principal encontrado nos dados",
  "hipotese_aplicada": "A hipótese que você está testando esta semana",
  "mudancas_instalador": "Descrição das mudanças feitas",
  "instalador_atualizado": "CONTEÚDO COMPLETO do instalador com as mudanças aplicadas",
  "linha_tsv": "A linha a adicionar no TSV (formato TSV com tabs, sem newline)"
}}

IMPORTANTE: O campo "instalador_atualizado" deve conter o arquivo COMPLETO, não apenas as partes modificadas.
"""

    # Chamar Claude API
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("[AutoResearch] Chamando Claude API...")
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text
    print("[AutoResearch] Resposta recebida. Processando...")

    # Extrair JSON da resposta
    import json
    import re

    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        print("[AutoResearch] ERRO: Não foi possível extrair JSON da resposta.")
        print(response_text[:500])
        sys.exit(1)

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        print(f"[AutoResearch] ERRO ao parsear JSON: {e}")
        print(json_match.group()[:500])
        sys.exit(1)

    # Aplicar mudanças no instalador
    if result.get("instalador_atualizado"):
        instalador_path.write_text(result["instalador_atualizado"], encoding="utf-8")
        print(f"[AutoResearch] Instalador atualizado: {instalador_path}")
    else:
        print("[AutoResearch] AVISO: Nenhuma mudança no instalador.")

    # Registrar no TSV
    if result.get("linha_tsv"):
        with open(tsv_path, "a", encoding="utf-8") as f:
            f.write(result["linha_tsv"] + "\n")
        print(f"[AutoResearch] TSV atualizado: {tsv_path}")

    # Salvar relatório de research
    report_path = REPO_ROOT / "performance" / f"{CLIENTE}-research-{semana_atual}.md"
    report_content = f"""# AutoResearch — {CLIENTE} — {semana_atual}

Data: {hoje}

## Análise

{result.get('analise', 'N/A')}

## Padrão identificado

{result.get('padrao_identificado', 'N/A')}

## Hipótese aplicada

{result.get('hipotese_aplicada', 'N/A')}

## Mudanças no instalador

{result.get('mudancas_instalador', 'N/A')}
"""
    report_path.write_text(report_content, encoding="utf-8")
    print(f"[AutoResearch] Relatório salvo: {report_path}")

    print("[AutoResearch] Ciclo concluído com sucesso.")

if __name__ == "__main__":
    main()
