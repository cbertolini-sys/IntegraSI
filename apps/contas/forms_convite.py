from django import forms

from apps.contas.validators import valida_cpf


class PrimeiroAcessoForm(forms.Form):
    """Os quatro dados que o aluno traz no primeiro acesso.

    Formulário simples, e não `ModelForm` de `Usuario`: o objeto que vai ser
    alterado não é escolhido aqui -- vem do token --, e um `ModelForm` teria de
    receber a instância antes de validar, o que abriria a porta para editar outra
    pessoa mudando um campo escondido.
    """

    senha = forms.CharField(label="Crie sua senha", widget=forms.PasswordInput, strip=False)
    confirmacao = forms.CharField(
        label="Repita a senha", widget=forms.PasswordInput, strip=False
    )
    cpf = forms.CharField(label="CPF", max_length=14)
    matricula = forms.CharField(label="Matrícula", max_length=20)
    telefone = forms.CharField(label="Telefone", max_length=20)

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
