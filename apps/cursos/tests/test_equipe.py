import pytest
from django.core.exceptions import ValidationError

from apps.cursos.models import MembroEquipe


@pytest.mark.django_db
def test_membro_e_vinculado_ao_curso(curso, aluno):
    MembroEquipe.objects.create(curso=curso, pessoa=aluno)
    assert curso.membros.count() == 1
    assert curso.tem_membro(aluno)


@pytest.mark.django_db
def test_mesma_pessoa_duas_vezes_e_recusada(curso, aluno):
    MembroEquipe.objects.create(curso=curso, pessoa=aluno)
    with pytest.raises(ValidationError):
        MembroEquipe.objects.create(curso=curso, pessoa=aluno)


@pytest.mark.django_db
def test_professor_pode_ser_membro_da_equipe(curso, outro_professor):
    """A regra que este plano inverte: a equipe de producao passa a aceitar
    professor, que produz material como qualquer membro (spec 4.1)."""
    MembroEquipe.objects.create(curso=curso, pessoa=outro_professor)
    assert curso.tem_membro(outro_professor)


@pytest.mark.django_db
def test_coordenador_pode_ser_membro_da_equipe(curso, coordenador):
    """Coordenador e professor (regra 1 do Plano 5), entao entra pela mesma porta."""
    MembroEquipe.objects.create(curso=curso, pessoa=coordenador)
    assert curso.tem_membro(coordenador)


@pytest.mark.django_db
def test_quem_nao_e_membro_nao_e_reconhecido(curso, aluno, outro_aluno):
    MembroEquipe.objects.create(curso=curso, pessoa=aluno)
    assert curso.tem_membro(outro_aluno) is False
