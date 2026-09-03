from django.urls import path

from apps.contas import views

urlpatterns = [
    path("convite/<uuid:token>/", views.primeiro_acesso, name="primeiro_acesso"),
    path("perfil/", views.perfil, name="perfil"),
    path("coordenacao/pessoas/", views.pessoas, name="pessoas"),
]
