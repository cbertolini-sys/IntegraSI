from django import forms

from apps.cursos.arquivos import valida_upload
from apps.cursos.models import Anexo, Secao


class SecaoForm(forms.ModelForm):
    class Meta:
        model = Secao
        fields = ["conteudo"]
        widgets = {"conteudo": forms.Textarea(attrs={"rows": 12})}


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
