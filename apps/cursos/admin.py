from django.contrib import admin

from apps.cursos.models import Curso, Tema


@admin.register(Tema)
class TemaAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug", "ativo"]
    list_filter = ["ativo"]
    search_fields = ["nome"]
    prepopulated_fields = {"slug": ("nome",)}


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
