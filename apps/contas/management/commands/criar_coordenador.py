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
        usuario.set_password(opcoes["senha"])
        usuario.save()
        self.stdout.write(self.style.SUCCESS("Coordenador ja existia; senha atualizada."))
