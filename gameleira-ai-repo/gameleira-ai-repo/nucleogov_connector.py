"""
nucleogov_connector.py

Conector reutilizável para instâncias do sistema NúcleoGov (usado por câmaras e
prefeituras em GO, entre outros estados). Construído a partir da documentação
oficial de API publicada em cada instância, em cumprimento ao Art. 8º, §3º, III
da Lei de Acesso à Informação (Lei 12.527/2011):

    https://acessoainformacao.gameleiradegoias.go.leg.br/cidadao/outras_informacoes/acesso_automatizado

IMPORTANTE — leia antes de rodar:
  1. Este ambiente (sandbox) não tem egress liberado para domínios .gov.br/.leg.br,
     então este código NÃO foi executado contra os servidores reais. Rode a partir
     da sua própria infraestrutura e valide as respostas antes de usar em produção.
  2. A API oficial documentada só cobre 2 endpoints (estrutura_organizacional e
     ouvidoria) — dados de folha de pagamento, contratos, licitações, receitas e
     despesas NÃO têm endpoint JSON documentado publicamente; eles vivem em
     páginas HTML (tabelas renderizadas). Para essas, incluí o mapa de rotas
     confirmado (ROTAS_TRANSPARENCIA) para servir de base a um scraper HTML
     (ex. com BeautifulSoup) — a implementação do parser fica para a próxima
     iteração, depois de inspecionar o HTML real de cada página.
  3. Antes de automatizar contra qualquer instância nova, confira o robots.txt
     e os Termos de Uso publicados no próprio portal.

Instâncias confirmadas até agora:
  - Câmara de Piracanjuba (GO)        -> sistema Centi (NÃO é NúcleoGov)
  - Prefeitura de Piracanjuba (GO)    -> NúcleoGov
  - Câmara de Gameleira de Goiás (GO) -> NúcleoGov
  - Prefeitura de Gameleira de Goiás  -> NúcleoGov

DESCOBERTA IMPORTANTE (validada em 22/07/2026):
  A página de "Folha de Pagamento" do NúcleoGov NÃO guarda esse dado no próprio
  banco — ela é uma casca que carrega, via JavaScript, os dados de um sistema
  terceiro: o "MegaSoft Transparência" (produto MegaAdmWeb, da empresa
  Megasoft), hospedado em um subdomínio próprio por cidade, ex.:

      https://camaragameleiradegoias.megasofttransparencia.com.br/

  Isso é ótima notícia para a arquitetura: o MegaSoft não é exclusivo da
  Prefeitura como imaginávamos antes — é o motor de folha de pagamento por
  trás de QUALQUER órgão (câmara ou prefeitura) que usa NúcleoGov como portal.
  Ou seja, 1 conector MegaSoft serve para os dois.

  Problema: esse subdomínio é uma SPA (JS puro) — o HTML bruto vem vazio, os
  dados chegam via chamada AJAX feita pelo navegador depois da página
  carregar. Não encontrei documentação pública de API JSON para o MegaSoft
  (diferente do NúcleoGov, que documenta a sua). Para descobrir a URL real da
  API, o próximo passo é abrir a página no navegador, abrir o DevTools
  (F12) -> aba "Network"/"Rede", filtrar por "XHR" ou "Fetch", recarregar a
  página, e ver qual URL é chamada para preencher a tabela de servidores.
"""

from dataclasses import dataclass, field
from typing import Optional
import requests


NUCLEOGOV_HEADER = {"X-NucleoGov-Services": "true"}


# ---------------------------------------------------------------------------
# Instâncias conhecidas. Adicionar novas cidades aqui conforme forem mapeadas.
# ---------------------------------------------------------------------------
INSTANCIAS = {
    "piracanjuba_prefeitura": "https://acessoainformacao.piracanjuba.go.gov.br",
    "gameleira_camara": "https://acessoainformacao.gameleiradegoias.go.leg.br",
    "gameleira_prefeitura": "https://acessoainformacao.gameleiradegoias.go.gov.br",
}

# ---------------------------------------------------------------------------
# Rotas HTML de transparência confirmadas na instância da Câmara de Gameleira.
# Prefixo relativo à base da instância. Mesmo padrão de nomenclatura tende a se
# repetir entre instâncias NúcleoGov (confirmar caso a caso).
# ---------------------------------------------------------------------------
ROTAS_TRANSPARENCIA = {
    "folha_pagamento": "/cidadao/transparencia/mgservidores",
    "padrao_remuneratorio": "/cidadao/transparencia/padraoremuneratorio",
    "receitas_duodecimo": "/cidadao/transparencia/sgduodecimo",
    "despesas": "/cidadao/transparencia/mgdespesas",
    "despesas_extraorcamentarias": "/cidadao/transparencia/mgextraorcamentarias",
    "gastos_parlamentares": "/cidadao/transparencia/sggastosparlamentares",
    "licitacoes": "/cidadao/informacao/licitacoes_mg",
    "licitacoes_fracassadas_desertas": "/cidadao/informacao/licitacoes_fd_mg",
    "dispensas_inexigibilidades": "/cidadao/informacao/dispensas_mg",
    "plano_contratacoes_anual": "/cidadao/informacao/plano_anual_contratacoes",
    "sancoes_administrativas": "/cidadao/informacao/sancoes_administrativas",
    "contratos": "/cidadao/informacao/contratos_mg",
    "fiscais_de_contratos": "/cidadao/informacao/fiscais_contratos_mg",
    "ordem_cronologica_pagamentos": "/cidadao/informacao/ordem_cronologica_pagamentos_mg",
    "prestacao_contas_balanco_anual": "/cidadao/resp_fiscal/balancos_mg",
    "relatorio_gestao": "/cidadao/resp_fiscal/relatorios_circunstanciados",
    "parecer_tribunal_contas": "/cidadao/resp_fiscal/tcpareceres",
    "relatorios_gestao_fiscal": "/cidadao/resp_fiscal/rgf_mg",
    "sic": "/cidadao/informacao/sic",
    "lista_estagiarios": "/cidadao/outras_informacoes/lista_estagiarios",
    "lista_terceirizados": "/cidadao/outras_informacoes/lista_terceirizados",
    "concursos_publicos": "/cidadao/concursos_selecoes/concursos",
    "processos_seletivos": "/cidadao/concursos_selecoes/selecoes",
    "atas_de_sessao": "/cidadao/atos_adm/mp/id=6",
    "leis": "/cidadao/legislacao/leis",
    "decretos_legislativos": "/cidadao/legislacao/decretos",
    "resolucoes": "/cidadao/legislacao/resolucoes",
}


@dataclass
class NucleoGovClient:
    """Cliente para a API oficial de acesso automatizado de uma instância NúcleoGov."""

    base_url: str
    timeout: int = 20
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self):
        self.base_url = self.base_url.rstrip("/")
        self.session.headers.update(NUCLEOGOV_HEADER)
        self._sessao_aquecida = False

    def _aquecer_sessao(self) -> None:
        """Visita uma página normal antes do POST em /api.

        No teste de 22/07/2026, o POST em /api só passou de 403 para 200
        depois de visitar a página normal primeiro (que gera cookies de
        sessão). Chamado automaticamente por _post_api na primeira vez.
        """
        if not self._sessao_aquecida:
            self.session.get(f"{self.base_url}/cidadao/transparencia/mgservidores", timeout=self.timeout)
            self._sessao_aquecida = True

    # -- Endpoints oficiais documentados ------------------------------------

    def estrutura_organizacional(
        self, unidade_id: Optional[int] = None, search: Optional[str] = None
    ) -> dict:
        """GET /api/estrutura_organizacional — unidades da estrutura organizacional."""
        params = {"acao": "listar_relacao"}
        if unidade_id is not None:
            params["unidade_id"] = unidade_id
        if search is not None:
            params["search"] = search
        return self._get("/api/estrutura_organizacional", params)

    def ouvidoria_relatorio(
        self, data_inicial: Optional[str] = None, data_final: Optional[str] = None
    ) -> dict:
        """GET /api/ouvidoria — relatório estatístico de manifestações.

        Datas no formato aaaa-mm-dd. Se omitidas, o próprio serviço usa o
        exercício anterior completo (01/jan a 31/dez) como padrão.
        """
        params = {"acao": "relatorio"}
        if data_inicial is not None:
            params["data_inicial"] = data_inicial
        if data_final is not None:
            params["data_final"] = data_final
        return self._get("/api/ouvidoria", params)

    # -- Rotas HTML de transparência (ainda sem parser — ver módulo futuro) --

    def url_transparencia(self, chave: str) -> str:
        """Monta a URL completa de uma página de transparência conhecida.

        Uso: client.url_transparencia("folha_pagamento")
        Lança KeyError se a chave não estiver mapeada em ROTAS_TRANSPARENCIA.
        """
        return self.base_url + ROTAS_TRANSPARENCIA[chave]

    # -- Endpoint multiplexado /api (engenharia reversa, 22/07/2026) --------
    #
    # Descoberto inspecionando o DevTools -> Network -> Fetch/XHR na página
    # de folha de pagamento da Câmara de Gameleira. O NúcleoGov expõe um
    # endpoint genérico POST /api que recebe um dicionário com uma chave
    # arbitrária (usada só para casar request/response — parece suportar
    # múltiplas "ações" numa única chamada) mapeando para os parâmetros da
    # ação pedida. A ação "megasoft/servidores" repassa a chamada para o
    # backend MegaSoft (o mesmo motor por trás da folha de pagamento tanto
    # da Câmara quanto da Prefeitura). NÃO documentado oficialmente — ao
    # contrário de estrutura_organizacional/ouvidoria, pode mudar sem aviso.

    def folha_pagamento(
        self,
        pagina: int = 1,
        tamanho_pagina: int = 15,
        ano: Optional[str] = None,
        mes: Optional[str] = None,
    ) -> dict:
        """Folha de pagamento (servidores/vereadores) via backend MegaSoft.

        ano/mes no formato "2026"/"06". Quando omitidos, o servidor parece
        usar o mês corrente como padrão (comportamento inferido a partir de
        uma única amostra — vale confirmar rodando sem esses parâmetros e
        comparando com uma chamada passando o mês explicitamente).

        Retorna um dict com "total" (nº de registros) e "registros" (lista).
        Cada registro já vem com o CPF parcialmente mascarado pelo próprio
        governo (ex. "xxx.278.211-xx"), então é seguro reexibir como está.
        """
        params = {"pagina": pagina, "tamanhoDaPagina": tamanho_pagina}
        if ano is not None:
            params["ano"] = ano
        if mes is not None:
            params["mes"] = mes
        return self._post_api("megasoft/servidores", **params)

    def licitacoes(self, pagina: int = 1, tamanho_pagina: int = 15) -> dict:
        """Licitações via backend MegaSoft. Confirmado em 23/07/2026."""
        return self._post_api("megasoft/licitacoes", pagina=pagina, tamanhoDaPagina=tamanho_pagina)

    def contratos(self, pagina: int = 1, tamanho_pagina: int = 15) -> dict:
        """Contratos via backend MegaSoft. Confirmado em 23/07/2026."""
        return self._post_api("megasoft/contratos", pagina=pagina, tamanhoDaPagina=tamanho_pagina)

    def relatorios_gestao_fiscal(self, pagina: int = 1, tamanho_pagina: int = 15) -> dict:
        """Relatórios de Gestão Fiscal via backend MegaSoft. Confirmado em 23/07/2026."""
        return self._post_api("megasoft/rgf", pagina=pagina, tamanhoDaPagina=tamanho_pagina)

    def prestacao_contas_balanco(self, pagina: int = 1, tamanho_pagina: int = 15) -> dict:
        """Prestação de Contas / Balanço Anual via backend MegaSoft. Confirmado em 23/07/2026."""
        return self._post_api("megasoft/balanco", pagina=pagina, tamanhoDaPagina=tamanho_pagina)

    def receitas(self, pagina: int = 1, tamanho_pagina: int = 15) -> dict:
        """Receitas / Duodécimo via backend MegaSoft. Confirmado em 23/07/2026."""
        return self._post_api("megasoft/receitas", pagina=pagina, tamanhoDaPagina=tamanho_pagina)

    # -- Segundo padrão de endpoint: "declaracoes/listaDinamicaSg" ----------
    #
    # Descoberto em 23/07/2026 na Prefeitura de Gameleira: nem todo módulo
    # segue o padrão "megasoft/<nome>". Licitações na Prefeitura usa um
    # endpoint genérico e mais rico em filtros, onde o módulo desejado é um
    # PARÂMETRO ("modulo": "licitacoes"), não parte do nome da ação. O "Sg"
    # no nome sugere um sistema de gestão diferente do MegaSoft. Como o
    # endpoint é genérico por design, é provável que sirva também para
    # outros módulos (ex. "modulo": "contratos") — ainda não testado.

    def declaracao_dinamica(
        self,
        modulo: str,
        pagina: int = 1,
        tamanho_pagina: int = 15,
        **filtros_extra,
    ) -> dict:
        """Endpoint genérico 'declaracoes/listaDinamicaSg', parametrizado por módulo.

        Uso: client.declaracao_dinamica("licitacoes")
             client.declaracao_dinamica("contratos")  # hipótese, não confirmada

        filtros_extra permite passar parâmetros adicionais vistos na captura
        original (data_inicio, data_fim, dispensas_inexigibilidades,
        only_dispensas, modalidades_especificas, situacoes_especificas) —
        omitidos aqui viram string vazia / valores padrão, que pareceu
        funcionar na captura real.
        """
        params = {
            "modulo": modulo,
            "data_inicio": "",
            "data_fim": "",
            "only_dispensas": False,
            "modalidades_especificas": "",
            "situacoes_especificas": "",
            "pagina": pagina,
            "tamanhoDaPagina": tamanho_pagina,
        }
        params.update(filtros_extra)
        return self._post_api("declaracoes/listaDinamicaSg", **params)

    def licitacoes_prefeitura(self, pagina: int = 1, tamanho_pagina: int = 15) -> dict:
        """Licitações via o padrão 'declaracoes/listaDinamicaSg'. Confirmado em 23/07/2026 (Prefeitura)."""
        return self.declaracao_dinamica("licitacoes", pagina=pagina, tamanho_pagina=tamanho_pagina)

    # -- Terceiro padrão de endpoint: "<nome>_mg/listar" ---------------------
    #
    # Descoberto em 23/07/2026 na página de Contratos da Prefeitura. Nem
    # "megasoft/X" nem "declaracoes/listaDinamicaSg" — um terceiro esquema,
    # com paginação em formato "offset, quantidade" (string, ex. "0, 15")
    # em vez de pagina/tamanhoDaPagina. Confirma que este sistema foi
    # construído em pedaços por equipes/épocas diferentes — não dá para
    # assumir um único padrão vale para todos os módulos.

    def _mg_listar(self, nome: str, offset: int = 0, limite: int = 15) -> dict:
        """Endpoint genérico '<nome>_mg/listar'.

        Uso: client._mg_listar("contratos") -> acao "contratos_mg/listar"
        """
        return self._post_api(f"{nome}_mg/listar", limit=f"{offset}, {limite}")

    def contratos_prefeitura(self, offset: int = 0, limite: int = 15) -> dict:
        """Contratos via o padrão '<nome>_mg/listar'. Confirmado em 23/07/2026 (Prefeitura).

        Retorna dict com "dados" (lista de contratos), "total", e campos
        auxiliares como "orgao_principal". Cada contrato traz fornecedor,
        CNPJ, valor, vigência, situação, fiscal do contrato e link para a
        licitação de origem.
        """
        return self._mg_listar("contratos", offset=offset, limite=limite)

    def _post_api(self, acao: str, **params) -> dict:
        """POST genérico para o endpoint multiplexado /api.

        Formato real confirmado em 22/07/2026 via "Copy as cURL" do Chrome
        (tentativas anteriores com corpo JSON puro retornavam 200 com "[]" —
        o servidor não estava rejeitando por auth/cookie, e sim porque o
        formato do corpo estava errado):

          Content-Type: application/x-www-form-urlencoded
          corpo: multi_request=true&params=<JSON URL-encoded>

        onde o JSON de "params" é {chave_correlacao: {"acao": acao, **params}},
        igual antes — só muda como isso é empacotado no corpo do POST.
        """
        import random
        import string
        import json as json_module

        chave = "0-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        params_json = json_module.dumps({chave: {"acao": acao, **params}})
        self._aquecer_sessao()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/cidadao/transparencia/mgservidores",
            "Origin": self.base_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        resp = self.session.post(
            f"{self.base_url}/api",
            data={"multi_request": "true", "params": params_json},
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get(chave, data)

    # -- Interno ---------------------------------------------------------------

    def _get(self, path: str, params: dict) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()


def get_client(nome_instancia: str) -> NucleoGovClient:
    """Atalho: get_client("gameleira_camara") usando o registro em INSTANCIAS."""
    if nome_instancia not in INSTANCIAS:
        raise KeyError(
            f"Instância '{nome_instancia}' não registrada. "
            f"Disponíveis: {list(INSTANCIAS)}"
        )
    return NucleoGovClient(INSTANCIAS[nome_instancia])


if __name__ == "__main__":
    # Exemplo de uso — rodar a partir de uma rede com acesso liberado aos
    # domínios .go.leg.br / .go.gov.br. Aqui, apenas ilustrativo.
    camara_gameleira = get_client("gameleira_camara")

    print("Estrutura organizacional:")
    print(camara_gameleira.estrutura_organizacional())

    print("\nRelatório da ouvidoria (padrão: exercício anterior):")
    print(camara_gameleira.ouvidoria_relatorio())

    print("\nURL da folha de pagamento (para scraper HTML futuro):")
    print(camara_gameleira.url_transparencia("folha_pagamento"))

    print("\nFolha de pagamento (via endpoint /api descoberto por engenharia reversa):")
    folha = camara_gameleira.folha_pagamento(pagina=1, tamanho_pagina=15)
    print(f"Total de registros: {folha.get('total')}")
    for servidor in folha.get("registros", []):
        print(f"  {servidor['nome']} — {servidor['cargo']} — R$ {servidor['totalLiquido']}")
