from django.contrib import messages
import datetime

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.contas import services
from apps.contas.forms import CadastroDeProfessorForm
from apps.contas.forms_convite import PrimeiroAcessoForm
from apps.contas.models import ConviteAluno, TentativaDeLogin, Usuario
from apps.contas.paginacao import paginar
from apps.contas.rede import ip_da_requisicao


# Dez tentativas em quinze minutos. O numero e mais generoso que o da
# solicitacao publica (cinco por hora) porque errar a propria senha algumas vezes
# e comum, e trancar quem digitou errado seria pior que o problema. Ainda assim
# derruba a forca bruta: a lista de e-mails institucionais e adivinhavel, mas
# quarenta tentativas por hora nao quebram senha nenhuma.
LIMITE_DE_TENTATIVAS = 10
JANELA_DE_TENTATIVAS = datetime.timedelta(minutes=15)


class LoginComLimite(LoginView):
    """O `LoginView` do Django, com limite de tentativas por IP.

    Conta por IP e ignora o e-mail tentado: sem isso, quem gira a lista de
    enderecos do mesmo lugar ganha cota nova a cada endereco.

    O GET nunca e bloqueado - trancar a propria tela deixaria a pessoa sem nem
    ler a mensagem que explica o bloqueio.
    """

    def post(self, request, *args, **kwargs):
        if self._excedeu(request):
            return self.render_to_response(
                self.get_context_data(
                    form=self.get_form(),
                    # A mesma resposta para conta que existe e conta que nao
                    # existe: a diferenca seria um oraculo de enderecos validos.
                    erro="Muitas tentativas deste endereço. Tente novamente mais tarde.",
                )
            )
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        self._registrar(self.request)
        return super().form_invalid(form)

    def _excedeu(self, request):
        desde = timezone.now() - JANELA_DE_TENTATIVAS
        return (
            TentativaDeLogin.objects.filter(
                ip=ip_da_requisicao(request), criado_em__gte=desde
            ).count()
            >= LIMITE_DE_TENTATIVAS
        )

    def _registrar(self, request):
        ip = ip_da_requisicao(request)
        TentativaDeLogin.objects.create(ip=ip)
        # Limpa o que saiu da janela na mesma passada: a tabela so guarda o que a
        # regra ainda le, e nao precisa de rotina de limpeza.
        TentativaDeLogin.objects.filter(
            ip=ip, criado_em__lt=timezone.now() - JANELA_DE_TENTATIVAS
        ).delete()


@require_http_methods(["GET", "POST"])
def primeiro_acesso(request, token):
    """Tela do convite: cria a senha e completa o cadastro.

    Aberta sem login de proposito -- quem chega aqui ainda nao tem senha. O token
    e a credencial, e `consumir_convite` e quem confere se ele ainda vale.
    """
    convite = ConviteAluno.objects.filter(token=token).first()
    if convite is None or not convite.valido:
        return render(request, "contas/convite_invalido.html")

    form = PrimeiroAcessoForm(request.POST or None, e_aluno=convite.usuario.e_aluno)
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        try:
            # `.get()` e nao `[...]`: o campo que nao e daquele papel foi apagado
            # do formulario, e o `None` diz ao servico para nao tocar nele.
            usuario = services.consumir_convite(
                token,
                senha=dados["senha"],
                cpf=dados["cpf"],
                matricula=dados.get("matricula"),
                telefone=dados.get("telefone", ""),
                nome=dados.get("nome_completo"),
                siape=dados.get("siape"),
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                form.add_error(None, mensagem)
        else:
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("painel")

    return render(
        request, "contas/primeiro_acesso.html", {"form": form, "convite": convite}
    )


@login_required
@require_http_methods(["GET", "POST"])
def pessoas(request):
    """Quem e professor, quem e coordenacao, e o botao para mudar isso."""
    # Checagem local pelo mesmo motivo de `_garante_coordenacao`: `contas` nao
    # importa `cursos`.
    if not request.user.e_coordenador:
        raise PermissionDenied("Área da coordenação.")

    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "CRIAR_PROFESSOR":
            # Antes do `get_object_or_404`: este ramo nao tem pessoa alvo, e cair
            # naquela linha daria 404 no lugar da tela de erro.
            cadastro = CadastroDeProfessorForm(request.POST)
            if not cadastro.is_valid():
                for mensagem in cadastro.errors.get("email", ["E-mail inválido."]):
                    messages.error(request, mensagem)
                return redirect("pessoas")
            try:
                criado = services.criar_professor(
                    cadastro.cleaned_data["email"],
                    por=request.user,
                    base_url=request.build_absolute_uri("/").rstrip("/"),
                )
            except ValidationError as erro:
                for mensagem in erro.messages:
                    messages.error(request, mensagem)
            else:
                messages.success(
                    request,
                    f"Convite enviado para {criado.email}. "
                    "Ele completa o cadastro no primeiro acesso.",
                )
            return redirect("pessoas")

        if not request.POST.get("usuario"):
            # Acao desconhecida e sem pessoa alvo. Sem esta linha cairia no
            # `get_object_or_404` com `pk=None` e a tela devolveria 404, como se a
            # pagina nao existisse.
            messages.error(request, "Ação não reconhecida.")
            return redirect("pessoas")

        alvo = get_object_or_404(Usuario, pk=request.POST.get("usuario"))
        try:
            # Igualdade explicita nos dois ramos, sem pega-tudo: um valor
            # inesperado nao pode cair na acao destrutiva. O mesmo defeito ja
            # apareceu duas vezes neste projeto (decidir_curso e o ramo RECUSAR
            # das solicitacoes).
            if acao == "PROMOVER":
                services.promover_a_coordenador(alvo, por=request.user)
                messages.success(request, f"{alvo.nome_completo} agora é coordenador.")
            elif acao == "REBAIXAR":
                services.rebaixar_a_professor(alvo, por=request.user)
                messages.success(request, f"{alvo.nome_completo} voltou a ser professor.")
            else:
                messages.error(request, "Ação não reconhecida.")
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        return redirect("pessoas")

    equipe = Usuario.objects.filter(
        papel__in=[Usuario.PROFESSOR, Usuario.COORDENADOR]
    ).order_by("nome_completo")
    pagina = paginar(request, equipe)
    return render(
        request,
        "contas/pessoas.html",
        {"equipe": pagina, "pagina": pagina, "cadastro": CadastroDeProfessorForm()},
    )
