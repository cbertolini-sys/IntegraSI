"""A regra de escrita do projeto, aplicada ao repositório inteiro.

Nada de travessão. A regra está no README.md e na CLAUDE.md; aqui ela deixa de
depender de quem lembra e passa a reprovar.

Este arquivo não escreve o símbolo literalmente em lugar nenhum: ele é montado a
partir do código Unicode. Sem isso, o próprio teste precisaria estar na lista de
exceções, e uma regra que não vale para quem a aplica é uma regra pela metade.
"""

import subprocess
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)

TRAVESSAO = chr(0x2014)
# Montada por partes pelo mesmo motivo do caractere: escrever a entidade inteira
# aqui faria este arquivo violar a regra que ele existe para impor.
ENTIDADE = "&" + "mdash;"

# Os dois documentos que DEFINEM a regra precisam mostrar o símbolo para explicá-lo.
# É a única exceção, e ela não é livre: `test_a_excecao_continua_justificada`
# reprova se um deles deixar de falar do assunto, para que a entrada não vire
# permissão esquecida.
PODEM_CITAR = {"README.md", "CLAUDE.md"}


def arquivos_versionados():
    saida = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return [c for c in saida.split("\0") if c]


def texto_de(caminho):
    """Devolve o conteúdo, ou None se o arquivo não for texto.

    Fonte, imagem e PDF entram no `git ls-files` como qualquer outro; o erro de
    decodificação é o que os separa, sem precisar manter uma lista de extensões
    que envelheceria a cada arquivo novo.
    """
    try:
        return (RAIZ / caminho).read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        return None


def ocorrencias(procurado):
    achados = []
    for caminho in arquivos_versionados():
        if caminho in PODEM_CITAR:
            continue
        conteudo = texto_de(caminho)
        if conteudo is None or procurado not in conteudo:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if procurado in linha:
                achados.append(f"{caminho}:{numero}: {linha.strip()[:100]}")
    return achados


def test_o_repositorio_nao_usa_travessao():
    """O caractere, em qualquer arquivo de texto versionado.

    Se este teste reprovar num arquivo que você acabou de trazer de fora, a
    correção é reescrever a frase, e não acrescentar o arquivo a `PODEM_CITAR`.
    Ver README.md, seção "Estilo de escrita", para qual pontuação usar em cada caso.
    """
    achados = ocorrencias(TRAVESSAO)
    assert not achados, "travessão encontrado em:\n" + "\n".join(achados)


def test_o_repositorio_nao_usa_a_entidade_do_travessao():
    """A entidade HTML renderiza o mesmo símbolo.

    Teste separado do anterior de propósito: são duas formas de escrever a mesma
    coisa, e um teste só que checasse as duas juntas continuaria verde com
    metade da regra apagada.
    """
    achados = ocorrencias(ENTIDADE)
    assert not achados, "entidade de travessão encontrada em:\n" + "\n".join(achados)


def test_a_excecao_continua_justificada():
    """Os dois arquivos isentos precisam continuar sendo os que explicam a regra.

    Sem isto, `PODEM_CITAR` viraria uma permissão permanente: alguém apagaria a
    seção de estilo do README e a isenção seguiria de pé, deixando dois arquivos
    livres para usar o símbolo sem que nada acusasse.
    """
    for nome in PODEM_CITAR:
        conteudo = texto_de(nome)
        assert conteudo is not None, f"{nome} sumiu"
        assert TRAVESSAO in conteudo, (
            f"{nome} está isento da regra por explicá-la, mas não mostra mais o "
            "símbolo. Tire-o de PODEM_CITAR ou devolva a explicação."
        )
        assert "travessão" in conteudo.lower(), f"{nome} não fala mais da regra"


def test_a_varredura_alcanca_o_repositorio_todo():
    """Prova que a busca não está vazia por engano.

    Um `git ls-files` que devolvesse nada deixaria os testes acima verdes para
    sempre, e o defeito seria invisível: nenhuma ocorrência é exatamente o que
    se espera ver quando tudo está certo.
    """
    arquivos = arquivos_versionados()
    assert len(arquivos) > 100, f"esperava o repositório inteiro, vi {len(arquivos)}"
    legiveis = [c for c in arquivos if texto_de(c) is not None]
    assert len(legiveis) > 100, "quase nada foi lido como texto"
