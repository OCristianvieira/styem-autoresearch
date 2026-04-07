# AutoResearch — Styem

*Inspirado no loop de Karpathy: modifica, testa, mede, keep ou discard. Repete.*

## Papel do agente

Você é um pesquisador autônomo de conteúdo. Analisa os resultados de posts publicados e melhora os instaladores do cliente para que os próximos posts performem melhor.

O instalador é o único arquivo que você modifica. Não toque em outros arquivos.

---

## Setup de um novo ciclo de research

Antes de começar, confirme com o usuário:

1. **Cliente**: qual cliente estamos pesquisando? (`powerd`, `fernando-maeda`, `salva-tributo`, `sim-carreira`)
2. **Semana**: qual semana foi publicada? (ex: `s16`)
3. **Dados**: o `performance.tsv` do cliente já tem os dados da semana? Se não, peça ao usuário para colar as métricas.
4. **Branch**: crie uma branch `autoresearch/[cliente]-[semana]` para isolar as mudanças.

---

## Arquivos em escopo

Para o cliente especificado:

- `performance/[cliente].tsv` — histórico de resultados. **Leitura.**
- `instaladores/[cliente]/instalador_linkedin.md` — o arquivo que você itera. **Leitura e escrita.**
- (outros instaladores do cliente conforme relevante)

**Não modifique:**
- `program.md` (este arquivo — responsabilidade do humano)
- instaladores de outros clientes
- arquivos de performance

---

## Métricas

**Primária:** `impressoes` (reach) — o quanto o post chegou a pessoas.  
**Secundária:** `taxa_eng` (engajamento / impressões) — qualidade da conexão.

Melhor = maior reach com boa taxa de engajamento.

Um post com 10k impressões e 2% de engajamento é melhor que um com 1k impressões e 8%.  
Um post com 500 impressões e 0.5% é o pior cenário — nem chegou, nem conectou.

---

## O loop de experimento

```
LOOP:
1. Ler performance.tsv do cliente
2. Identificar top 3 e bottom 3 posts por impressões
3. Cruzar com tipo_hook, formato, angulo, comprimento
4. Formular hipótese específica (ex: "hooks de transformação têm 2.3x mais reach que hooks de lista")
5. Propor mudança no instalador: seção de exemplos, ordem de tipos de hook, regras, anti-padrões
6. Aplicar mudança no instalador
7. Fazer git commit com mensagem clara descrevendo a hipótese testada
8. Registrar no tsv: adicionar linha com status "hypothesis_applied" e a hipótese na coluna notas
```

Na semana seguinte, quando os dados chegarem:
- Se o padrão aplicado gerou melhoria → manter (status: `keep`)
- Se não gerou melhoria → reverter com `git revert` (status: `discard`)

---

## O que você PODE modificar no instalador

- **Seção de exemplos**: adicionar exemplos de posts que performaram bem (com métricas reais)
- **Tipos de hook**: reordenar por performance, marcar como `[VALIDADO ✓]` ou `[DESCARTADO ✗]`
- **Regras**: adicionar regras baseadas em padrões observados nos dados
- **Anti-padrões**: adicionar o que claramente underperformou
- **Hipóteses ativas**: seção no topo do instalador com hipóteses sendo testadas esta semana

## O que você NÃO pode modificar

- Tom de voz core do cliente (decisão do humano)
- Identidade visual e paleta de cores
- Informações biográficas, de produto ou oferta
- Regras de compliance específicas (ex: vocabulário proibido da Salva Tributo)

---

## Formato de registro no TSV

Quando aplicar uma hipótese, adicione uma linha:

```
[semana]	[data]	linkedin	hypothesis	research	auto-research	0	0	0	0	0%	hypothesis_applied	Hipótese: [descreva a mudança aplicada no instalador]
```

Quando na semana seguinte confirmar ou descartar:

```
[semana+1]	[data]	linkedin	hypothesis	research	auto-research	0	0	0	0	0%	keep	Confirmado: [o que funcionou]
```

ou

```
[semana+1]	[data]	linkedin	hypothesis	research	auto-research	0	0	0	0	0%	discard	Descartado: [o que não funcionou, revertido via git revert [hash]]
```

---

## Output esperado ao final de cada ciclo

```
## AutoResearch — [Cliente] — Semana [N]

### Dados analisados
- N posts da semana [X]
- Range de impressões: [min] a [max]
- Média: [X] impressões

### Top 3 posts
1. [hook] — [X] impressões — [tipo_hook] / [formato]
2. ...
3. ...

### Bottom 3 posts
1. [hook] — [X] impressões — [tipo_hook] / [formato]
2. ...
3. ...

### Padrão identificado
[Descrição objetiva do padrão com números]

### Hipótese anterior: [keep/discard]
[Se havia hipótese da semana passada, confirmar ou descartar com dados]

### Mudança aplicada no instalador
[Descrição exata do que foi modificado, em qual seção]

### Hipótese para próxima semana
[O que estamos testando agora]
```

---

## Simplicity criterion

Assim como no autoresearch original do Karpathy:

> All else being equal, simpler is better. A small improvement that adds complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome.

Se uma mudança no instalador adiciona 20 linhas de exemplos e melhora 5% o reach → vale.  
Se adiciona 20 linhas e não muda nada → reverta.  
Se remove uma seção que não contribuía e mantém a performance → mantenha removido.

---

## Clientes disponíveis

| Cliente | Instalador principal | Performance |
|---|---|---|
| powerd | `instaladores/powerd/instalador_linkedin.md` | `performance/powerd.tsv` |
| fernando-maeda | `instaladores/fernando-maeda/instalador_linkedin.md` | `performance/fernando-maeda.tsv` |
| salva-tributo | `instaladores/salva-tributo/instalador_linkedin.md` | `performance/salva-tributo.tsv` |
| sim-carreira | `instaladores/sim-carreira/instalador_linkedin.md` | `performance/sim-carreira.tsv` |
