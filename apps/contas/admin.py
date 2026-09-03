from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.contas.forms import UsuarioChangeForm, UsuarioCreationForm
from apps.contas.models import ConviteAluno, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    ordering = ["nome_completo"]
    list_display = ["nome_completo", "email", "papel", "cpf_mascarado", "is_active"]
    list_filter = ["papel", "is_active"]
    # `cpf` fica de fora de propósito: buscar por CPF no Admin devolveria o
    # número na URL e nos registros de acesso do servidor. `matricula` e
    # `siape` ficam dentro, também de propósito -- ao contrário do CPF, são
    # identificadores internos da instituição, não um documento nacional, e o
    # coordenador legitimamente precisa achar um aluno pela matrícula. Não
    # "conserte" isso em nenhuma das duas direções.
    search_fields = ["nome_completo", "email", "matricula", "siape"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identificação", {"fields": ("nome_completo", "cpf", "papel", "matricula", "siape")}),
        ("Acesso", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "nome_completo",
                    "cpf",
                    "papel",
                    "matricula",
                    "siape",
                    "password1",
                    "password2",
                    "usable_password",
                ),
            },
        ),
    )

    @admin.display(description="CPF")
    def cpf_mascarado(self, obj):
        return obj.cpf_mascarado


@admin.register(ConviteAluno)
class ConviteAlunoAdmin(admin.ModelAdmin):
    """Somente leitura: o convite nasce por `services.convidar` e morre por
    `consumir_convite`. Editar o prazo ou marcar como usado pela mão contornaria
    as duas regras que ele existe para ter -- uso único e sete dias.

    Sem `readonly_fields`: com `has_change_permission` False o Django já renderiza
    tudo em leitura e recusa o POST. Somar as duas coisas criaria o par
    indistinguível que a CLAUDE.md descreve -- apagar a permissão sozinha deixaria
    um teste ingênuo verde.
    """

    list_display = ["usuario", "criado_por", "criado_em", "expira_em", "usado_em"]
    list_filter = ["usado_em"]
    search_fields = ["usuario__nome_completo", "usuario__email"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
