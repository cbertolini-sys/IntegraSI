from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.contas.validators import somente_digitos, valida_cpf


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nome_completo, cpf, papel, password=None, **extra):
        if not email:
            raise ValueError("E-mail e obrigatorio.")
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
        "matricula", max_length=20, unique=True, null=True, blank=True
    )
    siape = models.CharField("SIAPE", max_length=20, unique=True, null=True, blank=True)

    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("acessa o admin", default=False)
    date_joined = models.DateTimeField("cadastrado em", auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome_completo", "cpf"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
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
        # Normaliza antes de qualquer validacao: sem isso a unicidade nao vale nada,
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
                erros["matricula"] = "Matricula e obrigatoria para aluno."
            if self.siape:
                erros["siape"] = "Aluno nao tem SIAPE."
        else:
            if not self.siape:
                erros["siape"] = "SIAPE e obrigatorio para professor e coordenador."
            if self.matricula:
                erros["matricula"] = "Professor e coordenador nao tem matricula."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
