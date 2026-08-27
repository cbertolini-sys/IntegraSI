from django.contrib import admin

from apps.cursos.models import Curso, Tema


@admin.register(Tema)
class TemaAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug", "ativo"]
    list_filter = ["ativo"]
    search_fields = ["nome"]
    prepopulated_fields = {"slug": ("nome",)}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.cursos.services import atualizar_vetor_temas

        # Renomear um Tema muda o texto que vetor_temas guarda para cada curso
        # ligado a ele; sem reindexar aqui, a busca continuaria encontrando os
        # cursos pelo nome antigo do tema (ou deixaria de encontrar pelo novo).
        for curso in obj.cursos.all():
            atualizar_vetor_temas(curso)


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    # Desbloqueio barato, nao a tela de edicao de curso do Plano 3: sem isto, nada
    # no sistema grava Curso.competencias (CursoForm exclui o campo de proposito -
    # depende do referencial escolhido), entao um curso com referencial BNCC fica
    # para sempre preso na faixa de competencias do Plano de Ensino (item 3 da
    # revisao de branco). O Admin e a ferramenta do coordenador ate essa tela
    # existir.
    list_display = ["titulo", "professor_responsavel", "edicao", "status", "referencial"]
    list_filter = ["status", "formato", "tipo_publico", "referencial"]
    search_fields = ["titulo"]
    filter_horizontal = ["competencias", "temas"]
    # R56: so services.py move status de Curso (convencao registrada no CLAUDE.md).
    # Sem readonly_fields aqui, o formulario do Admin expunha "status" como campo
    # editavel comum, deixando o coordenador pular publicar_curso/devolver_curso
    # (e o LogTransicaoCurso e a notificacao que eles gravam) so preenchendo o
    # select. E sem has_add_permission=False, "Adicionar curso" pelo Admin criava
    # um Curso sem passar por services.criar_curso - portanto sem os cinco
    # Entregavel que o resto do sistema pressupoe que todo curso tem.
    readonly_fields = ["status"]

    def has_add_permission(self, request):
        return False

    def save_related(self, request, form, formsets, change):
        # save_related, nao save_model: o M2M (inclusive "temas", via
        # filter_horizontal) so existe depois que o ModelAdmin grava as relacoes
        # aqui - em save_model o form.instance.temas ainda esta vazio, e
        # reindexar la reindexaria para nada. Sem este hook, associar um tema a
        # um curso pelo Admin escreve Curso.temas pelo form.save_m2m() padrao do
        # Django, a mesma escrita direta que nova_proposta fazia antes do fix
        # deste mesmo defeito na view - so que por esta porta e o coordenador,
        # nao o professor, quem fica com o curso invisivel na busca por tema.
        super().save_related(request, form, formsets, change)
        from apps.cursos.services import atualizar_vetor_temas

        atualizar_vetor_temas(form.instance)
