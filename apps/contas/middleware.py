from django.shortcuts import redirect


class PerfilCompletoMiddleware:
    """Quem entrou e ainda não completou o cadastro só alcança a própria tela.

    Middleware, e não decorador em cada view: uma view nova nasceria desprotegida
    e ninguém perceberia. Aqui o padrão é fechado e as exceções são explícitas.

    Só age quando existe um convite pendente. Contas antigas -- criadas antes do
    Plano 5, ou pelo Admin -- podem estar sem telefone e não têm convite nenhum:
    sem para onde redirecionar, prendê-las seria trancá-las fora do sistema.
    """

    # `logout` está aqui de propósito: sem ele, quem entra com o cadastro pela
    # metade não consegue nem sair da conta. O catálogo é público e continua
    # público para quem está logado.
    LIBERADAS = {
        "primeiro_acesso",
        "logout",
        "login",
        "catalogo",
        "catalogo_curso",
        "solicitar",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            return None
        if usuario.perfil_completo:
            return None
        if request.resolver_match and request.resolver_match.url_name in self.LIBERADAS:
            return None
        # O Admin fica fora: é por onde a coordenação destrava uma conta presa.
        if request.path.startswith("/admin/"):
            return None
        convite = usuario.convites.filter(
            usado_em__isnull=True, cancelado_em__isnull=True
        ).first()
        if convite is None:
            return None
        return redirect("primeiro_acesso", token=convite.token)
