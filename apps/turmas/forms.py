from django import forms

from apps.contas.models import Usuario
from apps.turmas.models import Turma


class TurmaForm(forms.ModelForm):
    """Agendamento da turma que nasce de uma solicitação aceita.

    `curso` e `solicitacao` ficam de fora de propósito: quem os preenche é
    services.aceitar_solicitacao, a partir da solicitação que está sendo
    respondida. Deixá-los no formulário permitiria agendar a turma de um curso
    para a solicitação de outro.
    """

    professor = forms.ModelChoiceField(
        # Só professor conduz turma (Turma.clean). Restringir aqui é conveniência
        # de tela, não a guarda: a guarda é a do model, e continua valendo para
        # quem chamar o serviço direto.
        #
        # O coordenador entra na lista a partir do Plano 5 porque ele é professor
        # (regra 1) e `Turma.clean` passou a aceitá-lo. Filtrar só por PROFESSOR
        # aqui deixaria o formulário mais estrito que o modelo, e a coordenação
        # não conseguiria designar a si mesma para conduzir uma turma.
        queryset=Usuario.objects.filter(
            papel__in=[Usuario.PROFESSOR, Usuario.COORDENADOR], is_active=True
        ),
        help_text="Quem conduz esta turma. Coordenação também pode conduzir.",
        label="professor responsável",
    )

    class Meta:
        model = Turma
        fields = ["professor", "data_inicio", "data_fim", "local", "vagas", "observacoes"]
        help_texts = {
            "data_inicio": "Primeiro encontro da turma.",
            "data_fim": "Último encontro. Pode ser igual ao primeiro, numa oficina de um dia.",
            "local": (
                "Onde a turma acontece. Ex.: \u201cLaboratório 2 da EMEF Santa "
                "Rita\u201d. Em curso online, o endereço da sala virtual."
            ),
            "vagas": "Quantas pessoas cabem nesta turma.",
            "observacoes": (
                "Combinados com a instituição: material a levar, horário, "
                "estacionamento. Opcional."
            ),
        }
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
        }
