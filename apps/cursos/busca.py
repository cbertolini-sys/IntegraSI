from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVectorField
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce

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
    return (
        queryset.filter(Q(search_vector=consulta) | Q(vetor_temas=consulta))
        # Ordenar por RELEVANCIA, e nao pela ordenacao do modelo (`-criado_em`).
        #
        # Com o catalogo pequeno isso e invisivel. Numa replica de 50 mil linhas a
        # mesma busca casou 14.286 cursos, e o visitante recebia os doze mais
        # recentes: um curso cujo titulo e exatamente o termo buscado ficava atras
        # de qualquer outro publicado depois dele.
        #
        # Nao custa: medido na replica, `ts_rank` com LIMIT 12 levou 14,3 ms contra
        # 17,2 ms da ordenacao por data. O `top-N heapsort` resolve os dois igual.
        .annotate(
            relevancia=(
                SearchRank(F("search_vector"), consulta)
                # `Coalesce` obrigatorio: `vetor_temas` e nulo enquanto ninguem
                # definir tema, `SearchRank` sobre nulo devolve nulo, e nulo + numero
                # e nulo. Sem isto um curso sem tema perderia a relevancia inteira e
                # cairia para o fim - deixaria de ser encontrado por ter um campo
                # OPCIONAL vazio.
                + SearchRank(
                    Coalesce(F("vetor_temas"), Value("", output_field=SearchVectorField())),
                    consulta,
                )
            )
        )
        # A soma, e nao so o `search_vector`: curso que casa pelo titulo E pelo tema
        # e mais pertinente que um que casa so por um dos dois, e essa e a ordem que
        # quem procura espera.
        #
        # `-criado_em` como segundo criterio nao e enfeite: sem desempate, o Postgres
        # devolve empatados em ordem indefinida, e a paginacao passa a repetir e a
        # pular linhas entre a pagina 1 e a 2.
        .order_by("-relevancia", "-criado_em")
    )
