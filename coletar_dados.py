"""
coletar_dados.py

Roda todos os endpoints já confirmados (Câmara + Prefeitura de Gameleira de
Goiás) e salva o resultado em arquivos JSON dentro de data/. Pensado para
rodar automaticamente via GitHub Actions (ver .github/workflows/
atualizar-dados.yml), mas funciona igual rodando manualmente:

    python3 coletar_dados.py

Gera:
    data/camara.json
    data/prefeitura.json

O site (index.html) lê esses arquivos via fetch() — como ficam no mesmo
domínio do site publicado (GitHub Pages), não existe problema de CORS.
"""

import json
import os
from datetime import datetime, timezone

from nucleogov_connector import get_client


def coletar_camara() -> dict:
    camara = get_client("gameleira_camara")
    return {
        "folha_pagamento": camara.folha_pagamento(pagina=1, tamanho_pagina=50),
        "licitacoes": camara.licitacoes(pagina=1, tamanho_pagina=50),
        "contratos": camara.contratos(pagina=1, tamanho_pagina=50),
        "gestao_fiscal": camara.relatorios_gestao_fiscal(pagina=1, tamanho_pagina=50),
        "balanco": camara.prestacao_contas_balanco(pagina=1, tamanho_pagina=50),
        "receitas": camara.receitas(pagina=1, tamanho_pagina=50),
    }


def coletar_prefeitura() -> dict:
    prefeitura = get_client("gameleira_prefeitura")
    return {
        "folha_pagamento": prefeitura.folha_pagamento(pagina=1, tamanho_pagina=50),
        "contratos": prefeitura.contratos_prefeitura(offset=0, limite=50),
        "gestao_fiscal": prefeitura.relatorios_gestao_fiscal(pagina=1, tamanho_pagina=50),
        "balanco": prefeitura.prestacao_contas_balanco(pagina=1, tamanho_pagina=50),
        "receitas": prefeitura.receitas(pagina=1, tamanho_pagina=50),
        "licitacoes": prefeitura.licitacoes_prefeitura(pagina=1, tamanho_pagina=50),
    }


def salvar(caminho: str, dados: dict) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    pacote = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "dados": dados,
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(pacote, f, ensure_ascii=False, indent=2)
    print(f"Salvo: {caminho}")


def main():
    print("Coletando dados da Câmara...")
    try:
        salvar("data/camara.json", coletar_camara())
    except Exception as e:
        # Não derruba o job inteiro se um órgão falhar — o outro ainda salva.
        print(f"ERRO ao coletar Câmara: {e}")

    print("Coletando dados da Prefeitura...")
    try:
        salvar("data/prefeitura.json", coletar_prefeitura())
    except Exception as e:
        print(f"ERRO ao coletar Prefeitura: {e}")


if __name__ == "__main__":
    main()
