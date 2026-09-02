"""DEVOLVIDO deixa de ser status de entregavel: as linhas viram RASCUNHO.

Era o mesmo estado funcional de RASCUNHO (os dois `editavel`, nenhuma regra os
distinguindo), e o que ele acrescentava - "voltou com correcoes" - a `Revisao` ja
registra, com autor, data e motivo. Quem quiser saber por que um entregavel esta
com a equipe le o historico, que continua la.

So o dado aqui; o `AlterField` das escolhas fica na migracao seguinte, gerada
pelo Django, para que cada arquivo diga uma coisa so.

A volta e `noop` de proposito: desfeita a fusao, nao ha como saber quais linhas
eram DEVOLVIDO, porque a informacao que as distinguia nunca esteve nesta coluna.
"""

from django.db import migrations


def devolvidos_viram_rascunho(apps, schema_editor):
    Entregavel = apps.get_model("cursos", "Entregavel")
    Entregavel.objects.filter(status="DEVOLVIDO").update(status="RASCUNHO")


class Migration(migrations.Migration):
    dependencies = [("cursos", "0016_entregavel_de_avaliacao")]

    operations = [
        migrations.RunPython(devolvidos_viram_rascunho, migrations.RunPython.noop),
    ]
