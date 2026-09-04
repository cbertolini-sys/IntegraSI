from django import forms

from apps.catalogo.models import Solicitacao, SugestaoDeCurso


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


class SugestaoForm(forms.ModelForm):
    """Demanda por um curso que ainda nao existe.

    Espelha o `SolicitacaoForm` no que e defesa (honeypot, mesma recusa silenciosa
    a robo) e diverge no que e conteudo: aqui nao ha curso, entao nao ha periodo
    pretendido nem numero de participantes. Pedir participantes previstos de um
    curso que nao existe seria precisao falsa: quem responde planejaria em cima de
    um numero que ninguem teve como estimar.
    """

    confirmacao = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = SugestaoDeCurso
        fields = [
            "nome", "email", "telefone", "instituicao",
            "publico_alvo", "tem_laboratorio", "demanda",
        ]
        widgets = {
            "demanda": forms.Textarea(attrs={"rows": 6, "maxlength": 2000}),
            "tem_laboratorio": forms.RadioSelect,
        }
        help_texts = {
            "nome": "Seu nome completo, para a coordenação saber com quem falar.",
            "email": "Onde a coordenação responde. Confira antes de enviar.",
            "telefone": "Com DDD. Opcional, mas acelera o contato.",
            "instituicao": "Escola, associação ou grupo que receberia o curso.",
            "publico_alvo": (
                "Quem participaria. Ex.: \u201cturmas de 4º e 5º ano\u201d, "
                "\u201cprofessores da rede municipal\u201d, \u201cpais e "
                "responsáveis\u201d."
            ),
            "tem_laboratorio": (
                "Se o grupo tem computadores disponíveis. Isso muda o curso que dá "
                "para oferecer, e não impede nada: há cursos que funcionam sem tela."
            ),
            "demanda": (
                "O que a sua comunidade precisa aprender, com o máximo de detalhe "
                "que puder dar. Quanto mais concreto, maior a chance de virar curso."
            ),
        }

    def e_robo(self):
        return bool(self.data.get("confirmacao"))
