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
        help_texts = {
            "nome": "Seu nome completo, para a coordenação saber com quem falar.",
            "email": "Onde a coordenação responde. Confira antes de enviar.",
            "telefone": "Com DDD. Opcional, mas acelera o contato.",
            "instituicao": (
                "Escola, associação ou grupo que vai receber o curso."
            ),
            "num_participantes": (
                "Quantas pessoas devem participar. Um número aproximado já ajuda."
            ),
            "periodo_pretendido": (
                "Quando seria melhor. Ex.: \u201csegunda quinzena de outubro, à "
                "tarde\u201d."
            ),
            "mensagem": (
                "Qualquer coisa que ajude a coordenação a planejar: idade do "
                "grupo, se há laboratório, o que a turma já sabe. Opcional."
            ),
        }

    def e_robo(self):
        return bool(self.data.get("confirmacao"))
