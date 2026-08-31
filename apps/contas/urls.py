from django.urls import path

from apps.contas import views

urlpatterns = [
    path("painel/", views.painel, name="painel"),
    path("convite/<uuid:token>/", views.primeiro_acesso, name="primeiro_acesso"),
]
