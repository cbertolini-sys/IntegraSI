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

### 1.1 Este é o módulo de produção

O IntegraSI está planejado em dois módulos. Este documento especifica o primeiro:
**produção e catalogação**. Um segundo módulo, de **execução dos cursos**
(frequência, avaliação, certificação, acompanhamento de turma em andamento), será
construído depois, sobre esta base.

Isso não é uma nota de rodapé — é uma restrição de projeto, e três regras saem dela:

1. **`Turma` e `Participante` existem aqui na forma mínima**: agendamento e lista de
   presentes na lista, nada mais. São o ponto onde a demanda captada pelo catálogo
   pousa, e a fundação sobre a qual o módulo de execução será construído. Nenhum
   campo de frequência, nota ou certificado entra agora.
2. **A costura é a versão do curso.** A `Turma` aponta para uma versão específica do
   `Curso`, nunca para a linhagem. É o que permitirá ao módulo de execução dizer,
   em 2029, exatamente qual material foi aplicado numa turma de 2027 — mesmo que o
   curso tenha ganhado versões depois.
3. **`cursos` e `catalogo` não conhecem `turmas`.** A dependência é de mão única:
   `turmas` lê `cursos`. Assim o módulo de execução cresce a partir de `turmas` sem
   tocar no núcleo de produção.

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
13. Mais tarde, um curso fraco ou incompleto pode ganhar uma nova versão, produzida
    por outra equipe, sem sair do catálogo enquanto isso (§4.5).

## 4. Modelo de domínio

### 4.1 Pessoas e contexto

**Usuario** — user model próprio desde a primeira migração (trocar depois é
custoso).

Campos comuns a todos: nome completo, e-mail (é o login, único), CPF (único),
`papel` (`COORDENADOR`/`PROFESSOR`/`ALUNO`), ativo.

Campos de vínculo, um único modelo com validação condicional em `clean()`:

| Campo | Obrigatório para | Vazio para |
|---|---|---|
| `matricula` | `ALUNO` | professor e coordenador |
| `siape` | `PROFESSOR`, `COORDENADOR` | aluno |

Ambos únicos quando preenchidos. Um só modelo, e não perfis separados por papel:
a base é pequena, os campos são poucos e um `OneToOne` por papel triplicaria as
consultas em troca de nenhuma garantia que a validação já não dê.

**CPF, matrícula e SIAPE são normalizados na gravação** — só dígitos, sem ponto,
traço ou barra. Sem isso, `123.456.789-00` e `12345678900` convivem no banco e a
restrição de unicidade não serve para nada. O CPF tem os dígitos verificadores
conferidos; campo digitado à mão erra, e um CPF inválido só aparece anos depois,
quando alguém precisa dele.

**Finalidade dos dados pessoais (§10).** Nome, e-mail, matrícula e SIAPE identificam
quem produziu cada material e a quem o sistema se dirige. O CPF **não tem uso dentro
do módulo de produção**: é coletado para a identificação institucional inequívoca e
para a emissão de certificado no módulo de execução (§1.1). Está registrado aqui
justamente porque campo sem finalidade declarada é campo que ninguém sabe explicar
depois — e a LGPD cobra essa explicação.

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

**Cursos sem referencial são de primeira classe.** Um curso de Arduino, de IA na
Educação ou de qualquer outro foco nasce com `referencial` vazio, não seleciona
competência nenhuma e passa por todas as demais regras normalmente. A validação de
competências (§6-A) só roda quando existe referencial. Nenhuma tela, filtro ou
relatório pode pressupor BNCC.

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

Descoberta (§4.4): `temas` (M2M) e `palavras_chave` (texto livre).

Versionamento (§4.5): `raiz`, `versao`, `motivo_versao`.

Datas: criado em, atualizado em, publicado em.

### 4.4 Temas, palavras-chave e busca

Duas coisas diferentes, que servem a propósitos diferentes.

**Tema** — vocabulário controlado, cadastrado pelo coordenador no Admin
(Pensamento Computacional, Robótica, Segurança Digital, IA na Educação, Inclusão
Digital de Adultos…): nome, slug, ativo. Ligado ao curso por M2M e exposto como
**filtro** no catálogo. É controlado porque filtro com texto livre não funciona:
"robótica", "Robotica" e "robótica educacional" viram três filtros distintos e
nenhum deles encontra tudo.

**`palavras_chave`** — texto livre preenchido pela equipe. Não vira filtro;
alimenta a busca.

**Busca textual** — coluna `search_vector` (`SearchVectorField`) no `Curso`, com
índice GIN e dicionário em português. O dicionário é o que faz "robótica" encontrar
"robotica" e "robôs"; `LIKE` não faz isso.

Como a coluna é mantida, com uma pegadinha que custa uma tarde se descoberta tarde:
**coluna gerada não faz `JOIN`**. `GeneratedField` (Django 5.0) ou um trigger na
tabela `curso` cobrem os campos da própria linha — título, resumo, palavras-chave —
mas **não alcançam os nomes dos temas**, que vivem numa M2M. Então: campos próprios
por coluna gerada, e os temas incorporados ao vetor por atualização explícita quando
o vínculo muda. O mesmo vale se um `Tema` for renomeado — os cursos ligados a ele
precisam ser reindexados.

### 4.5 Versões de um curso

Um curso publicado pode se mostrar fraco ou incompleto, e outra equipe — em outro
semestre — pode melhorá-lo. Isso **não** é editar o curso publicado: é criar uma
nova versão dele.

Campos no `Curso`:

- `raiz` — FK para a primeira versão da linhagem (vazio na própria v1). Agrupa toda
  a história de um curso.
- `versao` — inteiro sequencial dentro da linhagem.
- `motivo_versao` — por que esta versão foi aberta. Obrigatório a partir da v2.

Como funciona:

1. Coordenador ou o professor responsável abre nova versão de um curso publicado,
   informando o motivo.
2. O sistema clona o curso na edição corrente: dados, entregáveis, seções e anexos.
   Todos os entregáveis clonados voltam a `RASCUNHO`; o histórico de `Revisao` da
   versão anterior **não** é copiado — pertence a ela.
3. O professor monta a nova equipe. Pode ser outra turma inteira.
4. A versão anterior **continua publicada e solicitável** durante todo o trabalho.
5. Quando o coordenador publica a nova versão, a anterior passa a `SUBSTITUIDO`,
   sai do catálogo e permanece consultável como histórico.

Restrições: no máximo uma versão de cada linhagem fora de `PUBLICADO`/`SUBSTITUIDO`
por vez — duas equipes não reescrevem o mesmo curso em paralelo. O catálogo mostra,
de cada linhagem, apenas a versão publicada.

**Curso abandonado antes de publicar é outro caso, e mais simples**: não precisa de
versão nenhuma. O professor troca os membros da equipe e o novo grupo continua de
onde o anterior parou.

### 4.6 As duas camadas da produção

O roteiro da disciplina fixa **o que** deve ser entregue; o professor decide **como**
o conteúdo se organiza dentro de cada entrega.

**Entregavel** — os cinco do roteiro, criados automaticamente na abertura do curso.
Campos: curso, `tipo` (`PLANO_ENSINO`, `CARDS`, `CADERNO`, `VIDEOS`, `SLIDES`),
status, responsável (aluno, opcional), atualizado em. Único por (curso, tipo).
É a unidade de revisão: o professor aprova ou devolve o entregável, não itens
individuais.

**Secao** — conteúdo em texto rico dentro de um entregável: título, ordem,
conteúdo (HTML sanitizado no salvamento), quem atualizou, quando. O professor
monta as seções que quiser.

Na abertura do curso, `criar_curso()` já cria as seções usuais do Plano de Ensino
vazias (ementa, objetivos, conteúdo programático, metodologia, cronograma,
avaliação, referências), junto com os cinco entregáveis e na mesma transação. O
aluno abre e encontra a estrutura pronta para preencher. **Isso não é feito por
sinal `post_save`**: sinal é invisível no fluxo, difícil de testar e não dispara de
forma confiável em fixtures e criações em lote — e contraria a regra do §7.2 de que
só os serviços alteram estado.

**Anexo** — arquivo ou link preso a um entregável, opcionalmente a uma seção:

- `tipo_midia`: `ARQUIVO`, `VIDEO` ou `LINK`. Link é material complementar
  (referência externa, atividade em Scratch) e **não satisfaz nenhuma validação
  do §6** — em particular, o entregável de vídeo-aulas exige arquivo enviado
- `arquivo` — FK para `Arquivo`; nome original exibido
- `url` para links
- título, descrição
- `referencia_bibliografica` — obrigatório nos cards
- `rotulo`: `NENHUM`, `SEM_GABARITO`, `COM_GABARITO`
- `tipo_pratica`: `NENHUM`, `PLUGADA`, `DESPLUGADA`, `AMBAS`
- `duracao_minutos` para vídeos
- enviado por, enviado em

**Arquivo** — o conteúdo binário, separado do anexo que o referencia: caminho em
disco (UUID), hash do conteúdo, tamanho, mime detectado, enviado por, enviado em.
Imutável.

A separação existe por causa do versionamento: clonar um curso não pode clonar 3 GB
de vídeo. Versões diferentes referenciam o **mesmo** `Arquivo`, e a remoção física
só acontece quando nenhum anexo de nenhuma versão o referencia — verificação feita
pela rotina de limpeza, nunca no momento de apagar um anexo.

**Revisao** — registro imutável de cada decisão do professor: entregável, revisor,
decisão (`APROVADO`/`DEVOLVIDO`), comentário, data. Nunca sobrescrito; é o
histórico das idas e vindas.

**LogTransicaoCurso** — curso, status de origem, status de destino, usuário, data,
observação. Responde "por que este curso saiu do ar?" seis meses depois.

### 4.7 Demanda e realização

**Solicitacao** — curso, nome, e-mail, telefone, instituição, número estimado de
participantes, período pretendido, mensagem, status
(`RECEBIDA`/`EM_ANALISE`/`ACEITA`/`RECUSADA`), resposta, data.

**Turma** — a versão do curso que será aplicada, solicitação de origem (opcional),
professor responsável (designado no aceite da solicitação, §7.2, e obrigatório),
data de início, data de fim, local, vagas, status
(`AGENDADA`/`EM_ANDAMENTO`/`CONCLUIDA`/`CANCELADA`), observações.

**Participante** — turma, nome, e-mail, telefone. Deliberadamente simples: sem
conta, sem login.

Ambos param aqui, por decisão de escopo (§1.1): registram o agendamento e quem
participou. Frequência, avaliação e certificado são do módulo de execução, e
qualquer campo desses que aparecer neste módulo é sinal de que a fronteira foi
atravessada sem querer.

### 4.8 Infraestrutura de dados

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
                        └──── DEVOLVIDO ───┘         DESPUBLICADO / SUBSTITUIDO

Nova versão:  PUBLICADO --(clona)--> nova v em RASCUNHO
              nova v PUBLICADO ==> versão anterior vira SUBSTITUIDO
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
- Nova versão só pode ser aberta a partir de curso `PUBLICADO`, e só se nenhuma
  outra versão da linhagem estiver em produção.
- Publicar uma versão move automaticamente a anterior para `SUBSTITUIDO`, na mesma
  transação. `SUBSTITUIDO` é terminal: consultável como histórico, fora do catálogo,
  não republicável.

Toda transição roda em transação atômica: muda o status e grava o histórico, ou
nada acontece.

## 6. Validações de envio por entregável

Aplicadas quando o aluno envia o entregável para revisão. A mensagem de erro lista
exatamente o que falta — é ela que evita a ida e volta com o professor.

**A — Plano de Ensino**: ao menos um anexo PDF; ao menos uma seção com conteúdo; e
os dados pedagógicos do **curso** preenchidos — público-alvo, carga horária, formato
e, se houver referencial, número de competências dentro da faixa dele.

Esses últimos são campos do `Curso`, não do `Entregavel` (§4.3): a validação lê
`entregavel.curso`. A checagem é repetida em `submeter_ao_coordenador`, porque o
curso pode ser editado depois que o Plano de Ensino foi aprovado — validar só no
envio do entregável deixaria passar um curso submetido sem carga horária.

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
| `cursos` | `Curso`, `MembroEquipe`, `Entregavel`, `Secao`, `Anexo`, `Arquivo`, `Tema`, `Revisao`, `LogTransicaoCurso`, `services.py`, `permissions.py` |
| `catalogo` | Páginas públicas, busca, `Solicitacao`. Lê `cursos`, nunca escreve nele |
| `turmas` | `Turma`, `Participante` |
| `notificacoes` | `Notificacao` e o comando de envio |

Sem dependências circulares entre apps.

### 7.2 Camada de serviços

Toda transição de estado é uma função em `cursos/services.py`:
`enviar_para_revisao`, `aprovar_entregavel`, `devolver_entregavel`,
`submeter_ao_coordenador`, `publicar_curso`, `despublicar_curso`,
`abrir_nova_versao`, `aceitar_solicitacao`. Cada uma valida, muda o estado, grava
histórico e enfileira notificação, dentro de uma transação.

`aceitar_solicitacao(solicitacao, professor, dados_turma)` **exige o professor
responsável** e cria a `Turma` na mesma transação, fixando a versão do curso
publicada naquele momento. É esse ato que responde "como o professor é atribuído a
uma turma que nasceu de uma solicitação externa": o coordenador o designa ao aceitar,
e é dessa designação que decorre o acesso dele aos participantes (§10). Solicitação
aceita sem turma e sem professor não é um estado alcançável.

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
publicar ou devolver → abrir nova versão de curso publicado → solicitações
recebidas → criar turma → Django Admin para pessoas, edições, temas e referenciais.

**Visitante** — catálogo com busca textual e filtros de público-alvo, tema,
referencial, categoria e formato → página do curso → formulário de solicitação.
Cada linhagem aparece uma única vez, na versão publicada.

## 8. Arquivos

**Limites por tipo**: PDF 20 MB, imagem 10 MB, slides 50 MB, vídeo 1 GB.
Validação pelo conteúdo real do arquivo (assinatura), não pela extensão. Nome em
disco por UUID; o nome original é apenas metadado exibido.

**Upload de vídeo é retomável.** O navegador divide o arquivo em blocos e envia um
a um contra `UploadEmAndamento`, com barra de progresso; queda de conexão retoma de
onde parou. Este é o único ponto do sistema com JavaScript próprio de verdade:
**HTMX não fatia arquivo**. O fatiamento usa `Blob.slice()` em JS simples — da ordem
de 150 linhas, sem dependência nova. Se durante a implementação isso se mostrar mais
espinhoso que o previsto, a alternativa é uma biblioteca minimalista (Resumable.js,
Uppy), e não esticar o HTMX para o que ele não faz. Um GB no upstream doméstico de um aluno leva perto de meia hora — um
POST único que falha aos 90% significa entrega perdida.

**Entrega de arquivo nunca passa pelo Django.** A view confere permissão e delega
ao nginx via `X-Accel-Redirect`. Isso é obrigatório, não otimização: transmitir
1 GB pelo processo Python prende um worker por dez minutos e três downloads
simultâneos derrubam o servidor. O nginx também dá *range requests*, então o vídeo
abre e navega no player em vez de só baixar.

No nginx, o `location` da mídia é marcado **`internal;`** — sem isso, qualquer
pessoa acessa o arquivo pela URL direta e a checagem de permissão do Django vira
decoração. A view define `Content-Disposition: inline` apenas para PDF e vídeo, para
abrirem no navegador; **todo o resto vai como `attachment`**, porque HTML ou SVG
servido inline a partir do nosso domínio é vetor de XSS.

**Formato de vídeo**: MP4/H.264 toca no navegador; outros formatos são aceitos mas
apenas baixados. Sem transcodificação no servidor.

> **Divergência registrada (Plano 4, decidida na revisão de branch).** O sistema
> implementado **recusa** vídeo que não seja MP4, em vez de aceitá-lo como
> download-only. A metade "download-only" já existe e continua valendo para todo o
> resto (`views/midia.INLINE` só tem PDF e MP4); o que não existe é a aceitação de
> outros contêineres de vídeo. Três razões, todas em `apps/cursos/arquivos.py`:
> a validação é por **assinatura de conteúdo**, e um contêiner que o sistema não
> sabe reconhecer é um contêiner dentro do qual ele não sabe recusar um executável;
> a recusa por extensão em `valida_declaracao` acontece **antes do primeiro byte**,
> e um upload de 1 GB só pode ser recusado cedo contra uma lista fechada; e sem
> transcodificação um `.mov` chegaria como um vídeo que o professor **não consegue
> assistir** na revisão — recusar no envio, dizendo "converta para MP4", é uma
> falha melhor do que aceitar um arquivo que ninguém pode revisar. Reabrir a
> decisão é acrescentar a assinatura e o teto do contêiner em `ASSINATURAS`,
> `LIMITES` e `EXTENSOES`, e nada mais.

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

Duas precauções, porque o comando é sequencial e o SMTP da UFSM pode demorar a
responder: o comando processa **em lote limitado** (50 notificações por execução) e
roda sob trava de arquivo (`flock`), para que uma execução lenta não se sobreponha à
seguinte e envie o mesmo e-mail duas vezes. Tentativas com falha usam recuo
progressivo e param depois de um limite, em vez de reprocessar para sempre.

## 10. Permissões e dados pessoais

Checagens centralizadas em `cursos/permissions.py`, chamadas pelos serviços — nunca
espalhadas em `if` de template.

- **Aluno**: só cursos onde é `MembroEquipe`. Edita seções e anexos apenas com o
  entregável em `RASCUNHO` ou `DEVOLVIDO`. Nunca aprova.
- **Professor**: total sobre os cursos que responde, incluindo abrir nova versão
  deles. Não publica, não mexe em curso alheio, não vê participantes de turma alheia.
- **Coordenador**: acesso total; publica, despublica e abre nova versão; Admin.
- **Abrir nova versão**: coordenador ou o professor responsável pelo curso, sempre
  com motivo registrado. A equipe da nova versão não herda acesso à anterior — ela
  já está publicada e é pública de qualquer forma.
- **Visitante**: exclusivamente cursos `PUBLICADO`.

**Anexos de curso em produção não são servidos pelo `MEDIA_URL`.** Todo download
passa pela view de permissão descrita no §8; URL de arquivo vaza com facilidade, e
material não aprovado não pode circular.

**Dados pessoais entram por três lugares.** Usuários internos (nome, e-mail, CPF,
matrícula ou SIAPE — §4.1), solicitantes externos e participantes de turma.

O CPF nunca aparece em tela pública, em listagem de equipe ou em página de curso.
No Django Admin é exibido mascarado na listagem e visível apenas na ficha da pessoa,
acessível só ao coordenador. Nenhuma tela de aluno ou de professor mostra o CPF de
outra pessoa.

**Os dados de terceiros** — solicitantes externos e participantes de turma — Consequências: aviso de finalidade no formulário público, acesso restrito ao
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
   equipe, anônimo baixando anexo não publicado, professor vendo turma alheia, CPF
   aparecendo em resposta que não seja do coordenador).
   Também: aluno sem matrícula e professor sem SIAPE são recusados; CPF com dígito
   verificador inválido é recusado; CPF, matrícula e SIAPE gravam normalizados e a
   unicidade pega o mesmo número escrito de duas formas.
3. **Validações do §6**: caderno sem gabarito, card sem referência, 1 ou 4 vídeos,
   competências fora da faixa do referencial, curso sem referencial passando limpo.
4. **Versionamento**: clone não duplica arquivo em disco; versão anterior segue
   publicada durante o trabalho; publicar a nova substitui a anterior; catálogo
   mostra uma linhagem uma vez só; segunda versão simultânea é recusada.

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
que ninguém reclamou); remoção de `Arquivo` órfão.

A remoção de órfãos tem uma corrida a evitar: entre o fim do upload e o salvamento
do `Anexo` existe uma janela em que o arquivo não tem referência nenhuma e não é
lixo. Por isso a rotina só considera `Arquivo` **sem anexos e criado há mais de
24 h**, e seleciona com `select_for_update()`. Deliberadamente **não** usamos
contador de referências: contador denormalizado desanda em exclusão em lote,
rollback ou clone de versão, e o modo de falha é apagar arquivo que ainda está em
uso.

**Carga inicial**: fixture da BNCC da Computação (categorias e competências por
etapa), fixture de temas iniciais, edição corrente, usuário coordenador.

## 14. Fora de escopo na primeira versão

Decidido deliberadamente, para não inflar a entrega:

- Certificado, controle de frequência, avaliação e acompanhamento de turma em
  andamento — tudo isso é o módulo de execução (§1.1), não corte arbitrário
- Login institucional / SSO da UFSM
- Auto-cadastro de usuários
- Comparação lado a lado entre versões de um curso (o histórico existe; a
  ferramenta de *diff* não)
- Versionamento de seções e arquivos dentro de uma mesma versão do curso
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
| Um só modelo de usuário com validação condicional, sem perfil por papel | Poucos campos e base pequena; `OneToOne` por papel custaria consultas sem dar garantia nova |
| CPF, matrícula e SIAPE normalizados e únicos, CPF com dígito conferido | Sem normalizar, a unicidade não vale nada; CPF digitado errado só aparece anos depois |
| CPF coletado com finalidade declarada e nunca exibido fora do Admin | Não tem uso no módulo de produção; existe para o certificado do módulo de execução |
| `Turma`/`Participante` mínimos, sem frequência nem certificado | Este é o módulo de produção; execução vem depois e cresce a partir de `turmas` |
| `turmas` depende de `cursos`, nunca o contrário | Mantém o núcleo de produção intocado quando o módulo de execução for construído |
| Melhoria de curso publicado gera nova versão, não edição no lugar | A versão no ar continua solicitável durante o trabalho, e a evolução do curso fica registrada |
| `Arquivo` separado de `Anexo`, compartilhado entre versões | Clonar curso não pode clonar gigabytes de vídeo |
| Tema controlado para filtrar, palavra-chave livre para buscar | Filtro com texto livre se fragmenta e para de encontrar as coisas |
| Seções padrão criadas por serviço, não por sinal `post_save` | Sinal é invisível, mal testável e contraria a regra de que só serviços mudam estado |
| Limpeza de arquivo órfão por idade + `select_for_update`, sem contador de referências | Contador denormalizado desanda e o modo de falha é apagar arquivo em uso |
| `location` da mídia `internal;` no nginx | Sem isso a URL direta burla toda a checagem de permissão |
| JS próprio com `Blob.slice()` para o upload em blocos | HTMX não fatia arquivo; é o único ponto do sistema que precisa de JS de verdade |
