# Etapas da educação básica. Usado pela Competencia e pelo campo etapa_ano do Curso
# quando o público é escolar (spec 4.3).
ETAPAS = [
    ("EI", "Educação Infantil"),
    ("EF01", "1º ano do Ensino Fundamental"),
    ("EF02", "2º ano do Ensino Fundamental"),
    ("EF03", "3º ano do Ensino Fundamental"),
    ("EF04", "4º ano do Ensino Fundamental"),
    ("EF05", "5º ano do Ensino Fundamental"),
    ("EF06", "6º ano do Ensino Fundamental"),
    ("EF07", "7º ano do Ensino Fundamental"),
    ("EF08", "8º ano do Ensino Fundamental"),
    ("EF09", "9º ano do Ensino Fundamental"),
    ("EM01", "1º ano do Ensino Médio"),
    ("EM02", "2º ano do Ensino Médio"),
    ("EM03", "3º ano do Ensino Médio"),
]


# Etapas como a BNCC organiza as habilidades, que NAO sao as do curso.
#
# O curso e proposto para um ano ("EM02"), mas as habilidades do Ensino Medio
# valem para os tres anos de uma vez ("EM13CO01"). Forcar o mesmo vocabulario nos
# dois obrigaria a gravar cada habilidade do Medio tres vezes, com o mesmo codigo,
# o que a unicidade de (referencial, codigo) nem permitiria.
ETAPAS_REFERENCIAL = [
    ("EI", "Educação Infantil"),
    ("EF01", "1º ano do Ensino Fundamental"),
    ("EF02", "2º ano do Ensino Fundamental"),
    ("EF03", "3º ano do Ensino Fundamental"),
    ("EF04", "4º ano do Ensino Fundamental"),
    ("EF05", "5º ano do Ensino Fundamental"),
    ("EF06", "6º ano do Ensino Fundamental"),
    ("EF07", "7º ano do Ensino Fundamental"),
    ("EF08", "8º ano do Ensino Fundamental"),
    ("EF09", "9º ano do Ensino Fundamental"),
    ("EM", "Ensino Médio"),
]


def etapa_do_referencial(etapa_ano):
    """Traduz a etapa do curso para a etapa em que o referencial organiza."""
    if not etapa_ano:
        return ""
    if etapa_ano.startswith("EM"):
        return "EM"
    return etapa_ano


def rotulo_da_competencia(etapa, plural=False):
    """Como a etapa chama o que o referencial oferece (spec 4.2).

    A Educacao Infantil da BNCC diz "objetivo de aprendizagem"; do 1o ano em
    diante, "habilidade". O modelo continua chamando tudo de Competencia, que e o
    nome generico do sistema; quem muda de palavra e a tela.
    """
    if etapa == "EI":
        return "objetivos de aprendizagem" if plural else "objetivo de aprendizagem"
    return "habilidades" if plural else "habilidade"
