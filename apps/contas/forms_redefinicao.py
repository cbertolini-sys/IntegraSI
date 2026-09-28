from django import forms


class EsqueciSenhaForm(forms.Form):
    """Só o e-mail. Formulário público: quem preenche pode nem ter conta, e a
    tela precisa responder a mesma coisa nos dois casos -- ver
    `apps.contas.services.solicitar_redefinicao_de_senha`."""

    email = forms.EmailField(
        label="E-mail",
        help_text="O e-mail institucional com que você entra no sistema.",
    )


class RedefinirSenhaForm(forms.Form):
    """A senha nova, duas vezes. Mesmo desenho de `PrimeiroAcessoForm`: quem vai
    ser alterado não é escolhido aqui -- vem do token --, então não há
    `ModelForm` nem instância nenhuma para amarrar."""

    senha = forms.CharField(
        label="Nova senha",
        widget=forms.PasswordInput,
        strip=False,
        help_text="Pelo menos 8 caracteres, e nada de sequência óbvia ou do seu próprio nome.",
    )
    confirmacao = forms.CharField(
        label="Repita a senha",
        widget=forms.PasswordInput,
        strip=False,
        help_text="Repita a senha nova, para conferir.",
    )

    def clean(self):
        dados = super().clean()
        if dados.get("senha") and dados.get("senha") != dados.get("confirmacao"):
            self.add_error("confirmacao", "As duas senhas precisam ser iguais.")
        return dados
