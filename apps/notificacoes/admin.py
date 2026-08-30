from django.contrib import admin
from django.utils.text import Truncator

from apps.notificacoes.models import Notificacao
from apps.notificacoes.services import LIMITE_TENTATIVAS


class SituacaoFilter(admin.SimpleListFilter):
    """As tres perguntas que o operador faz sobre a fila. "Esgotada" e a que nao
    aparece em nenhum outro lugar: a notificacao que queimou LIMITE_TENTATIVAS sai
    do filtro do cron e nunca mais e tentada -- ela nao volta sozinha, e sem uma
    tela ninguem descobre que ela existe."""

    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [
            ("pendente", "Pendente"),
            ("esgotada", "Esgotada (não será mais tentada)"),
            ("enviada", "Enviada"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "pendente":
            return queryset.filter(enviado_em__isnull=True, tentativas__lt=LIMITE_TENTATIVAS)
        if self.value() == "esgotada":
            return queryset.filter(enviado_em__isnull=True, tentativas__gte=LIMITE_TENTATIVAS)
        if self.value() == "enviada":
            return queryset.filter(enviado_em__isnull=False)
        return queryset


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    """Janela sobre a fila de e-mail, nao formulario. Divida do Plano 3 que vence na
    rotina de manutencao: sem esta tela, uma fila travada e o `ultimo_erro` que
    explica o travamento so aparecem por shell no servidor. O recuo progressivo
    (spec 9) piorou o quadro -- uma notificacao que falha leva pouco mais de uma
    hora para queimar as cinco tentativas, e durante essa hora nao havia nada que o
    coordenador pudesse olhar.

    Nada aqui e editavel: quem escreve `Notificacao` e `services.enfileirar` e o
    comando `enviar_notificacoes`. Um `enviado_em` limpo a mao reenviaria o e-mail;
    um `tentativas` zerado a mao ressuscitaria a notificacao sem que nenhum service
    tivesse sido chamado -- a mesma razao de `readonly_fields` em CursoAdmin (R56).
    A exclusao segue permitida: e o unico escape para um registro envenenado, e nao
    pula logica de dominio nenhuma."""

    list_display = ["destinatario", "evento", "assunto", "tentativas", "enviado_em", "erro_resumido"]
    list_filter = [SituacaoFilter, "evento"]
    # `destinatario` e um e-mail institucional, nao documento nacional: a restricao
    # do CLAUDE.md sobre `search_fields` vale para CPF, e `email` ja e buscavel em
    # UsuarioAdmin pelo mesmo criterio.
    search_fields = ["destinatario", "assunto"]
    date_hierarchy = "criado_em"
    ordering = ["-criado_em"]
    # Sem `readonly_fields`: com `has_change_permission` falso e permissao de
    # visualizacao, o proprio Admin ja renderiza a tela de detalhe so-leitura e
    # recusa o POST. Duplicar a guarda criaria o par indistinguivel por teste que o
    # CLAUDE.md manda evitar -- com todos os campos readonly, apagar
    # `has_change_permission` deixaria o POST voltar 302 sem alterar nada, e o teste
    # continuaria verde.

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="último erro")
    def erro_resumido(self, obj):
        # Traceback inteiro na coluna espremeria a lista ate o ilegivel; a mensagem
        # completa fica na tela de detalhe.
        return Truncator(obj.ultimo_erro).chars(80)
