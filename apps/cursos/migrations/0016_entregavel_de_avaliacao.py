from django.db import migrations


def criar_a_avaliacao(apps, schema_editor):
    """Cursos criados antes do sexto entregavel ficaram sem ele.

    Sem esta migracao, `pronto_para_o_coordenador` compara aprovados com SEIS e
    nenhum curso antigo jamais chegaria a coordenacao: eles so tem cinco
    entregaveis para aprovar. A falha seria silenciosa, porque a tela apenas
    deixaria de oferecer o botao de submeter.
    """
    Curso = apps.get_model("cursos", "Curso")
    Entregavel = apps.get_model("cursos", "Entregavel")
    for curso in Curso.objects.all().iterator():
        # get_or_create e nao create: a unicidade e por (curso, tipo), e a
        # migracao precisa poder rodar num banco onde alguem ja tenha criado o
        # entregavel a mao.
        Entregavel.objects.get_or_create(
            curso=curso, tipo="AVALIACAO", defaults={"status": "RASCUNHO"}
        )


def apagar_a_avaliacao(apps, schema_editor):
    """Reversa: so o entregavel de avaliacao, e so se estiver vazio.

    Um entregavel com anexo guarda trabalho de alguem, e voltar uma migracao nao
    e motivo para apagar trabalho. Se houver anexo, a reversa deixa como esta.
    """
    Entregavel = apps.get_model("cursos", "Entregavel")
    for entregavel in Entregavel.objects.filter(tipo="AVALIACAO").iterator():
        if not entregavel.anexos.exists() and not entregavel.secoes.exists():
            entregavel.delete()


class Migration(migrations.Migration):
    dependencies = [("cursos", "0015_tipo_de_entregavel")]
    operations = [migrations.RunPython(criar_a_avaliacao, apagar_a_avaliacao)]
