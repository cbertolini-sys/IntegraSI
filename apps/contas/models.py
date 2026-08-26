from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.contas.validators import somente_digitos, valida_cpf


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nome_completo, cpf, papel, password=None, **extra):
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

    nome_completo = models.CharField("nome completo", max_length=150)
    email = models.EmailField("e-mail", unique=True)
    cpf = models.CharField("CPF", max_length=11, unique=True, validators=[valida_cpf])
    papel = models.CharField("papel", max_length=20, choices=PAPEIS)
    matricula = models.CharField(
        "matrícula", max_length=20, unique=True, null=True, blank=True
    )
    siape = models.CharField("SIAPE", max_length=20, unique=True, null=True, blank=True)

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
        return self.papel == self.COORDENADOR

    @property
    def e_professor(self):
        return self.papel == self.PROFESSOR

    @property
    def e_aluno(self):
        return self.papel == self.ALUNO

    def full_clean(self, *args, **kwargs):
        # Normaliza antes de qualquer validação: sem isso a unicidade não vale nada,
        # porque 529.982.247-25 e 52998224725 conviveriam no banco (spec 4.1).
        self.cpf = somente_digitos(self.cpf)
        self.matricula = somente_digitos(self.matricula) or None
        self.siape = somente_digitos(self.siape) or None
        super().full_clean(*args, **kwargs)

    def clean(self):
        super().clean()
        erros = {}
        if self.e_aluno:
            if not self.matricula:
                erros["matricula"] = "Matrícula é obrigatória para aluno."
            if self.siape:
                erros["siape"] = "Aluno não tem SIAPE."
        else:
            if not self.siape:
                erros["siape"] = "SIAPE é obrigatório para professor e coordenador."
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
