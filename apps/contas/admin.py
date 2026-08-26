from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.contas.forms import UsuarioChangeForm, UsuarioCreationForm
from apps.contas.models import Usuario


def mascara_cpf(cpf):
    """Mostra só os três últimos dígitos e o verificador (spec 10)."""
    if not cpf:
        return ""
    return f"***.***.{cpf[6:9]}-{cpf[9:11]}"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    ordering = ["nome_completo"]
    list_display = ["nome_completo", "email", "papel", "cpf_mascarado", "is_active"]
    list_filter = ["papel", "is_active"]
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
        return mascara_cpf(obj.cpf)
