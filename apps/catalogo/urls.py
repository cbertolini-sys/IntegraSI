from django.urls import path

from apps.catalogo import views

urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("sobre/", views.sobre, name="sobre"),
    path("cursos/<int:pk>/publico/", views.catalogo_curso, name="catalogo_curso"),
    path("cursos/<int:pk>/solicitar/", views.solicitar, name="solicitar"),
]
