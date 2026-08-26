import pytest
from django.core.exceptions import ValidationError

from apps.cursos.models import MembroEquipe


@pytest.mark.django_db
def test_membro_e_vinculado_ao_curso(curso, aluno):
    MembroEquipe.objects.create(curso=curso, aluno=aluno)
    assert curso.membros.count() == 1
    assert curso.tem_membro(aluno)


@pytest.mark.django_db
def test_mesmo_aluno_duas_vezes_e_recusado(curso, aluno):
    MembroEquipe.objects.create(curso=curso, aluno=aluno)
    with pytest.raises(ValidationError):
        MembroEquipe.objects.create(curso=curso, aluno=aluno)


@pytest.mark.django_db
def test_professor_nao_pode_ser_membro_da_equipe(curso, professor):
    with pytest.raises(ValidationError):
        MembroEquipe.objects.create(curso=curso, aluno=professor)


@pytest.mark.django_db
def test_quem_nao_e_membro_nao_e_reconhecido(curso, aluno, outro_aluno):
    MembroEquipe.objects.create(curso=curso, aluno=aluno)
    assert curso.tem_membro(outro_aluno) is False
