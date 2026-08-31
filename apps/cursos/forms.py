from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance

from apps.cursos.arquivos import valida_upload
from apps.cursos.choices import PALAVRAS_CHAVE_EXIGIDAS, TipoPublico
from apps.cursos.models import Anexo, Curso, Secao
from apps.referenciais.choices import etapa_do_referencial
from apps.referenciais.models import Referencial


class SecaoForm(forms.ModelForm):
    class Meta:
        model = Secao
        fields = ["conteudo"]


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


class AnexoForm(forms.ModelForm):
    upload = forms.FileField(label="arquivo", required=False)
    # Declarado explicitamente (em vez de deixar o ModelForm derivar de Anexo.url)
    # so para fixar assume_scheme="https": sem isso o Django 5.2 emite
    # RemovedInDjango60Warning a cada requisicao, porque o padrao de esquema muda
    # de http para https na proxima versao maior. Continua opcional, como o campo
    # do modelo (Anexo.url tem blank=True).
    url = forms.URLField(label="link", required=False, assume_scheme="https")

    class Meta:
        model = Anexo
        fields = ["titulo", "descricao", "referencia_bibliografica", "rotulo", "tipo_pratica", "url"]

    def clean(self):
        dados = super().clean()
        upload = dados.get("upload")
        if upload:
            cabecalho = upload.read(16)
            upload.seek(0)
            dados["mime"] = valida_upload(upload.name, upload.size, cabecalho)
        elif not dados.get("url"):
            raise forms.ValidationError("Envie um arquivo ou informe um link.")
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
        widgets = {"resumo": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O vazio que o Django gera e "---------", que nao diz nada. Curso sem
        # referencial e de primeira classe (spec 4.2), entao a opcao se chama pelo
        # nome; senao parece campo que a pessoa esqueceu de preencher.
        #
        # Aqui, e nao redeclarando o campo: assim o queryset continua vindo da FK,
        # e um referencial desativado que ja esteja gravado nao some do select
        # (sumir o descartaria em silencio no proximo salvamento).
        self.fields["referencial"].empty_label = "Nenhum"
        self.fields["referencial"].queryset = Referencial.objects.para_publico_escolar(
            self.publico_e_escolar()
        )

    def publico_e_escolar(self):
        """O tipo de publico que a tela tem AGORA, e nao o gravado: a pessoa pode
        ter acabado de trocar o select e ainda nao ter salvo."""
        if self.is_bound:
            tipo = self.data.get("tipo_publico", "")
        else:
            tipo = self.instance.tipo_publico if self.instance else ""
        return tipo == TipoPublico.ESCOLAR

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
