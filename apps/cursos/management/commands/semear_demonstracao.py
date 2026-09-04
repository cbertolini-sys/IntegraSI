"""Semeia o ambiente de teste: as pessoas da lista e dois cursos publicados.

Existe para que a preparacao do servidor de teste seja revisavel e repetivel, em
vez de Python digitado a mao em producao.

**Ele nao manda convite.** O sistema cria conta por convite, e o convite vai por
e-mail; os enderecos da lista sao de um dominio que nao existe, entao o convite
so geraria devolucao. Por isso as contas nascem com o perfil ja completo e uma
senha conhecida. O fluxo de convite se testa a parte, com um endereco real.

O ciclo do curso passa inteiro pelos servicos (`criar_curso`, `adicionar_membro`,
`enviar_para_revisao`, `aprovar_entregavel`, `submeter_ao_coordenador`,
`publicar_curso`), e nao por escrita direta de status: e a mesma regra do resto
do projeto, e e o que faz o curso semeado ter historico de transicoes de verdade.
As CONTAS, sim, sao criadas direto, porque todo servico de conta e baseado em
convite.
"""

import hashlib
import re

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cursos import services
from apps.cursos.choices import (
    Formato,
    Rotulo,
    StatusCurso,
    TipoMidia,
    TipoPratica,
    TipoPublico,
)
from apps.cursos.models import Anexo, Arquivo, Curso
from apps.notificacoes.models import Notificacao

Usuario = get_user_model()

# `- 1 Coordenador:`, `- 2 Professores:`, `- 5 Alunos:`
CABECALHO = re.compile(r"^\s*-\s*\d+\s+(coordenador|professor|aluno)", re.IGNORECASE)
# `* Nome: Nick Fury | Email: nick@escola.com`
PESSOA = re.compile(r"\*\s*Nome:\s*(?P<nome>[^|]+?)\s*\|\s*Email:\s*(?P<email>\S+)", re.IGNORECASE)

PAPEL_DO_CABECALHO = {
    "coordenador": Usuario.COORDENADOR,
    "professor": Usuario.PROFESSOR,
    "aluno": Usuario.ALUNO,
}

# Prefixo alto de proposito: nenhum CPF real comeca com 900, entao o dado de
# teste se distingue a olho no Admin.
PREFIXO_CPF = "9000000"

SECOES_ESCRITAS = {
    "Ementa": "<p>Percurso introdutório, construído para caber em encontros curtos e "
    "sem depender de laboratório montado.</p>",
    "Objetivos": "<p>Ao final, a turma reconhece o conceito central, resolve "
    "problemas simples com ele e explica o próprio raciocínio.</p>",
    "Público-alvo": "<p>Turmas do ensino básico, em grupos de até 30 pessoas, com um "
    "professor acompanhando.</p>",
    "Metodologia": "<p>Encontros curtos, atividade em dupla e fechamento coletivo. "
    "Cada encontro termina com algo produzido pela turma.</p>",
    "Recursos necessários": "<p>Sala com mesas móveis, papel, canetas e o material "
    "impresso do curso. Computador é desejável, não obrigatório.</p>",
    "Cronograma": "<p>Quatro encontros de três horas: conceito, prática guiada, "
    "produção livre e apresentação.</p>",
    "Avaliação": "<p>Observação da participação e da produção de cada dupla. Não há "
    "prova: o critério é conseguir explicar a solução construída.</p>",
    "Referências": "<p>Material da BNCC de Computação e roteiros abertos de "
    "computação desplugada.</p>",
}

# O que cada entregavel precisa TER para poder ir a revisao (apps/cursos/validacoes.py).
# Sem isto o `enviar_para_revisao` recusa, e o curso nunca chega a PUBLICADO. Os
# arquivos sao marcadores de texto, e nao PDF de mentira: um .pdf que nao abre e
# pior, para quem esta conhecendo o sistema, que um .txt que abre e se anuncia.
ANEXOS = {
    "SLIDES": [
        {"titulo": "Slides do curso (demonstração)"},
    ],
    "CARDS": [
        {
            "titulo": "Card 1 (demonstração)",
            "referencia_bibliografica": "Material de demonstração do IntegraSI.",
        },
    ],
    "CADERNO": [
        {
            "titulo": "Caderno de atividades, sem gabarito (demonstração)",
            "rotulo": Rotulo.SEM_GABARITO,
            "tipo_pratica": TipoPratica.AMBAS,
        },
        {
            "titulo": "Caderno de atividades, com gabarito (demonstração)",
            "rotulo": Rotulo.COM_GABARITO,
            "tipo_pratica": TipoPratica.AMBAS,
        },
    ],
    "VIDEOS": [
        {"titulo": "Vídeo 1 (demonstração)", "tipo_midia": TipoMidia.VIDEO, "duracao_minutos": 7},
        {"titulo": "Vídeo 2 (demonstração)", "tipo_midia": TipoMidia.VIDEO, "duracao_minutos": 6},
    ],
    "AVALIACAO": [
        {"titulo": "Instrumento de avaliação (demonstração)"},
    ],
}

CURSOS = [
    {
        "titulo": "Pensamento computacional desplugado",
        "resumo": (
            "Algoritmos, sequências e repetição com papel, barbante e cartas. A turma "
            "resolve problemas de computação antes de encostar em qualquer tela."
        ),
        "tipo_publico": TipoPublico.ESCOLAR,
        "etapa_ano": "EF05",
        "carga_horaria": 12,
        "formato": Formato.PRESENCIAL,
        "palavras_chave": "pensamento computacional, algoritmo, desplugado, lógica, oficina",
    },
    {
        "titulo": "Senhas, golpes e privacidade",
        "resumo": (
            "O que acontece quando alguém clica no link errado. Reconhecer golpe, "
            "escolher senha que se lembra e entender o que se entrega ao aceitar um app."
        ),
        "tipo_publico": TipoPublico.ESCOLAR,
        "etapa_ano": "EF09",
        "carga_horaria": 8,
        "formato": Formato.HIBRIDO,
        "palavras_chave": "segurança, senha, golpe, privacidade, cidadania digital",
    },
]


def cpf_de_teste(indice):
    """Um CPF ficticio com digitos verificadores corretos.

    O modelo valida CPF em `full_clean()`, entao numero inventado ao acaso faria
    a conta nem gravar. Deterministico pelo indice para a semeadura ser repetivel.
    """
    base = f"{PREFIXO_CPF}{indice:02d}"
    for tamanho in (9, 10):
        soma = sum(int(base[i]) * (tamanho + 1 - i) for i in range(tamanho))
        base += str((soma * 10) % 11 % 10)
    return base


def ler_pessoas(caminho):
    """Le a lista, tolerando a prosa em volta.

    `utf-8-sig` porque o arquivo veio com marca de ordem de byte no inicio, e sem
    isso a primeira linha chega com um caractere invisivel grudado.
    """
    with open(caminho, encoding="utf-8-sig") as arquivo:
        linhas = arquivo.read().splitlines()

    pessoas, papel = [], None
    for linha in linhas:
        cabecalho = CABECALHO.match(linha)
        if cabecalho:
            papel = PAPEL_DO_CABECALHO[cabecalho.group(1).lower()]
            continue
        pessoa = PESSOA.search(linha)
        if pessoa and papel:
            pessoas.append(
                {
                    "papel": papel,
                    "nome": pessoa.group("nome").strip(),
                    "email": pessoa.group("email").strip().lower(),
                }
            )
    if not pessoas:
        raise CommandError(f"Nenhuma pessoa reconhecida em {caminho}.")
    return pessoas


class Command(BaseCommand):
    help = "Cria as pessoas da lista e dois cursos publicados, para testes."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", default="deploy/usersTemp.txt")
        parser.add_argument("--senha", required=True, help="Senha inicial de todos.")

    @transaction.atomic
    def handle(self, *args, **opcoes):
        pessoas = ler_pessoas(opcoes["arquivo"])
        senha = opcoes["senha"]

        contas = {}
        for indice, dados in enumerate(pessoas, start=1):
            contas[dados["email"]] = self._conta(indice, dados, senha)

        coordenador = next(
            c for c in contas.values() if c.papel == Usuario.COORDENADOR
        )
        professores = [c for c in contas.values() if c.papel == Usuario.PROFESSOR]
        alunos = [c for c in contas.values() if c.papel == Usuario.ALUNO]
        if not professores:
            raise CommandError("A lista precisa de ao menos um professor.")

        for numero, ficha in enumerate(CURSOS):
            professor = professores[numero % len(professores)]
            # Fatia alternada: com 5 alunos e 2 cursos, um fica com 3 e outro com
            # 2, e ninguem fica de fora. `[numero::len(CURSOS)]` em vez de metade
            # exata para nao deixar equipe vazia quando a lista for impar.
            equipe = alunos[numero :: len(CURSOS)]
            self._curso(ficha, professor, equipe, coordenador)

        self._avisar_dos_coordenadores(contas)
        self._limpar_fila(contas)
        self.stdout.write(
            f"{len(contas)} contas e "
            f"{Curso.objects.filter(status=StatusCurso.PUBLICADO).count()} cursos publicados."
        )

    def _conta(self, indice, dados, senha):
        """Cria a conta ja com o perfil completo, ou devolve a que existe.

        Perfil completo porque nao ha convite: sem CPF (e SIAPE ou matricula), o
        `PerfilCompletoMiddleware` prenderia a pessoa numa tela da qual ela nao
        teria como sair.
        """
        existente = Usuario.objects.filter(email__iexact=dados["email"]).first()
        if existente:
            self.stdout.write(f"  ja existia: {dados['email']}")
            return existente

        conta = Usuario(
            email=dados["email"],
            nome_completo=dados["nome"],
            papel=dados["papel"],
            cpf=cpf_de_teste(indice),
            # `promover_a_coordenador` liga os dois juntos, e este comando gravava
            # so o papel: o coordenador semeado tinha poder de coordenacao dentro
            # do sistema e nenhum acesso ao Admin, que e justamente a porta por
            # onde a coordenacao destrava conta presa (e a unica que o
            # PerfilCompletoMiddleware deixa passar de proposito). Achado olhando
            # o servidor, com a suite verde.
            is_staff=dados["papel"] == Usuario.COORDENADOR,
        )
        if dados["papel"] == Usuario.ALUNO:
            conta.matricula = f"90000{indice:03d}"
            conta.telefone = "(55) 99999-0000"
        else:
            conta.siape = f"90000{indice:03d}"
        conta.set_password(senha)
        conta.save()
        return conta

    def _curso(self, ficha, professor, equipe, coordenador):
        if Curso.objects.filter(titulo=ficha["titulo"]).exists():
            self.stdout.write(f"  ja existia: {ficha['titulo']}")
            return

        curso = services.criar_curso(professor_responsavel=professor, **ficha)
        for aluno in equipe:
            services.adicionar_membro(curso, aluno, por=professor)

        plano = curso.entregaveis.get(tipo="PLANO_ENSINO")
        for secao in plano.secoes.all():
            secao.conteudo = SECOES_ESCRITAS.get(
                secao.titulo, "<p>Conteúdo de demonstração.</p>"
            )
            secao.save()

        quem_envia = equipe[0] if equipe else professor
        for entregavel in curso.entregaveis.all():
            for dados in ANEXOS.get(entregavel.tipo, []):
                self._anexo(entregavel, dados, quem_envia)
        curso.refresh_from_db()

        for entregavel in curso.entregaveis.all():
            services.enviar_para_revisao(entregavel, por=quem_envia)
            services.aprovar_entregavel(
                entregavel, por=professor, comentario="Aprovado na semeadura de teste."
            )

        curso.refresh_from_db()
        services.submeter_ao_coordenador(curso, por=professor)
        services.publicar_curso(curso, por=coordenador)
        self.stdout.write(f"  publicado: {ficha['titulo']}")

    def _anexo(self, entregavel, dados, por):
        """Um anexo com arquivo de verdade, porque a validacao de envio o exige.

        `Arquivo` e criado direto: o caminho normal e o upload em blocos, que
        pressupoe navegador. Os campos calculados (tamanho, hash) sao preenchidos
        aqui pelo mesmo motivo de sempre - sao dado derivado, e deixa-los errados
        faria a tela de materiais mentir.
        """
        conteudo = (
            f"{dados['titulo']}\n\n"
            "Arquivo de demonstracao do IntegraSI. Substitua por material real.\n"
        ).encode()
        nome = re.sub(r"[^a-z0-9]+", "-", dados["titulo"].lower()).strip("-") + ".txt"
        arquivo = Arquivo.objects.create(
            nome_original=nome,
            tamanho=len(conteudo),
            mime="text/plain",
            hash_conteudo=hashlib.sha256(conteudo).hexdigest(),
            enviado_por=por,
        )
        arquivo.arquivo.save(nome, ContentFile(conteudo), save=True)
        Anexo.objects.create(
            entregavel=entregavel,
            arquivo=arquivo,
            enviado_por=por,
            tipo_midia=dados.get("tipo_midia", TipoMidia.ARQUIVO),
            titulo=dados["titulo"],
            referencia_bibliografica=dados.get("referencia_bibliografica", ""),
            rotulo=dados.get("rotulo", Rotulo.NENHUM),
            tipo_pratica=dados.get("tipo_pratica", TipoPratica.NENHUM),
            duracao_minutos=dados.get("duracao_minutos"),
        )

    def _avisar_dos_coordenadores(self, contas):
        """Diz o preco de ter criado coordenador, sem recusar a fazer.

        Todo coordenador ativo recebe aviso de solicitacao da comunidade e de
        curso submetido. Com endereco que nao existe, cada uma dessas acoes vira
        devolucao contra a conta que assina os envios, e devolucao acumulada
        derruba a reputacao do remetente. Aconteceu com a semeadura de 04/09 e
        custou um rebaixamento a mao em producao.

        O comando nao recusa porque nao tem como saber quais enderecos existem: a
        lista e que manda. Mas quem roda precisa saber o que acabou de ligar.
        """
        novos = [c for c in contas.values() if c.papel == Usuario.COORDENADOR]
        if not novos:
            return
        self.stdout.write(
            f"  ATENCAO: {len(novos)} coordenador(es) na lista "
            f"({', '.join(c.email for c in novos)})."
        )
        self.stdout.write(
            "  Todo coordenador ativo recebe aviso de solicitacao da comunidade e de "
            "curso submetido. Se o endereco nao existir, cada aviso vira uma devolucao "
            "contra a conta que assina os envios. Use endereco entregavel, ou rebaixe "
            "depois com contas.services.rebaixar_a_professor."
        )

    def _limpar_fila(self, contas):
        """Descarta os avisos que a propria semeadura gerou para as contas de teste.

        `adicionar_membro` e `submeter_ao_coordenador` enfileiram e-mail, e esses
        enderecos nao existem: o cron tentaria a cada 5 minutos e cada tentativa
        viraria devolucao contra a conta que assina o envio. Avisos para endereco
        real (a coordenacao de verdade, por exemplo) ficam na fila.
        """
        apagados, _ = Notificacao.objects.filter(
            enviado_em__isnull=True, destinatario__in=list(contas)
        ).delete()
        if apagados:
            self.stdout.write(f"  {apagados} avisos de teste retirados da fila.")
