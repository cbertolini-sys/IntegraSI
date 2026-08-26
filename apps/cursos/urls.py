from django.urls import path

from apps.cursos import views

urlpatterns = [
    path("cursos/", views.meus_cursos, name="meus_cursos"),
    path("cursos/<int:pk>/", views.curso, name="curso"),
    path("entregaveis/<int:pk>/", views.entregavel, name="entregavel"),
    path("entregaveis/<int:pk>/anexar/", views.anexar, name="anexar"),
    path("entregaveis/<int:pk>/enviar/", views.enviar_entregavel, name="enviar_entregavel"),
    path("secoes/<int:pk>/salvar/", views.salvar_secao, name="salvar_secao"),
]
