from django.contrib.postgres.search import SearchQuery
from django.db.models import Q

# R62: 'portuguese' sozinho e sensivel a acento (a extensao unaccent nao pode
# entrar direto na config por ser STABLE, nao IMMUTABLE - Postgres recusa isso em
# coluna gerada e em indice). 'portugues_unaccent' e uma copia de 'portuguese'
# com o mapeamento de hword/hword_part/word passando por unaccent antes do
# stemmer (ver migracao 0008), o que mantem tudo IMMUTABLE e faz 'robotica'
# encontrar 'Robótica'. Usada aqui e na coluna gerada de Curso (spec 4.4) - o
# nome vive so nesta constante para as duas pontas nao poderem divergir.
CONFIG_TEXTO = "portugues_unaccent"


def buscar(queryset, termo):
    """Filtra pelo termo usando busca de texto completo em portugues, insensivel a
    acento e a flexao (R62): 'robotica' encontra 'Robótica' e 'oficinas' encontra
    'oficina'; LIKE nao faz nenhuma das duas (spec 4.4). Termo vazio nao filtra
    nada."""
    termo = (termo or "").strip()
    if not termo:
        return queryset
    consulta = SearchQuery(termo, config=CONFIG_TEXTO)
    return queryset.filter(Q(search_vector=consulta) | Q(vetor_temas=consulta))
