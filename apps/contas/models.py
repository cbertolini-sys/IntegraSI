from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.contas.validators import somente_digitos, valida_cpf


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nome_completo, papel, cpf=None, password=None, **extra):
        if not email:
            raise ValueError("E-mail é obrigatório.")
        usuario = self.model(
            email=self.normalize_email(email),
            nome_completo=nome_completo,
            cpf=cpf,
            papel=papel,
            **extra,
        )
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, nome_completo, cpf, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(
            email=email,
            nome_completo=nome_completo,
            cpf=cpf,
            papel=Usuario.COORDENADOR,
            password=password,
            **extra,
        )


class Usuario(AbstractBaseUser, PermissionsMixin):
    COORDENADOR = "COORDENADOR"
    PROFESSOR = "PROFESSOR"
    ALUNO = "ALUNO"
    PAPEIS = [
        (COORDENADOR, "Coordenador"),
        (PROFESSOR, "Professor"),
        (ALUNO, "Aluno"),
    ]

    # `blank=True` porque a coordenacao cadastra professor SO com o e-mail e o
    # proprio informa o nome no primeiro acesso - o mesmo arranjo que o aluno ja
    # tinha com CPF e matricula. Quem exige o nome e a tela do convite, e nao o
    # modelo, senao o cadastro por e-mail seria impossivel.
    nome_completo = models.CharField("nome completo", max_length=150, blank=True)
    email = models.EmailField("e-mail", unique=True)
    cpf = models.CharField(
        "CPF", max_length=11, unique=True, null=True, blank=True, validators=[valida_cpf]
    )
    papel = models.CharField("papel", max_length=20, choices=PAPEIS)
    matricula = models.CharField(
        "matrícula", max_length=20, unique=True, null=True, blank=True
    )
    siape = models.CharField("SIAPE", max_length=20, unique=True, null=True, blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)

    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("acessa o admin", default=False)
    date_joined = models.DateTimeField("cadastrado em", auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    # siape fica de fora de propósito: clean() exige SIAPE para todo papel != ALUNO, então
    # o "manage.py createsuperuser" interativo nunca conseguiria passar por clean() de
    # qualquer forma. A rota suportada é o comando "criar_coordenador" (Task 4), que chama
    # create_superuser(..., siape=...) diretamente. Não "conserte" afrouxando a validação.
    REQUIRED_FIELDS = ["nome_completo", "cpf"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["nome_completo"]

    def __str__(self):
        return self.nome_completo

    @property
    def e_coordenador(self):
        """Nível de acesso Admin: publica curso, organiza turmas e promove
        professores. Ver `apps.cursos.permissions.pode_publicar`."""
        return self.papel == self.COORDENADOR

    @property
    def e_professor(self):
        """Verdadeiro também para o coordenador: todo coordenador é professor
        (regra 1 do Plano 5).

        A herança mora aqui, e não numa segunda coluna, para que exista um lugar
        só onde ela é definida. `papel` continua com um valor por pessoa; quem
        precisa da distinção usa `e_somente_professor`.

        Consequências pretendidas, todas por esta linha: o coordenador cria
        curso (`permissions.pode_criar_curso`), pode ser `professor_responsavel`
        (`Curso.clean`) e pode conduzir turma (`Turma.clean`). As permissões
        escritas como `e_coordenador or (e_professor and ...)` não mudam de
        comportamento -- o `or` já curto-circuitava para o coordenador.
        """
        return self.papel in (self.PROFESSOR, self.COORDENADOR)

    @property
    def e_somente_professor(self):
        """Professor que não é coordenador. Existe para que a distinção tenha um
        nome, em vez de reaparecer como `papel == PROFESSOR` solto pelo código."""
        return self.papel == self.PROFESSOR

    @property
    def e_aluno(self):
        return self.papel == self.ALUNO

    @property
    def identificacao(self):
        """O nome, ou o e-mail quando ainda não há nome.

        A coordenação cadastra professor só com o e-mail (regra desta tela em
        contas/services.criar_professor); `nome_completo` fica vazio até o
        primeiro acesso. Uma mensagem ou um <option> de <select> que interpola
        `nome_completo` direto, sem isto, imprime uma string vazia - frase sem
        sujeito, opção selecionável e invisível. Vale para os dois papéis: aluno
        e professor nascem só com o e-mail, e o nome chega no primeiro acesso.
        """
        return self.nome_completo or self.email

    @property
    def cpf_mascarado(self):
        """Só os três últimos dígitos e o verificador (spec 10).

        Mora aqui, e não no admin, porque agora há dois lugares que a usam: a
        lista do Admin e a tela do próprio perfil. Duas cópias da máscara é uma
        cópia a mais de uma regra de dado pessoal, e a segunda envelhece calada.
        """
        if not self.cpf:
            return ""
        return f"***.***.{self.cpf[6:9]}-{self.cpf[9:11]}"

    @property
    def perfil_completo(self):
        """Tem tudo o que o sistema precisa da pessoa.

        Derivado dos campos, e não de uma coluna `perfil_completo` à parte: uma
        flag paralela é uma segunda fonte de verdade que sai de sincronia na
        primeira edição pelo Admin. Aqui não há o que sincronizar.

        Professor e coordenador tambem passam pelo primeiro acesso desde que a
        coordenacao passou a cadastra-los so com o e-mail. Para eles o telefone
        nao entra na conta: e opcional na tela. O nome entra para os dois, porque
        agora ele pode nascer vazio.
        """
        if not self.nome_completo:
            return False
        if not self.e_aluno:
            return bool(self.cpf and self.siape)
        return bool(self.cpf and self.matricula and self.telefone)

    def full_clean(self, *args, **kwargs):
        # Normaliza antes de qualquer validação: sem isso a unicidade não vale nada,
        # porque 529.982.247-25 e 52998224725 conviveriam no banco (spec 4.1).
        # `or None` também no CPF: ele passou a ser opcional no Plano 5, e string
        # vazia colidiria com string vazia no índice único, enquanto NULL não
        # colide com NULL no Postgres.
        self.cpf = somente_digitos(self.cpf) or None
        self.matricula = somente_digitos(self.matricula) or None
        self.siape = somente_digitos(self.siape) or None
        super().full_clean(*args, **kwargs)

    def clean(self):
        super().clean()
        erros = {}
        if self.e_aluno:
            # Aluno recém-alocado não tem documento nenhum (regra 2 do Plano 5):
            # quem exige os três campos é a tela de primeiro acesso, e não o
            # modelo -- senão a própria alocação por nome e e-mail seria
            # impossível. O que o modelo continua garantindo é a coerência: com
            # CPF, tem de haver matrícula; e aluno nunca tem SIAPE.
            if self.cpf and not self.matricula:
                erros["matricula"] = "Informe a matrícula junto com o CPF."
            if self.siape:
                erros["siape"] = "Aluno não tem SIAPE."
        else:
            # Nem CPF nem SIAPE sao exigidos no cadastro, pelo mesmo motivo do
            # aluno: a coordenacao cria a conta so com o e-mail e a pessoa informa
            # os documentos no primeiro acesso. Quem exige os tres campos e aquela
            # tela; o que o modelo garante e a COERENCIA - com CPF tem de haver
            # SIAPE, e professor nunca tem matricula.
            if self.cpf and not self.siape:
                erros["siape"] = "Informe o SIAPE junto com o CPF."
            if self.matricula:
                erros["matricula"] = "Professor e coordenador não têm matrícula."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # django.contrib.auth chama user.save(update_fields=["last_login"]) a
        # cada login bem-sucedido (ver update_last_login em
        # django.contrib.auth.models). Uma escrita direcionada num objeto já
        # persistido não é lugar para validar o objeto inteiro: os serviços do
        # Plano 2 vão usar save(update_fields=["status"]) pelo mesmo motivo, e
        # sem esta guarda qualquer linha que já esteja inválida no banco (dado
        # legado, ou editado direto) travaria o login com um ValidationError
        # não tratado -- um 500, não um erro de formulário. Ver
        # docs/onde-mora-a-validacao.md.
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)


# Reexportado para que o resto do sistema importe de um lugar so.
from apps.contas.models_convite import ConviteAluno  # noqa: E402,F401


class TentativaDeLogin(models.Model):
    """Uma tentativa de login que falhou, para o limite por IP.

    Guarda o IP e a hora, e mais nada. O e-mail digitado nao entra de proposito:
    a regra conta por IP (girar a lista de enderecos do mesmo lugar nao pode dar
    cota nova), entao o endereco nao serve a nada - e endereco digitado num
    formulario publico pode ser de terceiro ou um erro de digitacao, dado pessoal
    que a regra nao usa. E a mesma linha de raciocinio do CPF fora do
    `search_fields` do Admin.

    Linha velha e lixo: `registrar` apaga o que saiu da janela na mesma passada,
    entao a tabela nao cresce sem limite e nao precisa de rotina de limpeza.
    """

    ip = models.GenericIPAddressField("IP de origem")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "tentativa de login"
        verbose_name_plural = "tentativas de login"
        indexes = [models.Index(fields=["ip", "criado_em"])]

    def __str__(self):
        return f"{self.ip} em {self.criado_em:%d/%m/%Y %H:%M}"
