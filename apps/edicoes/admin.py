from django.contrib import admin

from apps.edicoes.models import Edicao


@admin.register(Edicao)
class EdicaoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "descricao", "data_inicio", "data_fim", "ativa"]
    list_filter = ["ativa"]
    search_fields = ["codigo", "descricao"]
