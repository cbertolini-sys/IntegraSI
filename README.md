# IntegraSI

Sistema de gerenciamento de cursos de extensão do curso de Sistemas de Informação
da UFSM, campus Frederico Westphalen. Na disciplina UFSM00771 (TICs para Inclusão
Digital), equipes de alunos propõem, produzem e catalogam cursos e oficinas de
inclusão digital e computação; o IntegraSI dá um lugar a esse ciclo — proposta,
produção de material, aprovação e catálogo público — que hoje acontece espalhado
entre documentos, drive compartilhado e conversa.

Este repositório contém o **Plano 1: fundação e cadastros** (usuários, edições da
disciplina, referenciais pedagógicos e temas). Módulos seguintes estão descritos em
`docs/superpowers/plans/`.

## Requisitos

- Python 3.13
- PostgreSQL

## Configuração

```bash
git clone <url-do-repositorio>
cd IntegraSI
python3 -m venv .venv
source .venv/bin/activate
pip install "django>=5.1,<6.0" "psycopg[binary]>=3.2" "python-dotenv>=1.0" \
    "dj-database-url>=2.1" "pytest>=8.0" "pytest-django>=4.8"

cp .env.example .env
# edite .env com a URL do seu banco PostgreSQL e uma SECRET_KEY própria

python manage.py migrate
python manage.py loaddata bncc_computacao temas_iniciais
python manage.py criar_coordenador --email coord@ufsm.br --nome "Nome Completo" \
    --cpf 529.982.247-25 --siape 0000000 --senha "uma-senha-forte"

python manage.py runserver
```

`criar_coordenador` é a única rota para criar o primeiro superusuário — o modelo de
usuário exige SIAPE para todo papel que não seja aluno, então
`manage.py createsuperuser` não consegue completar. Rodar o comando de novo com o
mesmo e-mail reseta a senha (se já for coordenador) ou promove a conta a
coordenador (se pertencer a outro papel).

## Testes

```bash
python -m pytest
```

## Documentação

- `docs/superpowers/specs/` — a especificação de design do sistema.
- `docs/superpowers/plans/` — os planos de implementação, por módulo.
- `docs/onde-mora-a-validacao.md` — onde cada tipo de regra de validação vive neste
  código.
- `docs/dados/README.md` — como importar os dados de referência (BNCC da
  Computação).
