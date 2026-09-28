from django.urls import path

from apps.contas import views

urlpatterns = [
    path("convite/<uuid:token>/", views.primeiro_acesso, name="primeiro_acesso"),
    path("senha/esqueci/", views.esqueci_senha, name="esqueci_senha"),
    path("senha/redefinir/<uuid:token>/", views.redefinir_senha, name="redefinir_senha"),
    path("perfil/", views.perfil, name="perfil"),
    path("coordenacao/pessoas/", views.pessoas, name="pessoas"),
]
