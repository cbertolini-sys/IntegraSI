from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from apps.contas.models import Usuario


class UsuarioCreationForm(AdminUserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "nome_completo", "cpf", "papel", "matricula", "siape")


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = (
            "email",
            "nome_completo",
            "cpf",
            "papel",
            "matricula",
            "siape",
            "is_active",
            "is_staff",
        )
