from django.contrib import admin

from apps.turmas.models import Participante, Turma


class ParticipanteInline(admin.TabularInline):
    # Participante só existe por aqui: uma tela própria no Admin daria ao professor
    # a lista inteira de participantes, contornando o recorte por turma do
    # get_queryset abaixo (spec 10).
    model = Participante
    extra = 0


@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ["curso", "local", "data_inicio", "professor", "status"]
    list_filter = ["status", "data_inicio"]
    inlines = [ParticipanteInline]
    # "status" fica editável de propósito, ao contrário de CursoAdmin: a convenção
    # de R56 (só services.py move status) existe para impedir que se pule lógica de
    # domínio, e aqui não há nenhuma - AGENDADA -> EM_ANDAMENTO -> CONCLUIDA é do
    # módulo de execução futuro (spec 1.1). Torná-lo readonly agora deixaria o
    # campo sem nenhuma forma de ser mudado.

    def get_queryset(self, request):
        """Professor não vê turma alheia, e por consequência não vê os
        participantes dela (spec 10)."""
        queryset = super().get_queryset(request)
        if request.user.e_coordenador or request.user.is_superuser:
            return queryset
        return queryset.filter(professor=request.user)
