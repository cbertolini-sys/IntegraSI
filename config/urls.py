from django.contrib import admin

from django.urls import include, path

from apps.contas.views import LoginComLimite

urlpatterns = [
    path("admin/", admin.site.urls),
    # A nossa antes do include: `django.contrib.auth.urls` registra o `login`
    # padrao, e quem chega primeiro no urlpatterns responde.
    path("contas/login/", LoginComLimite.as_view(), name="login"),
    path("contas/", include("django.contrib.auth.urls")),
    path("", include("apps.catalogo.urls")),
    path("", include("apps.cursos.urls")),
    path("", include("apps.contas.urls")),
    path("", include("apps.painel.urls")),
    path("", include("apps.turmas.urls")),
]
