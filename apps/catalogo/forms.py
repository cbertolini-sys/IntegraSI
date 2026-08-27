from django import forms

from apps.catalogo.models import Solicitacao


class SolicitacaoForm(forms.ModelForm):
    # Campo invisível para pessoas. Robô preenche tudo que encontra; se vier
    # preenchido, descartamos em silêncio (spec 10).
    confirmacao = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Solicitacao
        fields = [
            "nome", "email", "telefone", "instituicao",
            "num_participantes", "periodo_pretendido", "mensagem",
        ]
        widgets = {"mensagem": forms.Textarea(attrs={"rows": 5, "maxlength": 2000})}

    def e_robo(self):
        return bool(self.data.get("confirmacao"))
