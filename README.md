# Cline Models

Página e app que listam os modelos de IA **gratuitos** na Cline, ordenados por
inteligência. Publicado no GitHub Pages: o `index.html` lê o `data.json`, que
é regenerado automaticamente duas vezes ao dia.

## Como funciona

1. **Coleta menções dos últimos 30 dias** em três fontes:
   - Reddit r/CLine — busca por "free" (via RSS de busca, com retry para o
     rate limit 429 do Reddit; o `.json` público retorna 403)
   - Hacker News — API pública do Algolia
   - Blog oficial da Cline (cline.bot/blog)
2. **Reconhece os modelos citados**: em cada frase que contém a palavra
   "free", procura o nome de um modelo usando o catálogo do modelgrep.com
   (sitemap, ~1.5 mil modelos). Frases que só citam o modelo sem falar de
   free são ignoradas — evita falsos positivos de posts de benchmark.
3. **Filtra pelo ranking smart do modelgrep**: só entra quem está em
   https://modelgrep.com/best/smartest, com o score dela — remove modelos
   free fora do top e os já deslistados. A lista final sai ordenada por
   inteligência.

## Regras de reconhecimento

- "Muse Spark 1.3 Contributor" == "Muse Spark 1.3" — o sufixo Contributor é
  só a variante de compartilhamento com a Meta.
- Versão mais nova da mesma família vence: quando a DeepSeek lançou o
  V4.1 Flash como free, o V4 Flash deixou de ser.
- Modelos stealth revelados ficam em `_STEALTH_ALIASES`
  (`cline_models/free_models.py`; ex.: Ox Alpha = GLM-5.3-Flash).

## Uso

```bash
python main.py              # lista "Models" ordenada por inteligência
python main.py --posts      # mostra as menções coletadas nas fontes
python main.py --json       # tudo em JSON (com scores e fontes)
python main.py --json > data.json   # regenera os dados da página
```

Sem dependências externas — apenas biblioteca padrão do Python (3.10+).

## Atualização automática

O workflow `.github/workflows/update-models.yml` roda o app duas vezes ao dia
(09:00 e 21:00 UTC, via cron do GitHub Actions) e faz commit do `data.json`
quando a lista muda. Com o GitHub Pages configurado para servir da branch
principal (pasta raiz), o site reflete a lista nova sozinho.

## Publicação no GitHub Pages

1. Suba o repositório para o GitHub.
2. Em **Settings → Pages**, escolha *Deploy from a branch* → branch `main`,
   pasta `/ (root)`.
3. O `index.html` passa a ser servido na URL do Pages, lendo o `data.json`
   da própria branch.

## Estrutura

- `index.html` — página do GitHub Pages (lê `data.json`, com fallback embutido).
- `data.json` — dados atuais: lista de modelos, scores, fontes e menções.
- `main.py` — CLI e pipeline.
- `cline_models/sources.py` — coleta de menções (Reddit, HN, blog) com filtro
  de data de 30 dias.
- `cline_models/reddit.py` — RSS de busca do Reddit e User-Agent de navegador.
- `cline_models/modelgrep.py` — rankings (smartest, free-llm-api), catálogo do
  sitemap e score/nome da página de detalhe de cada modelo.
- `cline_models/free_models.py` — detecção frase por frase, aliases de modelos
  stealth e regra de família (versão mais nova vence).
- `.github/workflows/update-models.yml` — atualização duas vezes ao dia.
