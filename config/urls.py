from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from apps.contas.views import LoginComLimite

urlpatterns = [
    path("admin/", admin.site.urls),
    # O login e o nosso, com limite de tentativas por IP (LoginComLimite). O
    # `login` padrao do Django nao entra mais no urlpatterns - ver a nota do
    # logout, abaixo.
    path("contas/login/", LoginComLimite.as_view(), name="login"),
    # So o logout, e nao o `include` inteiro de `django.contrib.auth.urls`.
    #
    # Aquele include registrava mais cinco rotas publicas que este projeto nao
    # usa: password_change (a troca de senha mora em /perfil/) e as quatro de
    # password_reset. A de recuperacao respondia 200 servindo o template do
    # Django Admin - titulo "Recuperar senha | Site de administração do Django" -
    # sem link em tela nenhuma, e mandava e-mail com send_mail direto, por fora
    # da fila de `notificacoes` que existe justamente para SMTP fora do ar nao
    # derrubar operacao nenhuma.
    #
    # Se um dia houver recuperacao de senha por autosservico, ela entra com
    # template proprio e passando pela fila. Hoje quem destrava uma conta e a
    # coordenacao, pelo Django Admin (docs/operacao.md).
    path("contas/logout/", LogoutView.as_view(), name="logout"),
    path("", include("apps.catalogo.urls")),
    path("", include("apps.cursos.urls")),
    path("", include("apps.contas.urls")),
    path("", include("apps.painel.urls")),
    path("", include("apps.turmas.urls")),
]
