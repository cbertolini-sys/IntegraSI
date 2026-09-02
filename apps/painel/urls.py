from django.urls import path

from apps.painel import views

urlpatterns = [
    path("painel/", views.painel, name="painel"),
]
