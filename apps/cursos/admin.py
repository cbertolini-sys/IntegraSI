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
    # Ate o Plano 6 este era o UNICO lugar do sistema que gravava
    # Curso.competencias, e o comentario aqui dizia "ate essa tela existir". A
    # tela existe: FichaCursoForm inclui competencias, e a equipe as escolhe pela
    # ficha do curso. O registro fica assim mesmo por outro motivo, que continua
    # valendo: a ficha congela quando o curso sai de producao (spec 4.5), e e por
    # aqui que a coordenacao corrige um curso ja publicado sem abrir nova versao.
    list_display = ["titulo", "professor_responsavel", "status", "publicado_em", "referencial"]
    list_filter = ["status", "formato", "tipo_publico", "referencial"]
    search_fields = ["titulo"]
    filter_horizontal = ["competencias", "temas"]
    # R56: so services.py move status de Curso (convencao registrada no CLAUDE.md).
    # Sem readonly_fields aqui, o formulario do Admin expunha "status" como campo
    # editavel comum, deixando o coordenador pular publicar_curso/devolver_curso
    # (e o LogTransicaoCurso e a notificacao que eles gravam) so preenchendo o
    # select. E sem has_add_permission=False, "Adicionar curso" pelo Admin criava
    # um Curso sem passar por services.criar_curso - portanto sem os seis
    # Entregavel que o resto do sistema pressupoe que todo curso tem.
    # Mesmo motivo do status, estendido pelo Plano 4: raiz/versao/motivo_versao sao
    # a linhagem (spec 4.5), e quem os escreve e services.abrir_nova_versao. Soltos
    # no formulario, um POST do Admin podia mudar a versao de linhagem, criar uma
    # segunda raiz ou renumerar a v2 para v1 - e a invariante "uma versao publicada
    # por linhagem", que o catalogo usa para dispensar DISTINCT ON, sai do ar sem
    # que nenhum service tenha sido chamado.
    readonly_fields = ["status", "raiz", "versao", "motivo_versao"]

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
