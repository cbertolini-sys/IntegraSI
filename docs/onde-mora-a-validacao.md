# Onde mora a validação

Este projeto tem quatro lugares legítimos para uma regra de validação viver. Cada um
tem um uso certo; o problema não é usar o mecanismo errado uma vez, é não ter
registrado a escolha em lugar nenhum — foi assim que `referenciais` ficou sem
`save() -> full_clean()` por uma premissa nunca conferida (ver item 2 da revisão de
branch de 2026-08-25). Este documento existe para que o Plano 2, ao acrescentar sete
models, não invente um quinto lugar.

## 1. Validator de campo

Para uma regra sobre **um único campo**, sem depender de outros campos ou de consulta
ao banco. Roda dentro de `clean_fields()`, chamado tanto por `full_clean()` quanto
pelo `ModelForm` via `_clean_fields()`.

Exemplo: `valida_cpf` (`apps/contas/validators.py`), anexado a
`Usuario.cpf = models.CharField(..., validators=[valida_cpf])`. Confere os dois
dígitos verificadores; não sabe nada sobre `papel` nem sobre o resto do usuário.

## 2. `Model.clean()`

Para uma regra que **cruza campos do mesmo objeto**, ou que precisa consultar outras
linhas da mesma tabela. Roda dentro de `full_clean()`, depois de `clean_fields()`.

Exemplos: `Usuario.clean()` (aluno exige matrícula e não pode ter SIAPE, e
vice-versa); `Edicao.clean()` (só uma edição ativa por vez, com mensagem amigável);
`Referencial.clean()` (`max_competencias` não pode ser menor que `min_competencias`).

**`clean()` só é alcançado através de `full_clean()`.** Um model sem
`save() -> full_clean()` deixa `clean()` morto: `Referencial.objects.create(
min_competencias=5, max_competencias=1)` era aceito até o item 2 desta revisão,
porque nada chamava `full_clean()` no caminho de `save()`. **Todo model com um
`clean()` que importa precisa de:**

```python
def save(self, *args, **kwargs):
    if "update_fields" not in kwargs:
        self.full_clean()
    super().save(*args, **kwargs)
```

## 3. `full_clean()` sobrescrito, para normalizar antes de validar

Para **transformar dados antes da validação rodar** — não para adicionar regras.
Roda antes de chamar `super().full_clean()`.

Exemplos: `Usuario.full_clean()` reduz `cpf`/`matricula`/`siape` a dígitos antes de
validar; `Tema.full_clean()` preenche `slug` a partir de `nome` quando vazio.

**Armadilha 1 — a normalização precisa rodar antes de `validate_unique()`, não
depois.** `full_clean()` chama `clean_fields()`, `clean()` e `validate_unique()`
nessa ordem; `validate_unique()` compara o valor **já normalizado** contra o banco.
Se a normalização morasse em `clean()` em vez de na sobrecarga de `full_clean()`,
`"529.982.247-25"` e `"52998224725"` conviveriam como CPFs "diferentes" — a
unicidade não valeria nada. É o que `test_mesmo_cpf_escrito_de_duas_formas_colide`
(`apps/contas/tests/test_models.py`) crava.

## 4. `clean_<campo>()` do form

Para uma regra **de apresentação/entrada**, não de dado — normalizar o que o usuário
digitou antes mesmo de chegar ao model. Roda em `_clean_fields()` do form, antes do
`full_clean()` do model (que o `ModelForm._post_clean()` chama sobre a instância).

Exemplo: `CamposComPontuacaoMixin.clean_cpf/clean_matricula/clean_siape`
(`apps/contas/forms.py`) — o form redeclara esses campos com `max_length` maior que o
do model, porque a validação de tamanho do `CharField` do form roda **antes** da
normalização do model, e um CPF com pontuação (14 caracteres) seria rejeitado por
"máximo 11 caracteres" antes de ter a chance de ser normalizado.

## Armadilha 2 — `full_clean()` em `save()` não pode disparar em `update_fields`

`django.contrib.auth` chama `user.save(update_fields=["last_login"])` a cada login.
Se `save()` sempre chamasse `full_clean()`, toda validação do objeto inteiro (CPF,
regras de papel, quatro `validate_unique()`) rodaria a cada login — e qualquer linha
que já esteja inválida no banco (dado legado, editada direto) ficaria incapaz de
logar, com um `ValidationError` sem tratamento estourando de dentro do signal.

Por isso todo `save()` que chama `full_clean()` neste projeto (`contas`, `edicoes`,
`referenciais`) pula a validação quando `update_fields` está presente:

```python
if "update_fields" not in kwargs:
    self.full_clean()
```

Os serviços do Plano 2 vão usar `save(update_fields=["status"])` pelo mesmo motivo:
uma escrita direcionada num objeto já persistido não é o lugar para revalidar o
objeto inteiro.
