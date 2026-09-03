from django import forms
from django.contrib.auth.forms import (
    AdminUserCreationForm,
    PasswordChangeForm,
    UserChangeForm,
)

from apps.contas.models import Usuario
from apps.contas.validators import somente_digitos


class CamposComPontuacaoMixin(forms.Form):
    """Declara cpf/matricula/siape com espaço para pontuação e normaliza no clean.

    O ModelForm gera esses campos a partir do model com o `max_length`
    exato do model (11 para cpf), e essa validação de tamanho do campo
    roda em `_clean_fields()`, antes do `Usuario.full_clean()` do model
    (onde vive a normalização de pontuação, ver Task 3). Sem esta
    declaração explícita, um CPF digitado com pontuação (14 caracteres)
    é rejeitado por "max 11 caracteres" antes mesmo de chegar lá.
    """

    cpf = forms.CharField(label="CPF", max_length=14, help_text="Com ou sem pontuação.")
    matricula = forms.CharField(label="Matrícula", max_length=20, required=False)
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


class CadastroDeProfessorForm(forms.Form):
    """O e-mail, e mais nada.

    A coordenação não digita nome, CPF nem SIAPE: quem tem esses dados é a própria
    pessoa, e ela os informa no primeiro acesso. Pedi-los aqui seria a coordenação
    transcrevendo documento alheio, e um erro de digitação viraria conta errada.
    """

    email = forms.EmailField(
        label="E-mail do professor",
        help_text="A pessoa recebe um convite neste endereço e completa o "
        "cadastro com nome, CPF e SIAPE ao entrar pela primeira vez.",
    )


class PerfilForm(forms.ModelForm):
    """Os dados que a própria pessoa mantém.

    `ModelForm` de `Usuario`, e não formulário solto como o do convite, porque
    aqui a instância é conhecida e é sempre `request.user`: a view a passa, e o
    POST não tem como trocá-la. `Meta.fields` é a cerca que impede o resto -- um
    `papel` ou um `is_superuser` chegando pelo POST não encontra campo onde
    entrar, e é ignorado antes de virar dado.

    `email` fica de fora de propósito: é a credencial de acesso, e trocá-la
    sozinho é trocar de conta.
    """

    # Declarado à mão, e não gerado do modelo, por dois motivos que andam juntos.
    # O `max_length` do modelo é 11 e recusaria o CPF pontuado antes que a
    # normalização rodasse (o mesmo motivo de `CamposComPontuacaoMixin`). E o
    # widget precisa nascer VAZIO: interpolar o número gravado imprimiria o
    # documento na página e no cache do navegador, que é justamente o que a
    # máscara ao lado evita.
    cpf = forms.CharField(
        label="Corrigir o CPF",
        max_length=14,
        required=False,
        help_text="Deixe em branco para manter o que está gravado. "
        "Digite o número inteiro apenas se precisar corrigi-lo.",
    )

    class Meta:
        model = Usuario
        fields = ("nome_completo", "cpf", "matricula", "siape", "telefone")
        help_texts = {
            "nome_completo": "Como seu nome deve aparecer nos cursos que você produz.",
            "matricula": "Sua matrícula na UFSM, só os números.",
            "siape": "Seu número SIAPE, o registro funcional de servidor.",
            "telefone": "Com DDD. É por onde a coordenação fala com você.",
        }

    # Matrícula é do aluno e SIAPE é do professor: `Usuario.clean()` recusa cada
    # um no papel errado, e deixá-los na tela só produziria erro depois de a
    # pessoa preencher tudo.
    CAMPOS_DO_ALUNO = ("nome_completo", "cpf", "matricula", "telefone")
    CAMPOS_DO_PROFESSOR = ("nome_completo", "cpf", "siape", "telefone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pessoa = self.instance
        permitidos = (
            self.CAMPOS_DO_ALUNO if pessoa.e_aluno else self.CAMPOS_DO_PROFESSOR
        )
        for nome in list(self.fields):
            if nome not in permitidos:
                del self.fields[nome]
        # O widget nasce vazio mesmo com instancia. Declarar o campo a mao nao
        # basta: o `ModelForm` preenche `initial` a partir da instancia para todo
        # campo de `Meta.fields`, e o CPF gravado ia parar no `value=` do HTML -
        # exatamente o que a mascara ao lado existe para evitar.
        self.initial["cpf"] = ""
        self.fields["nome_completo"].required = True
        # O telefone só é exigido do aluno: `perfil_completo` não o cobra do
        # professor, e cobrá-lo aqui trancaria a tela para quem entrou sem ele.
        self.fields["telefone"].required = pessoa.e_aluno

    def clean_cpf(self):
        """Em branco mantém o que está gravado.

        Sem chamar `valida_cpf` aqui, de propósito. `valida_cpf` já é validador do
        campo no modelo, e o `_post_clean` do `ModelForm` roda o `full_clean()` da
        instância e devolve o erro pendurado no campo `cpf` deste formulário --
        exatamente onde a pessoa precisa vê-lo. Repetir a chamada seria uma segunda
        guarda para o mesmo resultado, do tipo que nenhum teste consegue distinguir
        da primeira (CLAUDE.md, Testes). O `PrimeiroAcessoForm` chama porque é
        `forms.Form` e não tem `_post_clean` nenhum.
        """
        digitado = somente_digitos(self.cleaned_data.get("cpf"))
        if not digitado:
            return self.instance.cpf
        return digitado


class TrocaDeSenhaForm(PasswordChangeForm):
    """O formulário do Django, com a ajuda que este projeto exige de todo campo.

    Subclasse em vez de uso direto: `tests/test_ajuda.py` só varre os formulários
    declarados nos nossos apps, então o do Django entraria na tela sem tooltip
    nenhum e sem nada cobrando isso.
    """

    # `user=None` porque `PasswordChangeForm` o exige posicionalmente e a varredura
    # de `tests/test_ajuda.py` instancia todo formulario sem argumento nenhum. Sem
    # o padrao, a varredura quebraria e a exigencia de ajuda morreria junto.
    def __init__(self, user=None, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        # O `PasswordChangeForm` do Django marca `autofocus` na senha atual, e este
        # formulário mora no SEGUNDO cartão da tela: abrir "Meu perfil" jogava o
        # foco e a rolagem por cima de "Seus dados", direto na caixa de senha.
        # Quem chega ali vem ver os próprios dados, não trocar a senha.
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.fields["old_password"].help_text = (
            "A senha com que você entrou. Serve para confirmar que é você."
        )
        self.fields["new_password1"].help_text = (
            "Pelo menos 8 caracteres, e nada de sequência óbvia ou do seu próprio nome."
        )
        self.fields["new_password2"].help_text = "Repita a senha nova, para conferir."
