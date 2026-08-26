from django.core.management.base import BaseCommand

from apps.contas.models import Usuario


class Command(BaseCommand):
    help = "Cria (ou atualiza a senha do) coordenador inicial do sistema."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--nome", required=True)
        parser.add_argument("--cpf", required=True)
        parser.add_argument("--siape", required=True)
        parser.add_argument("--senha", required=True)

    def handle(self, *args, **opcoes):
        usuario = Usuario.objects.filter(email=opcoes["email"]).first()
        if usuario is None:
            Usuario.objects.create_superuser(
                email=opcoes["email"],
                nome_completo=opcoes["nome"],
                cpf=opcoes["cpf"],
                siape=opcoes["siape"],
                password=opcoes["senha"],
            )
            self.stdout.write(self.style.SUCCESS("Coordenador criado."))
            return
        if usuario.e_coordenador:
            usuario.set_password(opcoes["senha"])
            usuario.save()
            self.stdout.write(self.style.SUCCESS("Coordenador já existia; senha atualizada."))
            return

        # O e-mail já pertence a outra conta (aluno ou professor). Este é o único
        # comando suportado de recuperação de acesso -- roda sob estresse, por
        # alguém trancado para fora do sistema -- então "o e-mail já tem dono" não
        # pode virar silenciosamente "resetei a senha de outra pessoa". Promove
        # essa conta a coordenador explicitamente. Promover implica perder a
        # matrícula: clean() exige matrícula vazia para todo papel != ALUNO, e
        # save() (full_clean() por baixo) recusa a gravação caso contrário --
        # portanto, se a promoção falhar por qualquer outro motivo, ela falha alto
        # (ValidationError), nunca silenciosamente.
        usuario.papel = Usuario.COORDENADOR
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.siape = opcoes["siape"]
        usuario.matricula = None
        usuario.set_password(opcoes["senha"])
        usuario.save()
        self.stdout.write(self.style.SUCCESS("Usuário promovido a coordenador."))
