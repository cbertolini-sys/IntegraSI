"""A spec e a autoridade do projeto (CLAUDE.md). Uma regra que vale no codigo e
nao vale na spec vira contradicao silenciosa para quem ler depois -- e o Plano 5
contradiz o que a spec dizia sobre quem cria conta de aluno.

Estes testes leem o repositorio, nao o sistema. Nao provam que o codigo faz o que
a spec diz; provam que a spec nao afirma o contrario do que foi decidido.
"""

from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
SPEC = RAIZ / "docs" / "superpowers" / "specs" / "2026-08-25-integrasi-design.md"


def test_a_spec_registra_que_coordenador_e_professor():
    assert "todo coordenador é também professor" in SPEC.read_text().lower()


def test_a_spec_registra_a_alocacao_por_nome_e_email():
    texto = SPEC.read_text().lower()
    assert "nome e e-mail" in texto
    assert "primeiro acesso" in texto


def test_a_spec_nao_afirma_mais_que_o_coordenador_cadastra_todos():
    """A frase antiga contradiz a regra 2 e precisa SAIR, nao apenas ganhar uma
    ressalva em outro lugar: quem ler so a secao 2 acreditaria nela."""
    assert "criadas pelo coordenador via Django Admin" not in SPEC.read_text()


def test_claude_md_documenta_o_primeiro_acesso():
    texto = (RAIZ / "CLAUDE.md").read_text().lower()
    assert "primeiro acesso" in texto
    assert "convite" in texto


def test_operacao_ensina_a_diagnosticar_convite_nao_recebido():
    """Quem opera precisa saber onde olhar quando um aluno diz que nao recebeu o
    e-mail. Sem isto, a resposta e "reenvia e torce"."""
    assert "CONVITE_ALUNO" in (RAIZ / "docs" / "operacao.md").read_text()
