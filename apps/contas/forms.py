from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from apps.contas.models import Usuario
from apps.contas.validators import somente_digitos


class CamposComPontuacaoMixin(forms.Form):
    """Declara cpf/matricula/siape com espaco para pontuacao e normaliza no clean.

    O ModelForm gera esses campos a partir do model com o `max_length`
    exato do model (11 para cpf), e essa validacao de tamanho do campo
    roda em `_clean_fields()`, antes do `Usuario.full_clean()` do model
    (onde vive a normalizacao de pontuacao, ver Task 3). Sem esta
    declaracao explicita, um CPF digitado com pontuacao (14 caracteres)
    e rejeitado por "max 11 caracteres" antes mesmo de chegar la.
    """

    cpf = forms.CharField(label="CPF", max_length=14, help_text="Com ou sem pontuacao.")
    matricula = forms.CharField(label="matricula", max_length=20, required=False)
    siape = forms.CharField(label="SIAPE", max_length=20, required=False)

    def clean_cpf(self):
        return somente_digitos(self.cleaned_data["cpf"])

    def clean_matricula(self):
        return somente_digitos(self.cleaned_data["matricula"])

    def clean_siape(self):
        return somente_digitos(self.cleaned_data["siape"])


class UsuarioCreationForm(CamposComPontuacaoMixin, AdminUserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "nome_completo", "cpf", "papel", "matricula", "siape")


class UsuarioChangeForm(CamposComPontuacaoMixin, UserChangeForm):
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
