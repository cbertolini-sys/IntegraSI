# IntegraSI — Design

Sistema de gerenciamento de cursos de extensão do curso de Sistemas de Informação
da UFSM, campus Frederico Westphalen.

Data: 2026-08-25

## 1. Contexto

Na disciplina UFSM00771 (TICs para Inclusão Digital), equipes de alunos assumem o
papel de desenvolvedoras pedagógicas: planejam, produzem e catalogam cursos e
oficinas de inclusão digital e computação, voltados a uma etapa escolar específica
ou a um público da comunidade externa. Hoje esse trabalho acontece fora de qualquer
sistema — a proposta circula por documento, os materiais por drive compartilhado,
a aprovação por conversa, e o resultado não fica catalogado nem acessível a quem
poderia solicitar o curso.

O IntegraSI dá um lugar a esse ciclo inteiro: o professor propõe o curso, a equipe
produz os materiais dentro do sistema, o professor aprova entrega por entrega, o
coordenador aprova o curso, ele entra num catálogo público, e escolas e grupos da
comunidade solicitam a realização — o que gera uma turma acompanhada no sistema.

O sistema é de **produção de cursos**, não de inscrição em cursos. Os alunos
cadastrados são os produtores do material, não os cursistas.

## 2. Atores

| Ator | Quem é | O que faz |
|---|---|---|
| Coordenador | Coordenador do curso de SI | Cadastra pessoas e edições, aprova e publica cursos, recebe solicitações, cria turmas |
| Professor | Professor responsável por um curso | Cria a proposta, monta a equipe, aprova ou devolve entregáveis, submete ao coordenador, conduz turmas |
| Aluno | Aluno de SI, membro de uma equipe | Produz seções e anexos, envia entregáveis para revisão, corrige devolutivas |
| Visitante | Escola, professor da rede, grupo comunitário | Navega o catálogo público e solicita a realização de um curso |

Contas de coordenador, professor e aluno são criadas pelo coordenador via Django
Admin. O visitante não tem conta e nunca precisa de uma.

## 3. Fluxo principal

1. O coordenador cadastra a edição da disciplina e as pessoas.
2. O professor cria a proposta de curso: título, resumo, público-alvo, carga
   horária, formato e — se houver — referencial pedagógico e competências.
3. O professor monta a equipe de alunos daquele curso.
4. O sistema cria automaticamente os cinco entregáveis obrigatórios.
5. Os alunos preenchem seções e anexam materiais em cada entregável.
6. O aluno envia um entregável para revisão; o sistema valida as regras daquele
   entregável antes de aceitar o envio.
7. O professor aprova ou devolve com comentário. Devolvido volta a ser editável.
8. Com os cinco entregáveis aprovados, o professor submete o curso ao coordenador.
9. O coordenador publica (ou devolve ao professor).
10. O curso publicado aparece no catálogo público, filtrável por público-alvo,
    referencial, categoria e formato.
11. Um visitante solicita o curso pelo formulário público.
12. Professor e coordenador dão andamento à solicitação; aceita, ela vira turma
    com data, local, vagas e participantes.

## 4. Modelo de domínio

### 4.1 Pessoas e contexto

**Usuario** — user model próprio desde a primeira migração (trocar depois é
custoso). Campos: e-mail (login), nome completo, `papel`
(`COORDENADOR`/`PROFESSOR`/`ALUNO`), ativo.

**Edicao** — a oferta da disciplina. Campos: código (`2026/2`), descrição,
data de início, data de fim, ativa. Todo curso pertence a uma edição; é o que
mantém o catálogo legível ao longo dos anos.

**MembroEquipe** — vínculo aluno ↔ curso, criado pelo professor.
Único por (curso, aluno).

### 4.2 Referencial pedagógico

A BNCC da Computação é *um* referencial possível, não uma propriedade do domínio.
Cursos podem se apoiar em outros modelos, ou em nenhum.

**Referencial** — nome, sigla, descrição, `min_competencias`, `max_competencias`,
ativo. A regra "de 2 a 5 habilidades" do roteiro de 2026 é dado deste registro,
não constante no código.

**Categoria** — agrupamento dentro de um referencial (o que a BNCC chama de
*eixo*): referencial, nome, ordem. Para a BNCC da Computação: Pensamento
Computacional, Mundo Digital, Cultura Digital.

**Competencia** — referencial, categoria, código (`EF05CO01`), descrição, etapa
de ensino, ordem. Carregada por fixture.

### 4.3 O curso

**Curso** — título, resumo, edição, professor responsável, status.

Identidade pedagógica, exigida pelo roteiro como dado estruturado e não como prosa:

- `tipo_publico`: `ESCOLAR` ou `COMUNITARIO` — **obrigatório em todo curso**
- `etapa_ano`: obrigatório quando `ESCOLAR` (Educação Infantil ao Ensino Médio)
- `publico_descricao`: obrigatório quando `COMUNITARIO`
- `referencial`: opcional; quando presente, restringe as competências selecionáveis
- `competencias`: M2M, limitadas ao referencial escolhido, validadas pela faixa
  mínimo/máximo daquele referencial
- `carga_horaria` em horas, `formato` (`PRESENCIAL`/`HIBRIDO`/`ONLINE`),
  `pre_requisitos`

Datas: criado em, atualizado em, publicado em.

### 4.4 As duas camadas da produção

O roteiro da disciplina fixa **o que** deve ser entregue; o professor decide **como**
o conteúdo se organiza dentro de cada entrega.

**Entregavel** — os cinco do roteiro, criados automaticamente na abertura do curso.
Campos: curso, `tipo` (`PLANO_ENSINO`, `CARDS`, `CADERNO`, `VIDEOS`, `SLIDES`),
status, responsável (aluno, opcional), atualizado em. Único por (curso, tipo).
É a unidade de revisão: o professor aprova ou devolve o entregável, não itens
individuais.

**Secao** — conteúdo em texto rico dentro de um entregável: título, ordem,
conteúdo (HTML sanitizado no salvamento), quem atualizou, quando. O professor
monta as seções que quiser; o sistema sugere as usuais no Plano de Ensino
(ementa, objetivos, conteúdo programático, metodologia, cronograma, avaliação,
referências).

**Anexo** — arquivo ou link preso a um entregável, opcionalmente a uma seção:

- `tipo_midia`: `ARQUIVO`, `VIDEO` ou `LINK`. Link é material complementar
  (referência externa, atividade em Scratch) e **não satisfaz nenhuma validação
  do §6** — em particular, o entregável de vídeo-aulas exige arquivo enviado
- arquivo (nome em disco por UUID), nome original, tamanho, mime detectado
- `url` para links
- título, descrição
- `referencia_bibliografica` — obrigatório nos cards
- `rotulo`: `NENHUM`, `SEM_GABARITO`, `COM_GABARITO`
- `tipo_pratica`: `NENHUM`, `PLUGADA`, `DESPLUGADA`, `AMBAS`
- `duracao_minutos` para vídeos
- enviado por, enviado em

**Revisao** — registro imutável de cada decisão do professor: entregável, revisor,
decisão (`APROVADO`/`DEVOLVIDO`), comentário, data. Nunca sobrescrito; é o
histórico das idas e vindas.

**LogTransicaoCurso** — curso, status de origem, status de destino, usuário, data,
observação. Responde "por que este curso saiu do ar?" seis meses depois.

### 4.5 Demanda e realização

**Solicitacao** — curso, nome, e-mail, telefone, instituição, número estimado de
participantes, período pretendido, mensagem, status
(`RECEBIDA`/`EM_ANALISE`/`ACEITA`/`RECUSADA`), resposta, data.

**Turma** — curso, solicitação de origem (opcional), professor responsável, data
de início, data de fim, local, vagas, status
(`AGENDADA`/`EM_ANDAMENTO`/`CONCLUIDA`/`CANCELADA`), observações.

**Participante** — turma, nome, e-mail, telefone. Deliberadamente simples: sem
conta, sem login.

### 4.6 Infraestrutura de dados

**Notificacao** — destinatário, assunto, corpo, evento, tentativas, enviado em,
último erro. Fila persistente de e-mail (ver §9).

**UploadEmAndamento** — identificador, usuário, entregável, nome original, tamanho
total, partes recebidas, criado em, atualizado em. Suporte ao upload retomável
(ver §8).

## 5. Estados

```
Entregável:  RASCUNHO → EM_REVISAO → APROVADO
                             ↓
                         DEVOLVIDO → (volta a EM_REVISAO)

Curso:  RASCUNHO → EM_PRODUCAO → AGUARDANDO_COORDENADOR → PUBLICADO
                        ↑                  ↓                   ↓
                        └──── DEVOLVIDO ───┘              DESPUBLICADO
```

Regras de transição:

- Aluno envia entregável para revisão apenas de `RASCUNHO` ou `DEVOLVIDO`, e
  somente se as validações do §6 passarem.
- Entregável em `EM_REVISAO` ou `APROVADO` é somente leitura para o aluno.
- Professor aprova ou devolve apenas entregáveis em `EM_REVISAO`; devolver exige
  comentário não vazio.
- Curso vai a `AGUARDANDO_COORDENADOR` somente com os cinco entregáveis
  `APROVADO`.
- Somente o coordenador publica, devolve ao professor ou despublica.
- Curso `DESPUBLICADO` sai do catálogo público imediatamente; pode ser republicado.

Toda transição roda em transação atômica: muda o status e grava o histórico, ou
nada acontece.

## 6. Validações de envio por entregável

Aplicadas quando o aluno envia o entregável para revisão. A mensagem de erro lista
exatamente o que falta — é ela que evita a ida e volta com o professor.

**A — Plano de Ensino**: ao menos um anexo PDF; público-alvo definido no curso;
carga horária e formato preenchidos; se houver referencial, número de competências
dentro da faixa daquele referencial; ao menos uma seção com conteúdo.

**B — Infográficos e Cards**: ao menos um anexo; **todo** anexo com
`referencia_bibliografica` preenchida.

**C — Caderno de Exercícios**: ao menos um anexo com rótulo `SEM_GABARITO` e um
com `COM_GABARITO`; entre os anexos, ao menos um marcado como prática plugada
(`PLUGADA` ou `AMBAS`) e ao menos um como desplugada (`DESPLUGADA` ou `AMBAS`).

**D — Vídeo-Aulas**: de 2 a 3 vídeos, cada um com `duracao_minutos` entre 5 e 10.

**E — Slides**: ao menos um anexo.

## 7. Arquitetura

Django monolítico com templates renderizados no servidor e HTMX nas interações
vivas (aprovar, devolver, salvar seção, anexar). PostgreSQL. Sem framework de
frontend, sem API separada: o sistema é CRUD com máquina de estados e controle de
acesso, e o critério que mais pesa é quem mantém isso daqui a dois anos.

### 7.1 Apps

| App | Responsabilidade |
|---|---|
| `contas` | `Usuario`, papéis, autenticação. Cadastro de pessoas pelo Django Admin |
| `edicoes` | `Edicao`. Minúsculo, separado porque tudo aponta para ele e nada de volta |
| `referenciais` | `Referencial`, `Categoria`, `Competencia` + fixture da BNCC da Computação |
| `cursos` | `Curso`, `MembroEquipe`, `Entregavel`, `Secao`, `Anexo`, `Revisao`, `LogTransicaoCurso`, `services.py`, `permissions.py` |
| `catalogo` | Páginas públicas e `Solicitacao`. Lê `cursos`, nunca escreve nele |
| `turmas` | `Turma`, `Participante` |
| `notificacoes` | `Notificacao` e o comando de envio |

Sem dependências circulares entre apps.

### 7.2 Camada de serviços

Toda transição de estado é uma função em `cursos/services.py`:
`enviar_para_revisao`, `aprovar_entregavel`, `devolver_entregavel`,
`submeter_ao_coordenador`, `publicar_curso`, `despublicar_curso`,
`aceitar_solicitacao`. Cada uma valida, muda o estado, grava histórico e enfileira
notificação, dentro de uma transação.

Views, Admin e comandos chamam essas funções. **Nenhum código fora de `services.py`
altera campo de status diretamente.** Sem essa disciplina, em seis meses existem
três lugares que publicam um curso de jeitos ligeiramente diferentes.

### 7.3 Telas

**Aluno** — meus cursos → curso → painel dos cinco entregáveis com status e o que
falta → editar seção → anexar arquivo ou vídeo → enviar para revisão → ver
devolutivas.

**Professor** — meus cursos → criar proposta → montar equipe → fila de revisão
("o que espera por mim") → aprovar/devolver com comentário → submeter ao
coordenador → minhas turmas.

**Coordenador** — fila de cursos aguardando aprovação → revisar curso completo →
publicar ou devolver → solicitações recebidas → criar turma → Django Admin para
pessoas, edições e referenciais.

**Visitante** — catálogo filtrável por público-alvo, referencial, categoria e
formato → página do curso → formulário de solicitação.

## 8. Arquivos

**Limites por tipo**: PDF 20 MB, imagem 10 MB, slides 50 MB, vídeo 1 GB.
Validação pelo conteúdo real do arquivo (assinatura), não pela extensão. Nome em
disco por UUID; o nome original é apenas metadado exibido.

**Upload de vídeo é retomável.** O navegador divide o arquivo em blocos e envia um
a um contra `UploadEmAndamento`, com barra de progresso; queda de conexão retoma de
onde parou. Um GB no upstream doméstico de um aluno leva perto de meia hora — um
POST único que falha aos 90% significa entrega perdida.

**Entrega de arquivo nunca passa pelo Django.** A view confere permissão e delega
ao nginx via `X-Accel-Redirect`. Isso é obrigatório, não otimização: transmitir
1 GB pelo processo Python prende um worker por dez minutos e três downloads
simultâneos derrubam o servidor. O nginx também dá *range requests*, então o vídeo
abre e navega no player em vez de só baixar.

**Formato de vídeo**: MP4/H.264 toca no navegador; outros formatos são aceitos mas
apenas baixados. Sem transcodificação no servidor.

**Volume esperado**: até 3 GB de vídeo por curso; com ~8 equipes por edição, ~24 GB
por semestre e ~240 GB em cinco anos. Isso dimensiona disco e estratégia de backup.

## 9. Notificações

Dentro do sistema, cada perfil já tem sua fila do que espera por ele — não é
preciso e-mail para o aluno descobrir que tem trabalho.

**E-mail apenas quando o destinatário não abriria o sistema por conta própria:**

| Evento | Destinatário |
|---|---|
| Entregável devolvido | Equipe do curso |
| Curso publicado | Professor e equipe |
| Solicitação recebida | Professor responsável e coordenador |
| Solicitação respondida / turma agendada | Solicitante externo |

**E-mail não pode derrubar operação.** A ação grava a `Notificacao` e commita; o
envio acontece depois, por comando de `management` chamado pelo cron, que reprocessa
falhas. Sem Celery, sem Redis, sem serviço extra para manter.

## 10. Permissões e dados pessoais

Checagens centralizadas em `cursos/permissions.py`, chamadas pelos serviços — nunca
espalhadas em `if` de template.

- **Aluno**: só cursos onde é `MembroEquipe`. Edita seções e anexos apenas com o
  entregável em `RASCUNHO` ou `DEVOLVIDO`. Nunca aprova.
- **Professor**: total sobre os cursos que responde. Não publica, não mexe em curso
  alheio, não vê participantes de turma alheia.
- **Coordenador**: acesso total; publica e despublica; Admin.
- **Visitante**: exclusivamente cursos `PUBLICADO`.

**Anexos de curso em produção não são servidos pelo `MEDIA_URL`.** Todo download
passa pela view de permissão descrita no §8; URL de arquivo vaza com facilidade, e
material não aprovado não pode circular.

**Dados pessoais de terceiros** entram por solicitantes externos e participantes de
turma. Consequências: aviso de finalidade no formulário público, acesso restrito ao
professor da turma e ao coordenador, e retenção declarada. O formulário público é a
única porta anônima que escreve no banco — recebe validação estrita, limite de
tamanho de texto, *honeypot* e limite por IP, sem CAPTCHA de terceiro.

## 11. Erros e auditoria

- Validação de envio retorna ao formulário nomeando o que falta ("faltam a versão
  com gabarito e a referência bibliográfica em 2 cards").
- 403 e 404 com página própria, sem stack trace.
- Upload interrompido não deixa anexo órfão; fragmentos são limpos por rotina.
- `Revisao` guarda o histórico pedagógico; `LogTransicaoCurso` guarda o
  administrativo.

## 12. Testes

`pytest-django`, com esforço concentrado onde mora a regra — não distribuído por
igual:

1. **Máquina de estados**: cada transição válida e, principalmente, as inválidas
   (enviar entregável aprovado, submeter curso com entregável pendente, publicar
   curso devolvido).
2. **Permissões**: as negativas são o que importa (aluno abrindo curso de outra
   equipe, anônimo baixando anexo não publicado, professor vendo turma alheia).
3. **Validações do §6**: caderno sem gabarito, card sem referência, 1 ou 4 vídeos,
   competências fora da faixa do referencial.

Views recebem teste de fumaça. Admin e template trivial não recebem teste.
Desenvolvimento em TDD: o teste da regra antes da regra.

## 13. Deploy e operação

Ubuntu, PostgreSQL, gunicorn atrás de nginx, systemd. Configuração por variável de
ambiente, `DEBUG` desligado, HTTPS obrigatório. `client_max_body_size` e timeouts
dimensionados para o upload em blocos. Mídia em volume separado do sistema, porque
ela cresce e o resto não.

**Backup são dois problemas distintos**: `pg_dump` diário do banco, retenção de
30 dias — é o que salva de erro humano; e cópia incremental da mídia com `restic`
ou `borg` para destino fora do servidor. Backup que nunca foi restaurado não é
backup: uma restauração de teste faz parte da entrega.

**Rotinas de cron**: reenvio de notificações pendentes; limpeza de uploads em
blocos abandonados há mais de 24 h (sem ela, o disco enche de fragmentos de vídeo
que ninguém reclamou).

**Carga inicial**: fixture da BNCC da Computação (categorias e competências por
etapa), edição corrente, usuário coordenador.

## 14. Fora de escopo na primeira versão

Decidido deliberadamente, para não inflar a entrega:

- Certificado e controle de frequência dos participantes de turma
- Login institucional / SSO da UFSM
- Auto-cadastro de usuários
- Versionamento e comparação de versões de seções e arquivos
- Comentários em thread dentro das seções
- Relatórios gerenciais e indicadores de extensão
- Aplicativo móvel ou API pública

## 15. Decisões registradas

| Decisão | Motivo |
|---|---|
| Django monolítico com templates, não API + SPA | Sistema é CRUD com estados e permissões; manutenção futura por bolsistas |
| Revisão no nível do entregável, não da seção ou do anexo | Cinco decisões por curso em vez de vinte; casa com a ideia de pacote do roteiro |
| Entregáveis fixos, seções livres | Roteiro fixa o que entregar; professor decide como organizar |
| Referencial genérico em vez de campos BNCC | BNCC é um foco possível, não o único; abre para outros modelos sem tocar no código |
| Público-alvo obrigatório em todo curso | É a identidade do curso e o filtro principal do catálogo |
| Upload de vídeo até 1 GB, retomável, em vez de link externo | Decisão do responsável pelo projeto; material fica sob guarda da universidade |
| Entrega de arquivo via `X-Accel-Redirect` | 1 GB pelo processo Python derruba o servidor |
| Fila de e-mail em tabela + cron, sem Celery | Um serviço a menos para manter; SMTP fora do ar não pode travar aprovação |
| Contas criadas pelo coordenador | Base pequena e controlada; evita dependência do setor de TI para SSO |
