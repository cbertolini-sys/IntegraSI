"""Quem e a coordenacao, para efeito de aviso, se responde num lugar so.

A regra estava escrita duas vezes, identica e independente, em
`apps/cursos/services.py` e `apps/catalogo/views.py`. Enquanto a regra nao muda,
duas copias iguais nao quebram nada. O problema aparece na primeira vez que ela
mudar - e ela ja mostrou que vai mudar: em 04/09 um coordenador com endereco
inexistente gerou devolucao a cada aviso, e "excluir coordenador sem endereco
entregavel" e exatamente o tipo de ajuste que se faz num arquivo e se esquece no
outro. A suite fica verde e metade dos avisos passa a se comportar diferente da
outra metade.

Mora em `contas` porque `contas` e folha na hierarquia de apps: `cursos` e
`catalogo` ja podem importa-la, entao unificar aqui nao cria dependencia nova.
"""

import pytest

from apps.contas import services
from apps.contas.models import Usuario


@pytest.mark.django_db
def test_devolve_todos_os_coordenadores(coordenador, outro_coordenador):
    assert set(services.emails_da_coordenacao()) == {
        coordenador.email,
        outro_coordenador.email,
    }


@pytest.mark.django_db
def test_ignora_quem_nao_e_coordenador(coordenador, professor, aluno):
    emails = services.emails_da_coordenacao()

    assert professor.email not in emails
    assert aluno.email not in emails


@pytest.mark.django_db
def test_ignora_coordenador_desativado(coordenador, outro_coordenador):
    """Conta desativada nao recebe aviso: e o jeito de tirar alguem da lista sem
    apagar o historico dele."""
    outro_coordenador.is_active = False
    outro_coordenador.save(update_fields=["is_active"])

    assert services.emails_da_coordenacao() == [coordenador.email]


@pytest.mark.django_db
def test_sem_coordenador_devolve_lista_vazia(professor):
    """Nao pode estourar: `enfileirar` recebe esta lista e uma instalacao recem
    inaugurada pode nao ter coordenador nenhum ainda."""
    Usuario.objects.filter(papel=Usuario.COORDENADOR).delete()

    assert services.emails_da_coordenacao() == []
