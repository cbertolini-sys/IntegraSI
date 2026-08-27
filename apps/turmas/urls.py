from django.urls import path

from apps.turmas import views

urlpatterns = [
    path("solicitacoes/", views.solicitacoes, name="solicitacoes"),
    path("solicitacoes/<int:pk>/", views.responder_solicitacao, name="responder_solicitacao"),
    path("turmas/", views.minhas_turmas, name="minhas_turmas"),
]
