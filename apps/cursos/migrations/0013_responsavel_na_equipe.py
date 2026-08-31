from django.db import migrations


def por_o_responsavel_na_equipe(apps, schema_editor):
    """Cursos criados antes do Plano 6 tem o responsavel fora da equipe.

    Sem esta migracao a invariante "o responsavel e membro" valeria so para curso
    novo, e todo codigo que confia nela (a consulta de `meus_cursos`, a listagem
    de equipe) trataria os cursos antigos como excecao silenciosa.
    """
    Curso = apps.get_model("cursos", "Curso")
    MembroEquipe = apps.get_model("cursos", "MembroEquipe")
    for curso in Curso.objects.all().iterator():
        # get_or_create, e nao create: a migracao precisa poder rodar num banco
        # onde alguem ja tenha vinculado o responsavel a mao, sem estourar a
        # unicidade de (curso, pessoa).
        MembroEquipe.objects.get_or_create(curso=curso, pessoa_id=curso.professor_responsavel_id)


def tirar_o_responsavel_da_equipe(apps, schema_editor):
    """Reversa: desfaz o que a de ida criou, e nada alem disso.

    Nao apaga membro que nao seja o responsavel; a equipe de alunos nao tem por
    que sumir porque alguem voltou uma migracao.
    """
    Curso = apps.get_model("cursos", "Curso")
    MembroEquipe = apps.get_model("cursos", "MembroEquipe")
    for curso in Curso.objects.all().iterator():
        MembroEquipe.objects.filter(
            curso=curso, pessoa_id=curso.professor_responsavel_id
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("cursos", "0012_membroequipe_pessoa")]
    operations = [
        migrations.RunPython(por_o_responsavel_na_equipe, tirar_o_responsavel_da_equipe)
    ]
