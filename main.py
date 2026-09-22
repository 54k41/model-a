"""App CLI: modelos gratuitos na Cline, a partir de várias fontes.

    1. Coleta menções recentes (últimos 30 dias) em: r/CLine (busca "free"),
       Hacker News e blog oficial da Cline.
    2. Em cada frase com "free", reconhece o modelo citado usando o catálogo
       de modelos do modelgrep (sitemap) e descarta versões antigas da mesma
       família que foram substituídas.
    3. Filtra pelo ranking de inteligência do modelgrep: só entra quem está
       na lista smart (https://modelgrep.com/best/smartest), com o score dela.

Output: única lista "Models", ordenada por inteligência.

Uso:
    python main.py              # pipeline completo
    python main.py --posts      # mostra as menções coletadas
    python main.py --json       # tudo em JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from cline_models.free_models import detect_free_models
from cline_models.modelgrep import fetch_catalog, fetch_smartest_models
from cline_models.sources import fetch_all_posts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lista os modelos grátis na Cline, ordenados por inteligência.",
    )
    parser.add_argument("--posts", action="store_true",
                        help="mostra as menções coletadas nas fontes")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    args = parser.parse_args(argv)

    try:
        posts = fetch_all_posts(days=30)
    except Exception as exc:
        print(f"Erro ao coletar as fontes: {exc}", file=sys.stderr)
        return 1
    if not posts:
        print("Nenhuma menção encontrada nos últimos 30 dias.")
        return 0

    try:
        catalog = fetch_catalog()
    except Exception as exc:
        print(f"Erro ao obter o catálogo do modelgrep: {exc}", file=sys.stderr)
        return 1

    try:
        smartest = fetch_smartest_models()
    except Exception as exc:
        print(f"Erro ao obter o ranking do modelgrep: {exc}", file=sys.stderr)
        return 1

    # Filtro final: só permanece quem está no ranking smart do modelgrep —
    # remove modelos free fora do top (Solar Pro 4, LongCat 2.0) e os já
    # deslistados (Union Alpha).
    smart_by_url = {r.url: r for r in smartest}
    free_models = [m for m in detect_free_models(posts, catalog, resolve_details=False)
                   if m.url in smart_by_url]
    for model in free_models:
        ranked = smart_by_url[model.url]
        # o ranking exibe "Vendor: Nome"; para nomes iguais ao vendor, fica só o nome
        model.name = ranked.name.split(": ", 1)[-1]
        model.score = ranked.score
    free_models.sort(key=lambda m: -(m.score or 0))

    if args.posts:
        print(f"{len(posts)} menção(ões) coletada(s) nos últimos 30 dias:\n")
        for post in posts:
            date = post.date.strftime("%Y-%m-%d") if post.date else "s/ data"
            print(f"[{date}] ({post.source}) {post.title}")

    if args.json:
        print(json.dumps({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "models": [m.to_dict() for m in free_models],
            "posts": [p.to_dict() for p in posts],
        }, ensure_ascii=False, indent=2))
        return 0

    print()
    print("Models")
    if not free_models:
        print("  (nenhum modelo free detectado)")
    for model in free_models:
        print(f"- {model.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
