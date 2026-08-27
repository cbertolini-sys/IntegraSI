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
        queryset=Usuario.objects.filter(papel=Usuario.PROFESSOR, is_active=True),
        label="professor responsável",
    )

    class Meta:
        model = Turma
        fields = ["professor", "data_inicio", "data_fim", "local", "vagas", "observacoes"]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
        }
