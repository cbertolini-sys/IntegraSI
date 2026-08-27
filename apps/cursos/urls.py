from django.urls import path

from apps.cursos import views

urlpatterns = [
    path("cursos/", views.meus_cursos, name="meus_cursos"),
    path("cursos/<int:pk>/", views.curso, name="curso"),
    path("entregaveis/<int:pk>/", views.entregavel, name="entregavel"),
    path("entregaveis/<int:pk>/anexar/", views.anexar, name="anexar"),
    path("entregaveis/<int:pk>/enviar/", views.enviar_entregavel, name="enviar_entregavel"),
    path("secoes/<int:pk>/salvar/", views.salvar_secao, name="salvar_secao"),
    path("propostas/nova/", views.nova_proposta, name="nova_proposta"),
    path("cursos/<int:pk>/equipe/", views.equipe, name="equipe"),
    path("cursos/<int:pk>/submeter/", views.submeter_curso, name="submeter_curso"),
    path("revisao/", views.fila_revisao, name="fila_revisao"),
    path("revisao/<int:pk>/", views.revisar, name="revisar"),
    path("revisao/<int:pk>/decidir/", views.decidir, name="decidir"),
    path("coordenacao/", views.fila_coordenacao, name="fila_coordenacao"),
    path("coordenacao/catalogo/", views.cursos_no_catalogo, name="cursos_no_catalogo"),
    path("coordenacao/<int:pk>/", views.analisar_curso, name="analisar_curso"),
    path("coordenacao/<int:pk>/decidir/", views.decidir_curso, name="decidir_curso"),
]
