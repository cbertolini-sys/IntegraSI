# IntegraSI

Sistema de **produção de cursos de extensão** do curso de Sistemas de Informação da
UFSM, campus Frederico Westphalen. Professores propõem cursos, equipes de alunos
produzem o material dentro do sistema, o professor aprova entrega por entrega, o
coordenador publica, e um catálogo público recebe solicitações da comunidade.

Não é sistema de inscrição em cursos: os alunos cadastrados são quem **produz** o
material, não quem assiste.

## Onde está o desenho

- `docs/superpowers/specs/2026-08-25-integrasi-design.md` — a spec. É a autoridade;
  os planos argumentam a partir dela.
- `docs/superpowers/plans/` — quatro planos, executados em ordem:
  1. fundação e cadastros (**concluído**), 2. produção de cursos,
  3. publicação, catálogo e demanda, 4. mídia, versões e operação.
- `docs/onde-mora-a-validacao.md` — qual mecanismo de validação usar para quê.
  **Leia antes de acrescentar validação a qualquer modelo.**
- `docs/dados/README.md` — como carregar a BNCC.

Os planos foram corrigidos durante a execução quando as revisões acharam defeitos
neles. Se você reexecutar um plano, use a versão em git, não a lembrança dele.

## Comandos

```bash
source .venv/bin/activate
pytest                       # suíte completa
pytest apps/contas -v        # um app
python manage.py migrate
python manage.py loaddata bncc_computacao temas_iniciais
python manage.py criar_coordenador --email ... --nome ... --cpf ... --siape ... --senha ...
python manage.py runserver
```

PostgreSQL local, Python 3.13, Django 5.2. Configuração vem toda de variável de
ambiente (`.env`, modelo em `.env.example`). `createsuperuser` **não funciona** neste
projeto — `REQUIRED_FIELDS` omite `siape` de propósito; use `criar_coordenador`.

## Arquitetura

Django monolítico com templates no servidor, HTMX nas interações vivas. Apps sob
`apps/`, cada um com `name = "apps.<app>"` em `apps.py`.

`contas` (usuários e papéis) · `edicoes` (ofertas da disciplina) · `referenciais`
(referenciais pedagógicos genéricos) · `cursos` (núcleo; hoje só `Tema`)

Dependência é de mão única. A partir do Plano 3: `turmas` lê `cursos`; `cursos` e
`catalogo` **não** conhecem `turmas`.

**Fronteira de módulo (spec §1.1):** este é o módulo de *produção*. Frequência,
avaliação e certificado pertencem a um módulo de *execução* futuro. Qualquer campo
desses aparecendo aqui é sinal de que a fronteira foi atravessada sem querer.

## Convenções que custaram caro para estabelecer

**Validação**
- `save()` chama `full_clean()`, **exceto** quando vem `update_fields` — sem esse
  guarda, o `update_last_login` do Django valida o objeto inteiro a cada login e
  qualquer linha inválida deixa a pessoa impossibilitada de entrar.
  (`Tema.save()` ainda não tem o guarda; o Plano 2 aplica ao mover o arquivo.)
- Normalização de documentos roda em `full_clean()` **antes** do `validate_unique()`,
  nunca depois — senão a unicidade não vale nada.
- Só `services.py` altera campo de status (a partir do Plano 2). Nada de lógica de
  domínio em sinais `post_save`.

**Dados pessoais**
- CPF não aparece em lugar nenhum fora do Django Admin, e mascarado até lá.
- `search_fields` do admin exclui `cpf` de propósito: buscar por CPF o colocaria na
  URL e nos logs de acesso. `matricula` e `siape` continuam buscáveis — são
  identificadores institucionais internos, não documento nacional.

**Referenciais pedagógicos**
- A BNCC é *um* referencial, não a estrutura do sistema. Curso sem referencial
  (Arduino, IA na Educação) é de primeira classe. **Nenhuma tela, filtro ou relatório
  pode pressupor BNCC.**
- **Nunca invente códigos de habilidade da BNCC.** A fixture traz só o referencial e
  os três eixos; as habilidades são transcritas da Resolução CNE/CEB nº 1/2022 para
  um CSV e importadas.

**Higiene de app**
- Um app tem pacote `tests/`; nada de `tests.py` solto nem `views.py` vazio do
  `startapp`.
- Texto voltado ao usuário em português **acentuado**. Valores gravados (choices,
  slugs, códigos) sem acento e nunca alterados por passada de texto.

**Testes**
- TDD: teste que falha primeiro.
- **Enumere as regras antes de conferir os testes, nunca o contrário.** Ao terminar uma
  tarefa, escreva a lista das regras que ela introduz — lidas do plano e das restrições,
  não do código que você acabou de escrever. Só então percorra a lista dizendo, para cada
  regra, qual teste a prende e se apagar a implementação dela faria algum teste falhar.
  Partir dos testes só encontra teste fraco; partir das regras também encontra regra que
  ninguém testou. As duas perguntas parecem a mesma e não são.
- Teste que passa com a invariante quebrada não vale nada. Prove quebrando de propósito:
  apague a guarda, veja o teste falhar, restaure, veja passar. **Apague uma guarda de cada
  vez.** Um teste que falha por dois motivos ao mesmo tempo não prende nenhum dos dois: se
  o cenário viola duas regras juntas, apagar qualquer uma delas deixa a outra levantando a
  exceção e o teste segue verde. A pergunta não é "existe teste que exercita esta regra?",
  e sim "apagar *esta guarda sozinha* faria algum teste falhar?" — a enumeração de regras
  não detecta isso, só a deleção isolada detecta.
- **Comite antes de quebrar de propósito.** A deleção é temporária e o reflexo para desfazer
  é `git checkout <arquivo>` — que também descarta qualquer outra alteração não commitada
  naquele arquivo. Já custou trabalho neste projeto. Comite (ou faça `stash`) antes de
  mutilar a guarda, e restaure com a certeza de não levar mais nada junto. O padrão "teste com nome
  que não exercita a regra" apareceu **sete vezes** no Plano 2 e mais duas no Plano 3, em
  tarefas diferentes e achado por revisores diferentes — entre elas uma regra de segurança,
  a checagem de que o plano de ensino é PDF (apagável inteira sem quebrar nada) e a cerca da
  fronteira do módulo, que comparava seis nomes exatos e deixou passar calados três campos
  de nomes mais longos.
- **Duas guardas para a mesma coisa não se distinguem por teste de POST.** Quando a view
  chama um serviço que também confere permissão, afrouxar a guarda da view não quebra nada:
  o serviço recusa igual e o teste vê o mesmo 403. Ambas *existem*, ambas *têm* teste, e
  mesmo assim uma delas não está presa. Só o GET — ou qualquer caminho que não chame o
  serviço — isola a guarda da view. Ao pôr guarda numa view, pergunte por onde ela responde
  sozinha; se não houver caminho assim, ou o teste passa por ele ou a guarda não está presa.
- **A regra pode estar provada de um lado da fronteira de função e solta do outro.** Um teste
  da função pura prova a aritmética; não prova que o chamador a usa. No Plano 3, `recuo()`
  tinha teste de que dobra a cada falha, e trocar `recuo(tentativas)` por `RECUO_INICIAL` no
  ponto de chamada deixava a suíte verde. O nome do teste não mentia — a regra estava provada
  onde não roda e desprovada onde roda. Prenda no ponto de chamada, não só na função.

## Papéis e primeiro acesso (Plano 5)

- `papel` é um valor só por pessoa. A herança está em `Usuario.e_professor`, que
  vale para coordenador; `e_somente_professor` é para quem precisa da distinção.
  **Não reescreva `papel == PROFESSOR` solto pelo código.**
- Aluno é criado pelo professor com nome e e-mail, sem CPF e sem matrícula.
  `Usuario.perfil_completo` é derivado dos campos — não existe flag paralela, e
  não crie uma: seria segunda fonte de verdade, e sai de sincronia na primeira
  edição pelo Admin.
- O convite (`ConviteAluno`) vale 7 dias, serve uma vez e leva token, **nunca
  senha**: a fila de notificações persiste no banco.
- `PerfilCompletoMiddleware` prende quem não completou o cadastro na própria
  tela. As exceções são explícitas em `LIBERADAS`; `logout` está lá de propósito,
  senão a pessoa não consegue nem sair. Só age quando há convite pendente —
  conta antiga sem convite não tem para onde ser redirecionada.
- Promoção e rebaixamento passam por `contas.services`, nunca por edição do campo
  `papel` no Admin: o Admin não tem como recusar o auto-rebaixamento.
- `contas` **não** importa `cursos`. `alocar_aluno` (em `cursos`) importa
  `contas.services` dentro da função, como o arquivo já fazia com `Usuario`.

## Restrições entre planos

- `Curso.referencial` precisa continuar `PROTECT` (Plano 2). É o que impede apagar um
  referencial em uso, agora que as chaves dentro de `referenciais` cascateiam.
- `templates/base.html` tem região de `messages`; sem ela toda mensagem enfileirada
  pelos planos seguintes sumiria em silêncio. Os blocos `titulo` e `conteudo` são
  herdados por todas as telas.
- Segurança de produção (HTTPS, cookies seguros, HSTS) é do Plano 4, dono do deploy.
