from django import forms

from apps.contas.validators import valida_cpf


class PrimeiroAcessoForm(forms.Form):
    """Os dados que a pessoa traz no primeiro acesso.

    Formulário simples, e não `ModelForm` de `Usuario`: o objeto que vai ser
    alterado não é escolhido aqui -- vem do token --, e um `ModelForm` teria de
    receber a instância antes de validar, o que abriria a porta para editar outra
    pessoa mudando um campo escondido.

    As duas contas nascem só com o e-mail, e é aqui que a própria pessoa escreve
    o resto. Os campos diferem pelo papel: o aluno informa matrícula e telefone,
    o professor informa SIAPE. É esta tela que os exige, e não o modelo -- se o
    modelo os exigisse, nenhuma das duas contas poderia ser criada.
    """

    senha = forms.CharField(label="Crie sua senha", widget=forms.PasswordInput, strip=False)
    confirmacao = forms.CharField(
        label="Repita a senha", widget=forms.PasswordInput, strip=False
    )
    nome_completo = forms.CharField(label="Nome completo", max_length=150)
    cpf = forms.CharField(label="CPF", max_length=14)
    matricula = forms.CharField(label="Matrícula", max_length=20)
    siape = forms.CharField(label="SIAPE", max_length=20)
    telefone = forms.CharField(label="Telefone", max_length=20)

    # Cada papel só vê o que lhe cabe. Deixar matrícula na tela do professor não
    # seria só ruído: `Usuario.clean()` recusa professor com matrícula, e o erro
    # apareceria depois de a pessoa preencher tudo.
    CAMPOS_DO_ALUNO = (
        "senha", "confirmacao", "nome_completo", "cpf", "matricula", "telefone",
    )
    CAMPOS_DO_PROFESSOR = ("senha", "confirmacao", "nome_completo", "cpf", "siape", "telefone")

    def __init__(self, *args, e_aluno=True, **kwargs):
        super().__init__(*args, **kwargs)
        permitidos = self.CAMPOS_DO_ALUNO if e_aluno else self.CAMPOS_DO_PROFESSOR
        for nome in list(self.fields):
            if nome not in permitidos:
                del self.fields[nome]
        # O telefone da ficha do professor e opcional: `perfil_completo` nao o
        # cobra dele, so do aluno.
        if not e_aluno:
            self.fields["telefone"].required = False

    def clean_cpf(self):
        cpf = self.cleaned_data["cpf"]
        # Validado aqui além do modelo porque o erro do modelo só apareceria
        # depois do save(), como erro geral; aqui a pessoa vê no campo do CPF.
        valida_cpf("".join(c for c in cpf if c.isdigit()))
        return cpf

    def clean(self):
        dados = super().clean()
        if dados.get("senha") and dados.get("senha") != dados.get("confirmacao"):
            self.add_error("confirmacao", "As duas senhas precisam ser iguais.")
        return dados
