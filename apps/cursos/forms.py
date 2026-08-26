from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance

from apps.cursos.arquivos import valida_upload
from apps.cursos.models import Anexo, Curso, Secao


class SecaoForm(forms.ModelForm):
    class Meta:
        model = Secao
        fields = ["conteudo"]


class CursoForm(forms.ModelForm):
    class Meta:
        model = Curso
        fields = [
            "titulo", "resumo", "edicao", "tipo_publico", "etapa_ano", "publico_descricao",
            "referencial", "carga_horaria", "formato", "pre_requisitos", "temas", "palavras_chave",
        ]
        widgets = {"resumo": forms.Textarea(attrs={"rows": 4})}


class AnexoForm(forms.ModelForm):
    upload = forms.FileField(label="arquivo", required=False)

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
