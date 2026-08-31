# IntegraSI

Sistema de gerenciamento de cursos de extensão do curso de Sistemas de Informação
da UFSM, campus Frederico Westphalen. Na disciplina UFSM00771 (TICs para Inclusão
Digital), equipes de alunos propõem, produzem e catalogam cursos e oficinas de
inclusão digital e computação; o IntegraSI dá um lugar a esse ciclo - proposta,
produção de material, aprovação e catálogo público - que hoje acontece espalhado
entre documentos, drive compartilhado e conversa.

O sistema está implementado em cinco módulos, todos concluídos:

1. **Fundação e cadastros** - usuários, edições da disciplina, referenciais
   pedagógicos e temas.
2. **Produção de cursos** - proposta, equipe, os cinco entregáveis do roteiro,
   revisão entregável por entregável.
3. **Publicação, catálogo e demanda** - fila da coordenação, catálogo público com
   busca, formulário de solicitação e turmas.
4. **Mídia, versões e operação** - envio de vídeo de até 1 GB retomável, entrega
   protegida por `X-Accel-Redirect`, versões de curso e o deploy com backup.
5. **Papéis e primeiro acesso** - coordenador herda professor, alocação de aluno
   por nome e e-mail, convite com prazo e uso único.

Os planos de implementação estão em `docs/superpowers/plans/`, e a especificação
de design em `docs/superpowers/specs/`.

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

`criar_coordenador` é a única rota para criar o primeiro superusuário - o modelo de
usuário exige SIAPE para todo papel que não seja aluno, então
`manage.py createsuperuser` não consegue completar. Rodar o comando de novo com o
mesmo e-mail reseta a senha (se já for coordenador) ou promove a conta a
coordenador (se pertencer a outro papel).

## Testes

```bash
python -m pytest
```

## Documentação

- `docs/superpowers/specs/` - a especificação de design do sistema.
- `docs/superpowers/plans/` - os planos de implementação, por módulo.
- `docs/onde-mora-a-validacao.md` - onde cada tipo de regra de validação vive neste
  código.
- `docs/dados/README.md` - como importar os dados de referência (BNCC da
  Computação).

## Estilo de escrita

**É proibido o uso do travessão (`—`).** A regra vale para todo o repositório:
prosa, documentação, comentários de código, strings de interface e mensagens de
commit. Vale também para a entidade HTML `&mdash;`, que produz o mesmo símbolo.

Para separar frases ou introduzir explicações, escolha pelo que a frase está
fazendo:

| Situação | Use |
|---|---|
| O que vem depois explica o que veio antes | dois pontos (`:`) |
| O trecho é um aparte que se pode remover | parênteses (`( )`) |
| É só uma pausa | vírgula (`,`) |
| Nenhuma das outras serve | traço simples com espaços (` - `) |

Reescrever a frase costuma ser melhor que trocar o símbolo.

Para conferir antes de commitar:

```bash
git ls-files | xargs grep -n "—\|&mdash;"
```

`tests/test_estilo.py` reprova se o símbolo aparecer em qualquer arquivo de
texto versionado, apontando arquivo e linha. Se ele acusar um arquivo que você
acabou de trazer de fora, a correção é reescrever a frase, e não isentar o
arquivo: a única isenção são o `README.md` e a `CLAUDE.md`, que precisam mostrar
o símbolo para explicá-lo, e há um teste garantindo que essa isenção continue
justificada.

