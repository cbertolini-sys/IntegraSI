import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Renomeia MembroEquipe.aluno para MembroEquipe.pessoa.

    Escrita a mao, e nao por makemigrations. O autodetector so oferece renomear um
    campo quando ele e identico afora o nome, e aqui o verbose_name mudou de
    "aluno" para "pessoa" na mesma passada; sem o renome ele geraria RemoveField +
    AddField, que apagaria a equipe de todos os cursos.

    A constraint sai antes e volta depois porque nomeia a coluna antiga.
    """

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cursos", "0011_curso_uma_numeracao_por_linhagem"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="membroequipe", name="membro_unico_por_curso"),
        migrations.RenameField(model_name="membroequipe", old_name="aluno", new_name="pessoa"),
        migrations.AlterField(
            model_name="membroequipe",
            name="pessoa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="equipes",
                to=settings.AUTH_USER_MODEL,
                verbose_name="pessoa",
            ),
        ),
        migrations.AlterModelOptions(
            name="membroequipe",
            options={
                "ordering": ["pessoa__nome_completo"],
                "verbose_name": "membro da equipe",
                "verbose_name_plural": "membros da equipe",
            },
        ),
        migrations.AddConstraint(
            model_name="membroequipe",
            constraint=models.UniqueConstraint(
                fields=("curso", "pessoa"), name="membro_unico_por_curso"
            ),
        ),
    ]
