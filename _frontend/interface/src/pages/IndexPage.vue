<template>
  <q-page class="fit">
    <q-splitter
      v-model="splitterModel"
      class="fit"
      :limits="[30, 70]"
    >
     <template v-slot:before>
        <HtmlViewer :url="selectedVariantUrl" :title="selectedVariantTitle" />
      </template>
      <template v-slot:after>
        <div class="q-pa-md scroll fit">

            <q-slide-transition>


           <q-card flat bordered  v-if="selectedVariantUrl" class="q-mb-md">

            <q-banner class="bg-orange-6 text-white rounded-borders ">
              Visualizando tradução
            </q-banner>

            <q-expansion-item v-if="selectedVariantUrl"
              expand-separator
              icon="library_add"
              label="Adicionar Contexto"
              caption="Enriqueça a base de conhecimento para melhorar futuras traduções via RAG."
              :disable="!selecionado"
            >
              <q-card >
                <q-card-section>
                  <div class="text-caption text-grey-8 q-mb-sm">
                    Adicione termos ou trechos para refinar o contexto (RAG).
                  </div>

                  <div class="q-gutter-sm q-mb-md">
                    <div class="row items-center q-gutter-x-lg">
                      <div class="row items-center">
                        <q-radio v-model="contextType" val="glossario" label="Glossário" />
                        <q-btn round flat icon="help" color="primary" size="xs" @click="openHelp('glossario')" class="q-ml-xs">
                          <q-tooltip>O que é o Glossário?</q-tooltip>
                        </q-btn>
                      </div>
                      <div class="row items-center">
                        <q-radio v-model="contextType" val="corpus" label="Corpus" />
                        <q-btn round flat icon="help" color="primary" size="xs" @click="openHelp('corpus')" class="q-ml-xs">
                          <q-tooltip>O que é o Corpus?</q-tooltip>
                        </q-btn>
                      </div>
                    </div>
                  </div>

                  <q-separator class="q-mb-md" />

                  <!-- Formulário Glossário -->
                  <q-form v-if="contextType === 'glossario'" @submit.prevent="handleContextSubmit">
                    <div class="row q-col-gutter-sm">
                      <div class="col-6">
                        <q-input v-model="glossaryForm.term_src" label="Termo Origem" dense outlined :rules="[val => !!val || 'Obrigatório']" />
                      </div>
                      <div class="col-6">
                        <q-input v-model="glossaryForm.lang_src" label="Lang Origem" dense outlined />
                      </div>
                      <div class="col-6">
                        <q-input v-model="glossaryForm.term_tgt" label="Termo Destino" dense outlined :rules="[val => !!val || 'Obrigatório']" />
                      </div>
                      <div class="col-6">
                        <q-input v-model="glossaryForm.lang_tgt" label="Lang Destino" dense outlined />
                      </div>
                      <div class="col-12">
                        <q-input v-model="glossaryForm.notes" label="Notas (opcional)" dense outlined type="textarea" rows="2" />
                      </div>
                    </div>
                    <div class="q-mt-md text-right">
                      <q-btn label="Adicionar ao Glossário" type="submit" color="secondary" :loading="submittingContext" />
                    </div>
                  </q-form>

                  <!-- Formulário Corpus -->
                  <q-form v-if="contextType === 'corpus'" @submit.prevent="handleContextSubmit">
                    <div class="row q-col-gutter-sm">
                      <div class="col-12">
                        <q-input v-model="corpusForm.text" label="Texto / Trecho" dense outlined type="textarea" rows="3" :rules="[val => !!val || 'Obrigatório']" />
                      </div>
                      <div class="col-6">
                        <q-input v-model="corpusForm.language" label="Idioma" dense outlined />
                      </div>
                      <div class="col-6">
                        <q-input v-model="corpusForm.tags" label="Tags (separadas por vírgula)" dense outlined hint="Ex: civil, contrato" />
                      </div>
                      <div class="col-12">
                        <q-input v-model="corpusForm.notes" label="Notas (opcional)" dense outlined type="textarea" rows="2" />
                      </div>
                    </div>
                    <div class="q-mt-md text-right">
                      <q-btn label="Adicionar ao Corpus" type="submit" color="secondary" :loading="submittingContext" />
                    </div>
                  </q-form>

                </q-card-section>
              </q-card>
            </q-expansion-item>
           </q-card>
           </q-slide-transition>


          <q-list bordered class="rounded-borders">

            <!-- Seção 1: Documentos -->
            <q-expansion-item
              expand-separator
              icon="description"
              label="Documentos disponíveis"
              caption="Selecione ou envie um HTML para processar"
              default-opened
            >
              <q-card>
                <q-card-section>
                  <div class="row q-col-gutter-md">
                    <div class="col-12">
                      <q-select
                        v-model="selecionado"
                        :options="documentos"
                        label="Documento Selecionado"
                        dense
                        emit-value
                        map-options
                        option-label="label"
                        option-value="value"
                        :loading="carregando"
                        clearable
                        @update:model-value="carregarVariantes"
                      />
                    </div>
                    <div class="col-12">
                      <q-file
                        v-model="arquivo"
                        label="Enviar novo HTML"
                        accept=".html,text/html"
                        dense
                        filled
                        clearable
                      >
                        <template #prepend>
                          <q-icon name="upload" />
                        </template>
                      </q-file>
                      <div class="q-mt-sm text-right">
                        <q-btn
                          label="Enviar"
                          color="primary"
                          flat
                          size="sm"
                          @click="handleUpload"
                          :disable="!arquivo"
                        />
                      </div>
                    </div>
                  </div>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <!-- Seção 2: Processamento -->
            <q-expansion-item
              expand-separator
              icon="settings"
              label="Processar tradução"
              caption="Escolha backend, modo e parâmetros de RAG"
              default-opened
            >
              <q-card>
                <q-card-section>
                  <q-form @submit.prevent="handleProcess">
                    <div class="row q-col-gutter-sm">
                      <div class="col-6">
                        <q-select v-model="backend" :options="backends" label="Backend" dense />
                      </div>
                      <div class="col-6">
                        <q-select v-model="modo" :options="modos" label="Modo" dense />
                      </div>
                      <div class="col-6">
                        <q-input v-model="idioma" label="Idioma destino" dense />
                      </div>
                      <div class="col-6">
                        <q-input v-model.number="ragTopk" type="number" label="RAG Top K" dense />
                      </div>
                    </div>
                    <div class="q-mt-md">
                      <q-btn
                        label="Processar"
                        color="primary"
                        type="submit"
                        class="full-width"
                        :disable="!selecionado"
                        :loading="processando"
                      />
                    </div>
                  </q-form>
                </q-card-section>
                <q-card-section v-if="processamento">
                  <q-banner dense class="bg-green-1 text-green-10 rounded-borders">
                    Tradução concluída: {{ processamento.documento }} ({{ processamento.idioma }})
                  </q-banner>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <!-- Seção 3: Variantes -->
            <q-expansion-item
              expand-separator
              icon="view_list"
              label="Variantes disponíveis"
              caption="Clique na linha para visualizar"
              default-opened
            >
              <q-card>
                <q-card-section class="q-pa-none">
                  <div class="q-pa-sm text-right">
                    <q-btn label="Atualizar" icon="refresh" flat size="sm" @click="carregarVariantes" :disable="!selecionado" />
                  </div>
                  <q-table
                    v-if="variantes.length"
                    :rows="variantes"
                    :columns="colunasVariantes"
                    row-key="filename"
                    flat
                    dense
                    class="cursor-pointer"
                    :pagination="{ rowsPerPage: 0 }"
                    hide-bottom
                    @row-click="onRowClick"
                  >
                    <template v-slot:body-cell-variante="props">
                      <q-td :props="props">
                        <q-badge :color="props.value === 'baseline' ? 'grey-7' : 'primary'">
                          {{ props.value }}
                        </q-badge>
                      </q-td>
                    </template>
                  </q-table>
                  <div v-else class="q-pa-md text-caption text-grey text-center">Nenhuma variante encontrada.</div>
                </q-card-section>
              </q-card>
            </q-expansion-item>


          </q-list>
        </div>
      </template>
    </q-splitter>

    <!-- Dialogo de Ajuda RAG -->
    <q-dialog v-model="showHelp">
      <q-card style="max-width: 800px; width: 100%; height: 80vh;">

        <!-- Conteúdo do Glossário -->
        <div v-if="helpType === 'glossario'" class="fit display-flex column">
          <q-card-section>
            <div class="text-h6 text-primary">Glossário: Precisão Terminológica e Desambiguação</div>
          </q-card-section>

          <q-card-section class="q-pt-none scroll col">
            <div class="text-body1 q-mb-md">
              O <strong>Glossário</strong> é o componente de controle terminológico do sistema RAG. Ele atua como uma "lei" para o modelo de tradução, definindo traduções obrigatórias para termos específicos.
            </div>

            <q-separator class="q-my-md" />

            <div class="text-h6 q-mb-sm text-grey-9">1. O Problema da Consistência</div>
            <p class="text-justify">
              Em traduções jurídicas longas, modelos de IA tendem a variar a tradução de um mesmo termo (ex: traduzir "Contratada" ora como <em>Contractor</em>, ora como <em>Hired Party</em>). O Glossário elimina essa variação, forçando o modelo a usar sempre o termo definido, garantindo a integridade do documento.
            </p>

            <div class="text-h6 q-mb-sm text-grey-9">2. Desambiguação Semântica (Polissemia)</div>
            <p class="text-justify">
              Uma das maiores dificuldades na tradução é a <strong>polissemia</strong>: quando uma palavra tem múltiplos significados dependendo do contexto. O sistema utiliza <strong>Notas de Contexto</strong> para resolver isso.
            </p>
            <p class="text-justify">
              Ao contrário de um simples "Localizar e Substituir", o modelo lê a nota associada a cada entrada do glossário e analisa a frase original para decidir qual tradução se encaixa melhor.
            </p>

            <div class="q-pa-md bg-grey-2 rounded-borders q-mb-md">
              <div class="text-subtitle2 q-mb-xs">Exemplo Prático: A palavra "Trecho"</div>
              <p>No banco de dados, existem múltiplas entradas para "trecho":</p>

              <q-list bordered separator dense class="bg-white rounded-borders">
                <q-item>
                  <q-item-section>
                    <q-item-label class="text-weight-bold">Opção A: "trecho"</q-item-label>
                    <q-item-label caption>Tradução: <em>excerpt</em></q-item-label>
                    <q-item-label caption class="text-primary">Nota: Usar quando designa parte específica de um documento jurídico (citação).</q-item-label>
                  </q-item-section>
                </q-item>
                <q-item>
                  <q-item-section>
                    <q-item-label class="text-weight-bold">Opção B: "trecho"</q-item-label>
                    <q-item-label caption>Tradução: <em>stretch</em></q-item-label>
                    <q-item-label caption class="text-primary">Nota: Usar quando indica segmento de rodovia ou ferrovia (infraestrutura).</q-item-label>
                  </q-item-section>
                </q-item>
              </q-list>

              <div class="q-mt-sm text-caption text-grey-9">
                <strong>Como a IA decide?</strong><br>
                Se a frase for: <em>"Conforme o trecho da Lei 8.666..."</em> &rarr; A IA lê a nota "documento jurídico" e escolhe <strong>excerpt</strong>.<br>
                Se a frase for: <em>"O acidente ocorreu no trecho da BR-101..."</em> &rarr; A IA lê a nota "rodovia" e escolhe <strong>stretch</strong>.
              </div>
            </div>

            <div class="text-h6 q-mb-sm text-grey-9">3. Prioridade sobre o Modelo</div>
            <p class="text-justify">
              As instruções do Glossário têm peso maior que o conhecimento pré-treinado do modelo. Mesmo que o Google Gemini prefira traduzir "Juiz de Direito" como <em>Law Judge</em>, se o glossário mandar usar <em>State Judge</em>, o sistema obedecerá.
            </p>
          </q-card-section>
        </div>

        <!-- Conteúdo do Corpus -->
        <div v-if="helpType === 'corpus'" class="fit display-flex column">
          <q-card-section>
            <div class="text-h6 text-secondary">Corpus: Memória de Tradução e Estilo Jurídico</div>
          </q-card-section>

          <q-card-section class="q-pt-none scroll col">
            <div class="text-body1 q-mb-md">
              O <strong>Corpus</strong> é o coração do sistema RAG (Retrieval-Augmented Generation). Ele atua como uma biblioteca dinâmica de experiências passadas, permitindo que a IA consulte como problemas de tradução similares foram resolvidos anteriormente por humanos especialistas.
            </div>

            <q-separator class="q-my-md" />

            <div class="text-h6 q-mb-sm text-grey-9">1. Busca Semântica (Embeddings)</div>
            <p class="text-justify">
              Diferente de uma busca tradicional (Ctrl+F) que procura palavras exatas, o Corpus utiliza <strong>Embeddings Vetoriais</strong>. O sistema converte o significado das frases em vetores matemáticos multidimensionais.
            </p>
            <p class="text-justify">
              Isso significa que se você enviar a frase <em>"O réu foi absolvido"</em>, o sistema pode encontrar no Corpus a frase <em>"O acusado foi inocentado"</em>, pois elas possuem representações matemáticas próximas, mesmo sem compartilhar as mesmas palavras. Isso garante que o contexto jurídico seja preservado mesmo com variações de vocabulário.
            </p>

            <div class="text-h6 q-mb-sm text-grey-9">2. Aprendizado "Few-Shot" (Exemplos)</div>
            <p class="text-justify">
              Grandes Modelos de Linguagem (LLMs) aprendem muito bem com exemplos. Ao recuperar 3 ou 5 pares de tradução do Corpus e apresentá-los ao modelo antes dele traduzir a nova frase, estamos aplicando uma técnica chamada <strong>Few-Shot Learning</strong>.
            </p>
            <p class="text-justify">
              Basicamente, dizemos à IA: <em>"Aqui estão 3 exemplos de como traduzimos contratos neste escritório. Agora, traduza esta nova frase seguindo este mesmo padrão."</em> Isso ajusta o comportamento do modelo sem a necessidade de um retreino custoso (Fine-Tuning).
            </p>

            <div class="text-h6 q-mb-sm text-grey-9">3. Transferência de Estilo e "Legalese"</div>
            <div class="q-pa-md bg-grey-2 rounded-borders q-mb-md">
              <div class="text-subtitle2 q-mb-xs">Exemplo Prático: Cláusulas Padrão (Boilerplate)</div>
              <q-card flat bordered class="bg-white q-pa-sm q-mb-sm">
                <div class="text-caption text-grey-7">Frase Nova (Input):</div>
                <div class="q-mb-sm">"As partes elegem o foro da Comarca de São Paulo."</div>

                <q-separator class="q-my-xs" />

                <div class="text-caption text-secondary">Exemplo Recuperado do Corpus:</div>
                <div class="text-italic">"Fica eleito o foro da cidade do Rio de Janeiro para dirimir..."</div>
                <div class="text-weight-bold text-green-9">Tradução de Ref: "The courts of the city of Rio de Janeiro are elected to settle..."</div>
              </q-card>
              <div class="text-caption text-grey-9">
                A IA percebe que a estrutura passiva <em>"The courts... are elected"</em> é preferível à tradução literal <em>"The parties elect the forum"</em>. Ela copia a estrutura sintática do exemplo, alterando apenas as entidades (cidades), mantendo a formalidade jurídica.
              </div>
            </div>

            <div class="text-h6 q-mb-sm text-grey-9">4. A Importância das Tags (Filtragem)</div>
            <p class="text-justify">
              O Direito é vasto e terminologias mudam drasticamente entre áreas. As <strong>Tags</strong> funcionam como barreiras de proteção para o contexto.
            </p>
            <ul class="q-pl-md">
              <li><strong>Civil/Contratos:</strong> "Execução" refere-se geralmente à cobrança de dívidas ou cumprimento de obrigações (<em>Enforcement</em>).</li>
              <li><strong>Penal:</strong> "Execução" pode referir-se ao cumprimento de pena (<em>Execution of sentence</em>).</li>
            </ul>
            <p class="text-justify">
              Ao filtrar o Corpus por tags, impedimos que a IA use um exemplo de Direito Penal para traduzir um Contrato de Aluguel, evitando erros graves de interpretação semântica.
            </p>
          </q-card-section>
        </div>        <q-card-actions align="right">
          <q-btn flat label="Fechar" color="primary" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>  </q-page>
</template>

<script setup>
import { onMounted, ref, computed, watch } from 'vue'
import { useDocumentsStore } from 'src/stores/documents-store'
import { useQuasar } from 'quasar'
import HtmlViewer from 'src/components/HtmlViewer.vue'

const $q = useQuasar()
const documentsStore = useDocumentsStore()
const splitterModel = ref(40)

const arquivo = ref(null)
const selecionado = ref(null)
const backend = ref('google')
const backends = ['google', 'hf']
const modo = ref('doc')

const modos = computed(() => {
  if (backend.value === 'google') {
    return ['doc', 'doc-sintatico']
  } else {
    return ['window', 'node']
  }
})

watch(backend, (newVal) => {
  if (newVal === 'google') {
    modo.value = 'doc'
  } else {
    modo.value = 'window'
  }
})

const idioma = ref('en')
const ragTopk = ref(3)

const selectedVariantUrl = ref(null)
const selectedVariantTitle = ref('')

// Help Dialog State
const showHelp = ref(false)
const helpType = ref('glossario')

function openHelp(type) {
  helpType.value = type
  showHelp.value = true
}

// Context Form State
const contextType = ref('glossario')
const submittingContext = ref(false)
const glossaryForm = ref({
  term_src: '',
  lang_src: 'pt',
  term_tgt: '',
  lang_tgt: 'en',
  notes: ''
})
const corpusForm = ref({
  text: '',
  language: 'pt',
  tags: '',
  notes: ''
})

const documentos = computed(() =>
  documentsStore.documentos.map((nome) => ({ label: nome, value: nome }))
)
const carregando = computed(() => documentsStore.carregando)
const processamento = computed(() => documentsStore.processamento)
const processando = ref(false)
const variantes = computed(() => documentsStore.variantes)

const colunasVariantes = [
  { name: 'variante', label: 'Variante', field: 'variante', align: 'left' },
  { name: 'idioma', label: 'Lang', field: 'idioma', align: 'left' },
  { name: 'updated', label: 'Data', field: 'updated_at', align: 'right', format: (val) => new Date(val).toLocaleTimeString() }
]

async function carregarDocumentos() {
  await documentsStore.listarDocumentos()
  if (!selecionado.value && documentsStore.documentos.length) {
    selecionado.value = documentsStore.documentos[0]
  }
}

async function handleUpload() {
  if (!arquivo.value) return
  await documentsStore.uploadDocumento(arquivo.value)
  arquivo.value = null
  await carregarDocumentos()
}

async function handleProcess() {
  if (!selecionado.value) return
  processando.value = true
  try {
    await documentsStore.processarDocumento({
      input: `arquivos_juridicos/${selecionado.value}`,
      language: idioma.value,
      backend: backend.value,
      mode: modo.value,
      rag_topk: ragTopk.value,
    })
    await carregarVariantes()
    $q.notify({ type: 'positive', message: 'Processamento concluído!' })
  } catch (e) {
    $q.notify({ type: 'negative', message: 'Erro ao processar: ' + e.message })
  } finally {
    processando.value = false
  }
}

async function carregarVariantes() {
  if (!selecionado.value) return
  // limpar variantes selecionadas
  selectedVariantUrl.value = null
  await documentsStore.listarVariantes(selecionado.value, idioma.value)
}

function onRowClick(evt, row) {
  const baseUrl = 'http://localhost:8000'
  selectedVariantUrl.value = `${baseUrl}/resultados/html/${row.filename}`
  selectedVariantTitle.value = `${row.filename} (${row.variante})`
}

async function handleContextSubmit() {
  submittingContext.value = true
  try {
    if (contextType.value === 'glossario') {
      await documentsStore.adicionarGlossario({
        ...glossaryForm.value
      })
      $q.notify({ type: 'positive', message: 'Entrada adicionada ao Glossário!' })
      // Reset form
      glossaryForm.value.term_src = ''
      glossaryForm.value.term_tgt = ''
      glossaryForm.value.notes = ''
    } else {
      // Parse tags
      const tagsList = corpusForm.value.tags
        ? corpusForm.value.tags.split(',').map(t => t.trim()).filter(t => t)
        : []

      await documentsStore.adicionarCorpus({
        text: corpusForm.value.text,
        language: corpusForm.value.language,
        tags: tagsList,
        notes: corpusForm.value.notes
      })
      $q.notify({ type: 'positive', message: 'Trecho adicionado ao Corpus!' })
      // Reset form
      corpusForm.value.text = ''
      corpusForm.value.tags = ''
      corpusForm.value.notes = ''
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: 'Erro ao adicionar contexto: ' + e.message })
  } finally {
    submittingContext.value = false
  }
}

onMounted(async () => {
  await carregarDocumentos()
  if (selecionado.value) {
    await carregarVariantes()
  }
})
</script>
