# Cline Models

Seleção dos **melhores modelos gratuitos** disponíveis na Cline, ordenados por
inteligência.

O app monitora os anúncios mais recentes, identifica quais modelos estão de
fato grátis e valida cada um pelo seu score de inteligência — o resultado é a
lista publicada no [site do projeto](https://54k41.github.io/model-a/), que se
atualiza automaticamente duas vezes ao dia.

## Uso

```bash
python main.py              # lista "Models" ordenada por inteligência
python main.py --json > data.json   # regenera os dados da página
```

Sem dependências externas — apenas biblioteca padrão do Python (3.10+).

## Estrutura

- `index.html` — página publicada (lê `data.json`).
- `data.json` — dados atuais da lista.
- `main.py` — app CLI.
- `cline_models/` — módulos de coleta, reconhecimento e ranking.
- `.github/workflows/update-models.yml` — atualização automática 2x ao dia.
