# Operação do IntegraSI

Roteiro de instalação, conferência e manutenção do servidor. Os arquivos de
configuração citados estão em `deploy/`; este documento diz o que fazer com eles
e (mais importante) **o que precisa ser conferido contra o servidor no ar**,
porque a suíte de testes só conhece os arquivos do repositório.

Ambiente alvo (spec §13): Ubuntu, PostgreSQL, gunicorn atrás de nginx, systemd,
configuração inteira por variável de ambiente.

---

## 1. Instalação

### 1.1 Sistema e usuário

```bash
sudo apt install python3.13 python3.13-venv postgresql nginx
sudo adduser --system --group --home /srv/integrasi integrasi
```

A mídia mora em volume separado do sistema, porque ela cresce e o resto não
(spec §13). Monte o volume em `/srv/integrasi/media` **antes** do primeiro
upload; movê-la depois exige parar o serviço.

```bash
sudo mkdir -p /srv/integrasi/media /var/log/integrasi /srv/backups/sql
sudo chown integrasi:www-data /srv/integrasi/media /var/log/integrasi
```

### 1.2 Banco e a extensão `unaccent`

A busca do catálogo usa a configuração de texto `portugues_unaccent`, criada pela
migração `cursos/0008_busca.py`. Essa migração roda:

```sql
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE TEXT SEARCH CONFIGURATION portugues_unaccent (COPY = portuguese);
```

**`CREATE EXTENSION` exige privilégio que um papel comum não tem.** Sem ele o
`migrate` para com `permission denied to create extension "unaccent"`, e a
instalação não avança - a coluna gerada de `Curso` e o índice de busca dependem
dessa configuração de texto. É a dívida que o Plano 1 deixou para cá.

Caminho normal - crie o banco com um papel superusuário e deixe a aplicação usar
um papel comum:

```bash
sudo -u postgres createuser --pwprompt integrasi
sudo -u postgres createdb --owner=integrasi integrasi
```

Ser dono do banco **não** basta para criar extensão. Se o `migrate` reclamar de
permissão, use uma destas saídas, nesta ordem de preferência:

1. **Criar a extensão como superusuário, antes do `migrate`.** A migração usa
   `CreateExtension`, que é idempotente: encontrando a extensão pronta, ela
   segue adiante.

   ```bash
   sudo -u postgres psql -d integrasi -c 'CREATE EXTENSION IF NOT EXISTS unaccent;'
   ```

   A configuração de texto (`CREATE TEXT SEARCH CONFIGURATION`) o dono do banco
   cria sem privilégio especial, então o resto da migração passa.

2. **PostgreSQL 13+ com `unaccent` marcada como *trusted*** (é o caso nas
   distribuições recentes): o dono do banco pode criar a extensão sozinho e nada
   precisa ser feito.

3. **Conceder o papel `pg_create_extension`** ou rodar a migração uma única vez
   com um papel superusuário, voltando depois ao papel comum na `DATABASE_URL`.

**A restauração tropeça no mesmo requisito, e por isso a instalação faz mais dois
passos.** O dump traz `CREATE EXTENSION unaccent` e o banco de destino precisa
aceitá-lo, só que `deploy/restaurar-teste.sh` roda como o papel da aplicação, que
não é superusuário. Resolva de uma vez, ainda na instalação:

```bash
# 1. unaccent no template1: todo banco criado a partir daqui ja nasce com ela, e
#    o CREATE EXTENSION IF NOT EXISTS do dump vira no-op.
sudo -u postgres psql -d template1 -c 'CREATE EXTENSION IF NOT EXISTS unaccent;'

# 2. o papel precisa poder criar o banco descartavel do drill.
sudo -u postgres psql -c 'ALTER ROLE integrasi CREATEDB;'
```

Sem o passo 1 o drill para em `permission denied to create extension "unaccent"`;
sem o passo 2, em `permission denied to create database`. O `COMMENT ON EXTENSION`
que o `pg_dump` emite em seguida continua exigindo a posse da extensão: o drill
descarta essa linha, e o porquê está escrito nele.

Confira ao final que ficou tudo no lugar:

```bash
psql -d integrasi -c "\dx unaccent"
psql -d integrasi -c "\dF portugues_unaccent"
```

### 1.3 Código e ambiente

```bash
sudo -u integrasi git clone <repo> /srv/integrasi
cd /srv/integrasi
sudo -u integrasi python3.13 -m venv .venv
sudo -u integrasi .venv/bin/pip install -e .
sudo -u integrasi cp .env.example .env   # e edite
```

No `.env` de produção, além de `SECRET_KEY`, `DATABASE_URL` e `ALLOWED_HOSTS`:

| Chave | Valor em produção | O que quebra se estiver errada |
|---|---|---|
| `DEBUG` | `False` | stack trace e SQL na cara do visitante |
| `USAR_X_ACCEL` | `True` | vídeo de 1 GB saindo de dentro de um worker Python |
| `CONFIAR_NO_PROXY` | `True` | limite por IP vira limite global (todo mundo atrás do nginx é 127.0.0.1) |
| `SEGURANCA_HTTPS` | `True` | sem redirecionamento https, sem cookie `Secure`, sem HSTS |
| `CAMINHO_DO_LOG` | `/var/log/integrasi/app.log` | sem log de aplicação: um 500 só deixa rastro no stderr do gunicorn |
| `ADMINS` | `Nome:email`, separados por vírgula | ninguém é avisado de erro 500 |

As três primeiras nascem ligadas quando `DEBUG=False`; estão no `.env.example`
para ficarem explícitas, não porque o padrão dependa delas.
**`CONFIAR_NO_PROXY=True` só é correto com o nginx na frente** - gunicorn exposto
direto na rede tem que deixar `False`, senão o `X-Forwarded-For` é texto do
cliente.

`CAMINHO_DO_LOG` e `ADMINS` são diferentes: **não** têm padrão ligado, de
propósito. As três de segurança produzem a configuração segura quando esquecidas;
esta abre um arquivo no disco, e um caminho impossível faz o processo **não
subir** (o handler é construído na carga das settings). Por isso o diretório
precisa existir antes do primeiro start:

```bash
sudo mkdir -p /var/log/integrasi
sudo chown integrasi:integrasi /var/log/integrasi
```

O mesmo diretório recebe a saída do cron (`deploy/crontab`). A rotação do
`app.log` é do próprio Django (10 arquivos de 10 MB); os `.log` do cron ficam por
conta do `logrotate` da máquina.

```bash
sudo -u integrasi .venv/bin/python manage.py migrate
sudo -u integrasi .venv/bin/python manage.py loaddata bncc_computacao temas_iniciais
sudo -u integrasi .venv/bin/python manage.py criar_coordenador \
    --email ... --nome ... --cpf ... --siape ... --senha ...
sudo -u integrasi .venv/bin/python manage.py collectstatic --noinput
```

`createsuperuser` não funciona neste projeto (o `REQUIRED_FIELDS` omite `siape`
de propósito); o coordenador inicial sai do `criar_coordenador`.

A carga da BNCC completa (habilidades) é descrita em `docs/dados/README.md`. Os
códigos vêm transcritos da Resolução CNE/CEB nº 1/2022 - **nunca inventados**.

### 1.4 Rotação dos logs

```bash
sudo install -o root -g root -m 644 deploy/logrotate-integrasi /etc/logrotate.d/integrasi
sudo logrotate -f -d /etc/logrotate.d/integrasi   # simula, não escreve nada
```

**Confira a saída da simulação, e não só o código de retorno.** O `logrotate`
ignora em silêncio um arquivo de configuração que não seja do root, e a
mensagem ("Ignoring ... because the file owner is wrong") passa despercebida
entre dezenas de linhas de depuração. Foi o que aconteceu na primeira
instalação.

O `app.log` **não** entra nessa rotação, e a razão está escrita no próprio
arquivo: ele já rotaciona pelo `RotatingFileHandler` do Django, e incluí-lo
quebraria o log. O gunicorn mantém o arquivo aberto, o `logrotate` rotaciona
renomeando, e o processo continuaria escrevendo no arquivo renomeado enquanto o
`app.log` novo ficaria vazio até o próximo reinício.

### 1.5 Serviço, proxy e cron

```bash
sudo cp deploy/integrasi.service /etc/systemd/system/
sudo systemctl enable --now integrasi

sudo cp deploy/nginx.conf /etc/nginx/sites-available/integrasi
sudo ln -s /etc/nginx/sites-available/integrasi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo crontab -u integrasi /srv/integrasi/deploy/crontab
```

Antes de instalar o cron, ajuste o `MAILTO=` do `deploy/crontab` para um endereço
que alguém lê (§4).

---

## 2. Conferências que só o servidor no ar dá

**Os testes automatizados leem os arquivos do repositório.** Eles provam que o
`deploy/nginx.conf` versionado está certo; não provam que o nginx em execução
está rodando esse arquivo. Faça as conferências abaixo uma vez, no deploy, e a
cada mudança no nginx. Anote o resultado.

### 2.1 O `internal;` da mídia - a mais importante de todas

Sem `internal;` no `location /protegido/`, qualquer pessoa - sem sessão, sem
conta - pede a URL direta e recebe material não aprovado. A view de permissão
continua perfeitamente correta e o sistema fica escancarado. **Nenhum teste da
suíte alcança isso**, porque o Django nunca vê essa requisição.

```bash
# 1. Sem cookie nenhum, direto no prefixo interno. TEM QUE responder 404.
curl -i https://integrasi.ufsm.br/protegido/materiais/ab/abcdef0123456789

# 2. Se responder 200, PARE: o `internal;` não está no bloco que casa com o
#    prefixo emitido pela view. Corrija e repita antes de liberar o sistema.
```

Complemento: a rota do Django, **com** cookie de sessão de quem é da equipe, tem
que devolver 200 com o corpo do arquivo (quem transmite é o nginx):

```bash
curl -i -b "sessionid=<da sessão>" https://integrasi.ufsm.br/materiais/<uuid>/
```

Um 404 aqui, com o (1) devolvendo 404 também, costuma ser desencontro entre o
`alias` do `location /protegido/` e o `MEDIA_ROOT` - barulhento, não perigoso.

### 2.2 HTTPS, HSTS e cookies

**Feito em 04/09/2026.** O DNS veio do CPD: `integrasi.ufsm.br` é apelido de
`integrasi.cfw.ufsm.br`, que aponta para 200.132.38.187.

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d integrasi.ufsm.br -d integrasi.cfw.ufsm.br
```

**`certonly`, e não `certbot --nginx` puro.** O segundo reescreve a configuração
do nginx, e a deste servidor é versionada em `deploy/nginx.conf`: deixar o certbot
mexer nela faz o servidor divergir do repositório em silêncio, e a divergência só
aparece quando alguém compara os dois.

Depois, no `.env`, **apague** a linha `SEGURANCA_HTTPS=False` em vez de trocá-la
para `True`: o padrão com `DEBUG=False` já liga tudo, e uma linha a menos é uma
chance a menos de a configuração e o padrão discordarem. E ponha o domínio no
`ALLOWED_HOSTS`, mantendo o IP, para quem tiver o endereço antigo guardado.

Confira, e não confie:

```bash
.venv/bin/python manage.py check --deploy    # tem que dizer "no issues"
curl -sI https://integrasi.ufsm.br/ | grep -i strict-transport
curl -sI https://integrasi.ufsm.br/contas/login/ | grep -i set-cookie   # tem que ter Secure
curl -s -o /dev/null -w "%{http_code}\n" https://integrasi.ufsm.br/protegido/qualquer  # 404
```

**A renovação é a parte que falha calada.** O certificado vale 90 dias e o
`certbot.timer` renova sozinho; o que precisa ser provado é que ele consegue:

```bash
sudo certbot renew --dry-run
```

Duas coisas fazem essa renovação funcionar, e as duas estão em `deploy/nginx.conf`:
o bloco 80 tem uma exceção para `/.well-known/acme-challenge/` **antes** do
`return 301` (sem ela o desafio é redirecionado para https e a renovação falha), e
o `ssl_certificate` aponta para `/etc/letsencrypt/live/`, que a renovação
reescreve, e não para uma cópia em `/etc/ssl`, que ficaria velha.

Com HSTS de um ano ligado, certificado vencido **não é uma tela feia, é um site
inacessível**: o navegador recusa a conexão e não oferece como prosseguir. Rode o
ensaio acima depois de qualquer mexida em nginx.

### 2.3 O limite por IP do formulário público

O formulário do catálogo é a única porta anônima que escreve no banco (spec §10).
O limite é de 5 solicitações por IP por hora.

```bash
# Seis vezes, forjando um X-Forwarded-For diferente a cada vez. A sexta TEM QUE
# ser recusada: o cabeçalho forjado não pode ganhar cota nova.
for i in $(seq 6); do
  curl -s -o /dev/null -w '%{http_code} ' -X POST \
    -H "X-Forwarded-For: 9.9.9.$i" \
    https://integrasi.ufsm.br/cursos/<id>/solicitar/ --data '...'
done
```

Isso confere as duas camadas ao mesmo tempo: o nginx sobrescrevendo o cabeçalho
com `$remote_addr` e o Django lendo o **último** elemento da lista. Se as
solicitações passarem todas, uma das duas está errada.

---

### A conferência da entrega protegida, por comando

O `curl` à mão continua valendo, mas existe um comando que faz a mesma coisa e
devolve código de saída - serve no deploy e no cron:

```bash
python manage.py conferir_entrega_protegida --base-url https://integrasi.ufsm.br
```

- **Sai 0** e diz "porta fechada": o nginx recusou a rota (404 ou 403), como deve.
- **Sai diferente de 0**: ou a rota respondeu 200 - e aí qualquer pessoa baixa
  material sem passar pela checagem de permissão, corrija o `internal;` e recarregue
  o nginx agora - , ou o servidor não respondeu, e nesse caso **a conferência não
  foi feita**: o comando reprova em vez de dar por seguro o que não checou.

O caminho conferido sai de `apps.cursos.views.midia.PREFIXO_INTERNO`, e não de uma
string repetida no comando: trocar o prefixo no código sem trocar no nginx é um dos
jeitos de abrir a porta, e a conferência acompanha o código.

Rode **depois de instalar, depois de qualquer mudança no nginx**, e uma vez por
semana pelo cron.

## 3. Backup e restauração

Backup são dois problemas distintos (spec §13), e nesta instalação cada um tem
um dono diferente:

| O que salva de | Quem faz | Onde |
| --- | --- | --- |
| erro humano (curso apagado, `migrate` errado) | `deploy/backup.sh`, 02:05 | `pg_dump` diário em `/srv/backups/sql`, 30 dias |
| perder a máquina (disco, VM, datacenter) | **CPD da UFSM** | backup diário da máquina virtual inteira |

**A segunda linha é uma dependência externa, e é o ponto frágil desta seção.**
O backup do CPD leva o disco inteiro, e portanto leva junto tanto a mídia em
`/srv/integrasi/media` quanto os dumps que o `backup.sh` deixa em
`/srv/backups/sql`. É por isso que o dump fica no disco da própria VM de
propósito, em vez de num destino externo com ferramenta própria: seria copiar
duas vezes a mesma coisa, e cada cópia a mais é uma senha a mais para guardar.

A consequência é que **se esta VM deixar de ser copiada pelo CPD, o sistema fica
sem backup de disco e nada aqui avisa**: o `backup.sh` continua rodando às 02:05,
o drill continua passando e a suíte de testes continua verde. Nenhum teste deste
repositório alcança a máquina virtual. Confirme com o CPD e anote:

| Pergunta ao CPD | Resposta | Conferido em |
| --- | --- | --- |
| Esta VM está no backup diário? | sim (informado pela coordenação) | 04/09/2026 |
| Retenção: quantos dias dá para voltar? | a confirmar | |
| Como se pede uma restauração, e quanto demora? | a confirmar | |

As duas linhas em aberto não são burocracia. Backup que ninguém sabe pedir tem o
mesmo valor prático de backup que não existe, e a hora de descobrir o
procedimento não é a hora em que o disco morreu.

### 3.1 A restauração de teste

**Backup que nunca foi restaurado não é backup.** Rode `deploy/restaurar-teste.sh`
depois do primeiro backup e **uma vez por semestre**. Ele restaura o último dump
num banco descartável, confere que voltou usuário, e derruba o banco no final -
não toca no banco de produção em momento nenhum. Ele depende dos dois passos de
banco da seção 1.2 (`unaccent` no `template1` e `CREATEDB` no papel); sem eles
ele para antes de restaurar a primeira linha.

Ele prova o `pg_dump`, e só ele. A metade do CPD se confere pedindo ao CPD uma
restauração de teste da VM, o que é passo de operador e não tem script aqui.

Anote a data das duas; se ninguém sabe qual foi, não há backup conferido.

| Instalação | Restauração de teste do dump | Restauração de teste da VM (CPD) |
| --- | --- | --- |
| 200.132.38.187 | 03/09/2026 - 1 usuário restaurado, saída 0 | nunca pedida |

---

## 4. Alertas do cron, e o vazamento que eles pegam

**Mais de um endereço no `ADMINS`.** Canal de alerta com um destinatário só falha
exatamente quando essa pessoa está de férias. O formato é uma lista separada por
vírgula, em `Nome:email`:

```
ADMINS=Cristiano:cbertolini@gmail.com,Evandro:evandro.preuss@ufsm.br
```

Conferir que a rota inteira funciona (`ADMINS` até o SMTP) sem precisar derrubar
uma requisição de verdade:

```bash
.venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from django.core.mail import mail_admins
mail_admins('teste da rota de alerta', 'Conferindo o canal.', fail_silently=False)
"
```

É o mesmo caminho que o `AdminEmailHandler` usa quando uma view estoura. Se o
comando não levantar exceção e a mensagem chegar nas duas caixas, o canal está de
pé. **Repita depois de qualquer mudança no SMTP**: um canal de alerta que falha
calado é pior que não ter canal, porque quem confia nele para de olhar o log.



O `deploy/crontab` tem `MAILTO=` e **não** redireciona `stderr` para o log: o
stdout de cada rotina vai para `/var/log/integrasi/cron.log` e todo `stderr` vira
e-mail para o endereço do `MAILTO`. Foi decisão deliberada - com `2>&1`, o único
aviso do problema abaixo iria para um arquivo que ninguém lê.

**O que o alerta pega.** `limpar_arquivos_orfaos` e `limpar_uploads` apagam a
linha do banco dentro da transação e os bytes só depois do commit
(`transaction.on_commit`). A ordem é a correta: ao contrário, um rollback
devolveria o registro ao banco sem os bytes e todo anexo apontaria para um 404
permanente. O preço é este: se o apagamento dos bytes falhar **depois** do commit
(disco cheio, permissão, volume desmontado), as linhas já saíram e os bytes ficam
no disco sem nada apontando para eles. A rotina de órfãos parte de `Arquivo`, e
esse registro não existe mais - ela não os reencontra nunca.

Quando chegar um e-mail de `limpar_arquivos_orfaos` ou `limpar_uploads`:

1. Trate a causa (espaço, permissão do usuário `integrasi` sobre
   `/srv/integrasi/media`, volume montado).
2. Reconcilie o disco com o banco, para achar os bytes que ficaram para trás:

```bash
psql -tAc "select arquivo from cursos_arquivo order by 1" integrasi > /tmp/no-banco.txt
cd /srv/integrasi/media && find materiais -type f | sort > /tmp/no-disco.txt
comm -13 <(sort /tmp/no-banco.txt) /tmp/no-disco.txt   # está no disco e não no banco
```

O que sair dessa última lista é lixo confirmado **desde que nenhum upload esteja
em curso** - rode com o serviço parado, ou desconsidere arquivos criados nas
últimas 24 h (é a mesma janela de segurança que a rotina de órfãos respeita, e
pelo mesmo motivo: entre o fim do upload e o salvamento do `Anexo` o arquivo
legitimamente não tem referência). Apague à mão, conferindo a lista antes.

Notificações que esgotaram as tentativas não somem: aparecem no Django Admin, em
*Notificações*, no filtro **situação → esgotada**. Elas não voltam à fila
sozinhas.

---

## 5. Rotina

| Quando | O quê |
|---|---|
| A cada deploy | `migrate`, `collectstatic`, `systemctl restart integrasi`, `nginx -t && systemctl reload nginx` |
| Contínuo | Monitoração externa em `GET /saude/`: 200 com banco, 503 sem. É o caso que o `Restart=always` do systemd não enxerga - processo vivo e inútil |
| A cada mudança no nginx | repetir a conferência §2.1 |
| Semanalmente | olhar `/var/log/integrasi/cron.log` e a fila esgotada no Admin |
| Semestralmente | `deploy/restaurar-teste.sh` e revisão do certificado TLS |

Logs: `journalctl -u integrasi` (aplicação), `/var/log/integrasi/cron.log`
(rotinas), `/var/log/integrasi/backup.log` (backup),
`/var/log/nginx/{access,error}.log` (proxy).


## 6. Convites de primeiro acesso

O aluno entra no sistema por um convite que o professor dispara ao alocá-lo numa
equipe (Plano 5). O e-mail sai pela mesma fila de tudo, então o diagnóstico é o
mesmo - só o evento muda.

- **Aluno diz que não recebeu:** procure em `/admin/notificacoes/` pelo evento
  `CONVITE_ALUNO` e pelo e-mail dele. Com `ultimo_erro` preenchido, o problema é
  SMTP e o recuo progressivo já está reagendando; a seção 4 explica os alertas do
  cron. Se a notificação nem existe, o convite não chegou a ser criado - confira
  em `/admin/contas/convitealuno/`.
- **Reenvio:** pela tela da equipe do curso, pelo professor responsável ou pela
  coordenação. O reenvio **cancela** o convite anterior: o link antigo para de
  funcionar no ato, e é assim de propósito - dois links vivos dobram a janela em
  que um token vazado ainda serve.
- **Convite vencido:** sete dias, contados da criação. Não há como estender o
  prazo de um convite existente; envie outro.
- **Aluno preso na tela de primeiro acesso:** é o esperado enquanto CPF,
  matrícula e telefone não estiverem preenchidos. Para destravar sem o convite (aluno que perdeu o acesso ao e-mail, por exemplo) a coordenação completa os
  três campos em `/admin/contas/usuario/` e define uma senha.
