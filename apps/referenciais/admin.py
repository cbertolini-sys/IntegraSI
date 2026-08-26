from django.contrib import admin

from apps.referenciais.models import Categoria, Competencia, Referencial


class CategoriaInline(admin.TabularInline):
    model = Categoria
    extra = 0


@admin.register(Referencial)
class ReferencialAdmin(admin.ModelAdmin):
    list_display = ["nome", "sigla", "min_competencias", "max_competencias", "ativo"]
    list_filter = ["ativo"]
    inlines = [CategoriaInline]


@admin.register(Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "etapa", "categoria", "referencial"]
    list_filter = ["referencial", "etapa", "categoria"]
    search_fields = ["codigo", "descricao"]
