from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance

from apps.cursos.arquivos import valida_upload
from apps.cursos.validacoes import DURACAO_MAXIMA, DURACAO_MINIMA
from apps.cursos.choices import (
    PALAVRAS_CHAVE_EXIGIDAS,
    Formato,
    TipoEntregavel,
    TipoPublico,
)
from apps.cursos.models import Anexo, Curso, Secao
from apps.referenciais.choices import ETAPAS, etapa_do_referencial
from apps.referenciais.models import Referencial


class SecaoForm(forms.ModelForm):
    class Meta:
        model = Secao
        fields = ["conteudo"]
        help_texts = {
            "conteudo": (
                "Escreva direto no campo. Aceita negrito, listas e links, e o texto "
                "é salvo sem recarregar a página."
            ),
        }


class PropostaForm(forms.ModelForm):
    """A criacao pede o titulo e mais nada (spec 4.3).

    O resto e trabalho da equipe, cobrado no portao de completude
    (validacoes.dados_do_curso), que ja rodava na revisao do Plano de Ensino e na
    submissao a coordenacao. Exigir a ficha inteira aqui so obrigava o professor a
    inventar carga horaria e publico antes de a equipe estudar o assunto.
    """

    class Meta:
        model = Curso
        fields = ["titulo"]
        help_texts = {
            "titulo": (
                "Um nome provisório basta: você e a equipe ajustam depois. O resto "
                "do curso é preenchido em seguida, na tela de editar."
            ),
        }


# Quais campos o formulario de anexar oferece em cada entregavel.
#
# Cada entregavel tem regras proprias (spec 6), e o formulario oferecia os campos
# de TODOS: referencia bibliografica e dos cards, rotulo e tipo de pratica sao do
# caderno de exercicios. Nos slides eram quatro campos que nao servem a nada.
#
# Lista vazia quer dizer outra coisa: este entregavel nao recebe anexo nenhum por
# aqui. O Plano de Ensino e escrito nas secoes, e a vídeo-aula precisa de
# `TipoMidia.VIDEO`, que so o envio em blocos cria (`services.concluir_upload`) -
# anexo comum nos dois casos e material que a validacao nunca conta.
#
# Entregavel que nao esta aqui mantem o formulario inteiro, ate alguem decidir o
# que ele pede. E de proposito: enxugar por adivinhacao esconderia campo que a
# regra daquele entregavel usa.
CAMPOS_DO_ANEXO = {
    TipoEntregavel.PLANO_ENSINO: [],
    TipoEntregavel.SLIDES: ["titulo", "descricao", "upload"],
    TipoEntregavel.VIDEOS: [],
}


def oferece_anexo(tipo):
    """Se este entregavel recebe material pelo formulario comum de anexar."""
    campos = CAMPOS_DO_ANEXO.get(tipo)
    return campos is None or bool(campos)


class EnvioDeVideoForm(forms.Form):
    """Os campos do envio de video-aula. Serve para DESENHAR a tela, e nao para
    validar: o envio e fatiado em blocos pelo upload.js, que le os campos pelo
    `name` e manda JSON para `upload_concluir` (spec 8). Quem valida e o servico,
    com `Anexo` como autoridade.

    Existe como formulario, e nao como HTML escrito a mao, por causa da ajuda: a
    explicacao de campo mora no `help_text`, em Python, e `tests/test_ajuda.py`
    cobra uma para todo campo de todo formulario do projeto. Escrito a mao, este
    era o unico da interface sem tooltip nenhum, e ficaria de fora dessa regra
    para sempre.

    Os limites saem das mesmas fontes de antes (o campo do `Anexo` e as constantes
    de `validacoes`), so que agora atraves dos widgets. Numero repetido aqui
    divergiria da regra no dia em que ela mudasse.
    """

    upload = forms.FileField(
        label="Vídeo-aula (MP4, até 1 GB)",
        # Sem `required`: quem recusa o envio sem arquivo e o upload.js, com uma
        # mensagem no aviso. O `required` do navegador barraria o submit antes, e
        # o caminho que o cenario do harness exercita nunca rodaria.
        required=False,
        widget=forms.FileInput(attrs={"accept": "video/mp4"}),
        help_text=(
            "O arquivo do vídeo, em MP4. Se a conexão cair no meio, escolha o "
            "mesmo arquivo de novo: o envio retoma de onde parou."
        ),
    )
    titulo = forms.CharField(
        label="Título",
        max_length=Anexo._meta.get_field("titulo").max_length,
        help_text=(
            "Como a vídeo-aula aparece na lista de materiais. Ex.: \u201cAula 1: "
            "o que é um algoritmo\u201d."
        ),
    )
    descricao = forms.CharField(
        label="Descrição",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "data-editor": True}),
        help_text=(
            "O que esta aula cobre, em uma ou duas linhas. Aceita negrito, listas "
            "e links. Opcional."
        ),
    )
    duracao_minutos = forms.IntegerField(
        label="Duração em minutos",
        min_value=DURACAO_MINIMA,
        max_value=DURACAO_MAXIMA,
        help_text=(
            f"Quanto tempo o vídeo tem, em minutos inteiros. O roteiro pede de "
            f"{DURACAO_MINIMA} a {DURACAO_MAXIMA} minutos por aula."
        ),
    )


class AnexoForm(forms.ModelForm):
    upload = forms.FileField(
        label="arquivo",
        required=False,
        help_text="O arquivo em si: PDF, imagem, apresentação ou documento.",
    )
    # Declarado explicitamente (em vez de deixar o ModelForm derivar de Anexo.url)
    # so para fixar assume_scheme="https": sem isso o Django 5.2 emite
    # RemovedInDjango60Warning a cada requisicao, porque o padrao de esquema muda
    # de http para https na proxima versao maior. Continua opcional, como o campo
    # do modelo (Anexo.url tem blank=True).
    url = forms.URLField(
        label="link",
        required=False,
        assume_scheme="https",
        help_text=(
            "Endereço do material, se ele já estiver publicado em outro lugar. "
            "Use o link ou o arquivo, não os dois."
        ),
    )

    class Meta:
        model = Anexo
        fields = ["titulo", "descricao", "referencia_bibliografica", "rotulo", "tipo_pratica", "url"]
        help_texts = {
            "titulo": (
                "Como o material aparece na lista. Ex.: \u201cCartaz sobre senhas "
                "fortes\u201d."
            ),
            "descricao": "Uma linha dizendo para que serve o material. Opcional.",
            "referencia_bibliografica": (
                "De onde veio o conteúdo ou a imagem. Obrigatória nos infográficos "
                "e cards."
            ),
            "rotulo": (
                "No caderno de exercícios, diz se este arquivo é a versão com ou "
                "sem gabarito."
            ),
            "tipo_pratica": (
                "Diz se a atividade precisa de computador. É o que responde "
                "\u201cpreciso de laboratório?\u201d no catálogo."
            ),
        }

    def __init__(self, *args, tipo=None, **kwargs):
        """`tipo` e o entregavel que esta sendo preenchido.

        Sem ele o formulario vem inteiro, que e o comportamento de antes: os
        chamadores que ainda nao passam o tipo continuam funcionando.
        """
        super().__init__(*args, **kwargs)
        permitidos = CAMPOS_DO_ANEXO.get(tipo)
        if permitidos is not None:
            for campo in list(self.fields):
                if campo not in permitidos:
                    del self.fields[campo]

    def clean(self):
        dados = super().clean()
        upload = dados.get("upload")
        if upload:
            cabecalho = upload.read(16)
            upload.seek(0)
            dados["mime"] = valida_upload(upload.name, upload.size, cabecalho)
        elif not dados.get("url"):
            # A mensagem acompanha o formulario: mandar "informe um link" num
            # formulario sem campo de link e instrucao para um campo que a pessoa
            # nao encontra, o que e pior que nenhuma.
            if "url" in self.fields:
                raise forms.ValidationError("Envie um arquivo ou informe um link.")
            raise forms.ValidationError("Envie o arquivo.")
        return dados

    def _post_clean(self):
        # Anexo.clean() confere arquivo/url conforme tipo_midia (Model.clean(), regra
        # que cruza campos - doc "onde mora a validacao" item 2). Mas tipo_midia,
        # arquivo, entregavel e enviado_por nao sao campos deste form: so a view sabe
        # decidir tipo_midia (upload x link) e so ela cria o Arquivo, depois que este
        # form ja validou. Chamar o full_clean() padrao do ModelForm aqui rodaria
        # Anexo.clean() sobre uma instancia sempre pela metade - tipo_midia vazio,
        # arquivo_id nulo - e falharia mesmo numa submissao valida, com um erro num
        # campo ("arquivo") que este form nem declara. Por isso so construimos a
        # instancia e validamos campo a campo; a invariante de tipo_midia/arquivo/url
        # continua garantida, so que no momento certo: Anexo.save() chama full_clean()
        # incondicionalmente, depois que a view preencheu tudo.
        exclude = self._get_validation_exclusions()
        try:
            self.instance = construct_instance(self, self.instance, self._meta.fields, self._meta.exclude)
        except ValidationError as erro:
            self._update_errors(erro)
        try:
            self.instance.clean_fields(exclude=exclude)
        except ValidationError as erro:
            self._update_errors(erro)


class CaixasDePalavraChave(forms.MultiWidget):
    """Uma caixa por palavra, em vez de uma linha com virgulas.

    Deixa obvio quantas se espera e evita que alguem escreva uma frase inteira num
    campo so, que e o que acontecia com o campo de texto livre.
    """

    def __init__(self, attrs=None):
        entradas = [
            forms.TextInput(attrs={"placeholder": f"palavra {i + 1}"})
            for i in range(PALAVRAS_CHAVE_EXIGIDAS)
        ]
        super().__init__(entradas, attrs)

    def decompress(self, value):
        """Reparte o texto gravado de volta nas caixas, para a equipe nao ter de
        reescrever tudo a cada edicao."""
        partes = [p.strip() for p in (value or "").split(",") if p.strip()]
        partes += [""] * PALAVRAS_CHAVE_EXIGIDAS
        return partes[:PALAVRAS_CHAVE_EXIGIDAS]


class PalavrasChaveField(forms.MultiValueField):
    """Cinco caixas que gravam um texto so.

    O campo do banco continua sendo um CharField unico porque e ele que alimenta
    o `search_vector` do curso (spec 4.4); quebrar em cinco colunas obrigaria a
    reescrever a busca para ganhar nada.

    `required=False` de proposito: a obrigatoriedade das cinco e cobrada no portao
    de completude, como todo o resto da ficha, para que a equipe possa salvar o
    trabalho pela metade.
    """

    widget = CaixasDePalavraChave

    def __init__(self, **kwargs):
        campos = [
            forms.CharField(required=False, max_length=50)
            for _ in range(PALAVRAS_CHAVE_EXIGIDAS)
        ]
        kwargs.setdefault("required", False)
        super().__init__(fields=campos, require_all_fields=False, **kwargs)

    def compress(self, valores):
        return ", ".join(v.strip() for v in (valores or []) if v and v.strip())


class FichaCursoForm(forms.ModelForm):
    palavras_chave = PalavrasChaveField(
        label="palavras-chave",
        help_text=(
            f"{PALAVRAS_CHAVE_EXIGIDAS} palavras que ajudem a encontrar o curso na "
            "busca. Podem ficar para depois; a lista de pendências cobra."
        ),
    )

    """A ficha que a equipe preenche depois da proposta (spec 4.3)."""

    class Meta:
        model = Curso
        # A ordem e a da tela, pedida por quem preenche: o que descreve o curso
        # primeiro, depois o publico, depois o referencial com as habilidades
        # coladas nele, e os pre-requisitos por ultimo.
        fields = [
            "titulo", "resumo", "palavras_chave", "temas", "carga_horaria", "formato",
            "tipo_publico", "etapa_ano", "publico_descricao", "referencial",
            "competencias", "pre_requisitos",
        ]
        widgets = {
            "resumo": forms.Textarea(attrs={"rows": 4}),
            # Caixas de marcar, e nao o <select multiple> padrao do Django: aquele
            # exige segurar Ctrl para escolher mais de um, que e conhecimento que
            # ninguem tem por obrigacao. Com poucos temas cadastrados, as caixas
            # cabem em duas linhas e mostram todas as opcoes de uma vez.
            "temas": forms.CheckboxSelectMultiple(),
        }
        help_texts = {
            "titulo": (
                "O nome do curso como a escola vai lê-lo no catálogo. Pode mudar "
                "enquanto o curso não for publicado."
            ),
            "resumo": (
                "Dois ou três parágrafos dizendo o que o curso ensina e para que "
                "serve. É o primeiro texto que a escola lê."
            ),
            "temas": (
                "Assuntos gerais em que o curso se encaixa, usados para filtrar o "
                "catálogo. Marque quantos fizerem sentido."
            ),
            "carga_horaria": (
                "Total de horas do curso, somando todos os encontros. Só o número."
            ),
            "formato": "Como o curso acontece: presencial, híbrido ou online.",
            "tipo_publico": (
                "Escolar, quando o curso é para turmas de uma escola. Comunitário, "
                "quando é para um grupo da comunidade."
            ),
            "etapa_ano": (
                "O ano escolar a que o curso se destina. Fica disponível quando o "
                "tipo de público é escolar."
            ),
            "publico_descricao": (
                "Complemento em texto livre, quando a etapa não diz tudo. Ex.: "
                "\u201cturmas da escola do campo\u201d. Opcional."
            ),
            "pre_requisitos": (
                "O que a turma precisa saber antes de começar. Deixe vazio se o "
                "curso parte do zero."
            ),
        }

    def __init__(self, *args, publico=None, **kwargs):
        """`publico` deixa a view dizer qual tipo a tela tem agora.

        As trocas por HTMX chegam num GET, com o formulario nao vinculado: sem esse
        parametro, o formulario leria o tipo GRAVADO e desenharia os selects do
        estado anterior, que e justamente o que a troca esta desfazendo.
        """
        super().__init__(*args, **kwargs)
        self._publico = publico

        # O vazio que o Django gera e "---------", que nao diz nada. Curso sem
        # referencial e sem etapa sao legitimos (spec 4.2 e publico comunitario),
        # entao as opcoes se chamam pelo nome; senao parecem campo esquecido.
        #
        # `empty_label` aqui, e nao redeclarando o campo: assim o queryset continua
        # vindo da FK, e um referencial desativado que ja esteja gravado nao some
        # do select (sumir o descartaria em silencio no proximo salvamento).
        self.fields["referencial"].empty_label = "Nenhum"
        self.fields["referencial"].help_text = (
            "Modelo pedagógico que o curso segue, se houver. Curso sem referencial "
            "é normal: escolha Nenhum."
        )
        self.fields["competencias"].help_text = (
            "As habilidades do referencial que o curso desenvolve. Marque as que o "
            "curso realmente trabalha."
        )
        self.fields["referencial"].queryset = Referencial.objects.para_publico_escolar(
            self.publico_e_escolar()
        )

        # Curso.clean() ja recusa etapa em curso comunitario. O select oferecia as
        # treze mesmo assim, e a pessoa so descobria ao salvar.
        vazio = [("", "Nenhum")]
        comunitario = self.tipo_publico_em_uso() == TipoPublico.COMUNITARIO
        self.fields["etapa_ano"].choices = vazio if comunitario else vazio + list(ETAPAS)

        # Os outros dois selects opcionais tambem mostravam "---------". O rotulo
        # e diferente de proposito: "Nenhum" e estado LEGITIMO da etapa (curso
        # comunitario nao tem etapa), enquanto tipo de publico e formato vazios sao
        # pendencia que o portao cobra. Chamar os tres de "Nenhum" diria que estao
        # resolvidos.
        for campo, choices in (
            ("tipo_publico", TipoPublico.choices),
            ("formato", Formato.choices),
        ):
            self.fields[campo].choices = [("", "A definir")] + list(choices)

    def tipo_publico_em_uso(self):
        """O tipo de publico que a tela tem AGORA, e nao o gravado: a pessoa pode
        ter acabado de trocar o select e ainda nao ter salvo."""
        if self._publico is not None:
            return self._publico
        if self.is_bound:
            return self.data.get("tipo_publico", "")
        return self.instance.tipo_publico if self.instance else ""

    def publico_e_escolar(self):
        return self.tipo_publico_em_uso() == TipoPublico.ESCOLAR

    def clean(self):
        dados = super().clean()
        referencial = dados.get("referencial")
        competencias = dados.get("competencias") or []
        # O select mostra todas as competencias, sem filtro por referencial:
        # filtrar no cliente exigiria campo dependente em JavaScript, e este
        # projeto so aceita JS proprio onde HTMX nao alcanca (o upload em blocos).
        # A regra fica aqui, onde tem mensagem e teste.
        fora = [c for c in competencias if c.referencial_id != getattr(referencial, "pk", None)]
        if fora:
            codigos = ", ".join(c.codigo for c in fora)
            raise ValidationError(
                {"competencias": f"Estas competências não são do referencial escolhido: {codigos}."}
            )
        # Regra separada da de cima de proposito: sao duas (referencial errado,
        # etapa errada), e junta-las num `if` so faria uma delas nunca ser
        # exercitada sozinha. A tela ja filtra, mas um POST forjado nao passa
        # pela tela.
        etapa = etapa_do_referencial(dados.get("etapa_ano"))
        fora_da_etapa = [c for c in competencias if etapa and c.etapa != etapa]
        if fora_da_etapa:
            codigos = ", ".join(c.codigo for c in fora_da_etapa)
            raise ValidationError(
                {"competencias": f"Estas não são da etapa escolhida: {codigos}."}
            )
        return dados
