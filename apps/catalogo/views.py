from django.shortcuts import get_object_or_404, render

from apps.cursos.busca import buscar
from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.cursos.models import Curso, Tema
from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Referencial


def cursos_publicados():
    """Visitante enxerga exclusivamente cursos PUBLICADO (spec 10)."""
    return Curso.objects.filter(status=StatusCurso.PUBLICADO).select_related("referencial")


def catalogo(request):
    cursos = cursos_publicados()

    etapa = request.GET.get("etapa", "")
    if etapa:
        cursos = cursos.filter(tipo_publico=TipoPublico.ESCOLAR, etapa_ano=etapa)
    if request.GET.get("comunitario"):
        cursos = cursos.filter(tipo_publico=TipoPublico.COMUNITARIO)

    tema = request.GET.get("tema", "")
    if tema:
        cursos = cursos.filter(temas__slug=tema)

    referencial = request.GET.get("referencial", "")
    if referencial:
        cursos = cursos.filter(referencial__sigla=referencial)

    formato = request.GET.get("formato", "")
    if formato:
        cursos = cursos.filter(formato=formato)

    cursos = buscar(cursos, request.GET.get("q", "")).distinct()

    return render(
        request,
        "catalogo/lista.html",
        {
            "cursos": cursos,
            "etapas": ETAPAS,
            "temas": Tema.objects.filter(ativo=True),
            "referenciais": Referencial.objects.filter(ativo=True),
            "formatos": Formato.choices,
            "filtros": request.GET,
        },
    )


def catalogo_curso(request, pk):
    curso = get_object_or_404(cursos_publicados().prefetch_related("temas", "competencias"), pk=pk)
    return render(request, "catalogo/curso.html", {"curso": curso})
