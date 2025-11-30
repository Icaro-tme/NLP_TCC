<template>
  <q-page class="fit">
    <q-splitter v-model="splitterModel" class="fit"  :limits="[30, 70]">
      <template v-slot:before>
        <HtmlViewer :url="selectedVariantUrl" :title="selectedVariantTitle" />
      </template>
      <template v-slot:separator>
        <q-avatar color="primary" text-color="white" size="sm" outlined icon="drag_indicator" />
      </template>
      <template v-slot:after>
        <div class="q-pa-md scroll full-width " style="height:100vh">

          <q-slide-transition>
            <q-card flat bordered v-if="selectedVariantUrl" class="q-mb-md">

              <q-banner class="bg-orange-6 text-white rounded-borders ">
                Visualizando tradução
              </q-banner>

              <q-expansion-item v-if="selectedVariantUrl" expand-separator icon="library_add" label="Adicionar Contexto"
                caption="Enriqueça a base de conhecimento para melhorar futuras traduções via RAG."
                :disable="!selecionado">
                <q-card>
                  <q-card-section>
                    <div class="text-caption text-grey-8 q-mb-sm">
                      Adicione termos ou trechos para refinar o contexto (RAG).
                    </div>

                    <div class="q-gutter-sm q-mb-md">
                      <div class="row items-center q-gutter-x-lg">
                        <div class="row items-center">
                          <q-radio v-model="contextType" val="glossario" label="Glossário" />
                          <q-btn round flat icon="help" color="primary" size="xs" @click="openHelp('glossario')"
                            class="q-ml-xs">
                            <q-tooltip>O que é o Glossário?</q-tooltip>
                          </q-btn>
                        </div>
                        <div class="row items-center">
                          <q-radio v-model="contextType" val="corpus" label="Corpus" />
                          <q-btn round flat icon="help" color="primary" size="xs" @click="openHelp('corpus')"
                            class="q-ml-xs">
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
                          <q-input v-model="glossaryForm.term_src" label="Termo Origem" dense outlined
                            :rules="[val => !!val || 'Obrigatório']" />
                        </div>
                        <div class="col-6">
                          <q-input v-model="glossaryForm.lang_src" label="Lang Origem" dense outlined />
                        </div>
                        <div class="col-6">
                          <q-input v-model="glossaryForm.term_tgt" label="Termo Destino" dense outlined
                            :rules="[val => !!val || 'Obrigatório']" />
                        </div>
                        <div class="col-6">
                          <q-input v-model="glossaryForm.lang_tgt" label="Lang Destino" dense outlined />
                        </div>
                        <div class="col-12">
                          <q-input v-model="glossaryForm.notes" label="Notas (opcional)" dense outlined type="textarea"
                            rows="2" />
                        </div>
                      </div>
                      <div class="q-mt-md text-right">
                        <q-btn label="Adicionar ao Glossário" type="submit" color="secondary"
                          :loading="submittingContext" />
                      </div>
                    </q-form>

                    <!-- Formulário Corpus -->
                    <q-form v-if="contextType === 'corpus'" @submit.prevent="handleContextSubmit">
                      <div class="row q-col-gutter-sm">
                        <div class="col-12">
                          <q-input v-model="corpusForm.text" label="Texto / Trecho" dense outlined type="textarea"
                            rows="3" :rules="[val => !!val || 'Obrigatório']" />
                        </div>
                        <div class="col-6">
                          <q-input v-model="corpusForm.language" label="Idioma" dense outlined />
                        </div>
                        <div class="col-6">
                          <q-input v-model="corpusForm.tags" label="Tags (separadas por vírgula)" dense outlined
                            hint="Ex: civil, contrato" />
                        </div>
                        <div class="col-12">
                          <q-input v-model="corpusForm.notes" label="Notas (opcional)" dense outlined type="textarea"
                            rows="2" />
                        </div>
                      </div>
                      <div class="q-mt-md text-right">
                        <q-btn label="Adicionar ao Corpus" type="submit" color="secondary"
                          :loading="submittingContext" />
                      </div>
                    </q-form>

                  </q-card-section>
                </q-card>
              </q-expansion-item>
            </q-card>
          </q-slide-transition>


          <q-list bordered class="rounded-borders">

            <!-- Seção 1: Documentos -->
            <q-expansion-item expand-separator icon="description" label="Documentos disponíveis"
              caption="Selecione ou envie um HTML para processar" default-opened>
              <q-card>
                <q-card-section>
                  <div class="row q-col-gutter-md">
                    <div class="col-12">
                      <q-select v-model="selecionado" :options="documentos" label="Documento Selecionado" dense
                        emit-value map-options option-label="label" option-value="value" :loading="carregando" clearable
                        @update:model-value="carregarVariantes" />
                    </div>
                    <div class="col-12">
                      <q-file v-model="arquivo" label="Enviar novo HTML" accept=".html,text/html" dense filled
                        clearable>
                        <template #prepend>
                          <q-icon name="upload" />
                        </template>
                      </q-file>
                      <div class="q-mt-sm text-right">
                        <q-btn label="Enviar" color="primary" flat size="sm" @click="handleUpload"
                          :disable="!arquivo" />
                      </div>
                    </div>
                  </div>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <!-- Seção 2: Processamento -->
            <q-expansion-item expand-separator icon="settings" label="Processar tradução"
              caption="Escolha modo e parâmetros de RAG" default-opened>
              <q-card>
                <q-card-section>
                  <q-form @submit.prevent="handleProcess">
                    <div class="row q-col-gutter-sm">
                      <div class="col-12">
                        <q-select v-model="modo" :options="modos" label="Modo" dense />
                      </div>
                      <div v-if="modo === 'window'" class="col-12">
                        <q-input v-model.number="windowSize" type="number" label="Tamanho da Janela" dense />
                      </div>
                      <div class="col-6">
                        <q-input v-model="idioma" label="Idioma destino" dense />
                      </div>
                      <div class="col-6">
                        <q-input v-model.number="ragTopk" type="number" label="RAG Top K" dense />
                      </div>
                    </div>
                    <div class="q-mt-md">
                      <q-btn label="Processar" color="primary" type="submit" class="full-width" :disable="!selecionado"
                        :loading="processando" />
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
            <q-expansion-item expand-separator icon="view_list" label="Variantes disponíveis"
              caption="Clique na linha para visualizar" default-opened>
              <q-card>
                <q-card-section class="q-pa-none">
                  <div class="q-pa-sm text-right">
                    <q-btn label="Atualizar" icon="refresh" flat size="sm" @click="carregarVariantes"
                      :disable="!selecionado" />
                  </div>
                  <q-table v-if="variantes.length" :rows="variantes" :columns="colunasVariantes" row-key="filename" flat
                    dense class="cursor-pointer" :pagination="{ rowsPerPage: 0 }" hide-bottom @row-click="onRowClick">
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

            <!-- Seção 4: Avaliação de Tradução Humana -->
            <q-expansion-item expand-separator icon="rule" label="Avaliação de Tradução Humana"
              caption="Comparar variante baseline/adapted com HTML humano">
              <q-card>
                <q-card-section>
                  <div class="row q-col-gutter-sm">
                    <div class="col-6">
                      <q-file v-model="arquivoHumano" label="HTML Humano" dense filled accept=".html,text/html" />
                    </div>
                    <div class="col-3">
                      <q-select v-model="varianteComparar" :options="['baseline', 'adapted']" label="Variante" dense />
                    </div>
                    <div class="col-3 flex items-end">
                      <q-btn :loading="avaliando" color="primary" label="Avaliar" @click="handleAvaliar"
                        class="full-width" />
                    </div>
                  </div>
                </q-card-section>
                <q-separator />
                <!-- Removido modo nó-a-nó: avaliação apenas por documento -->
                <q-card-section v-if="resultadoAvaliacao">
                  <div class="text-subtitle2 q-mb-sm">Resumo (Documento)</div>
                  <q-list dense bordered class="rounded-borders q-mb-md">
                    <q-item v-for="r in [
                      { k: 'BLEU', v: resultadoAvaliacao.bleu },
                      { k: 'chrF', v: resultadoAvaliacao.chrf },
                      { k: 'TER', v: resultadoAvaliacao.ter },
                      { k: 'Jaccard', v: resultadoAvaliacao.jaccard_medio },
                      { k: 'POS Acc', v: resultadoAvaliacao.pos_accuracy_media }
                    ]" :key="r.k">
                      <q-item-section>{{ r.k }}</q-item-section>
                      <q-item-section side>
                        <q-badge :color="metricColor(r.k, r.v)">{{ r.v !== null ? r.v.toFixed(3) : '—' }}</q-badge>
                      </q-item-section>
                    </q-item>
                  </q-list>
                  <div class="row q-col-gutter-sm">
                    <div class="col-6">
                      <div class="text-caption text-grey-8 q-mb-xs">Humano</div>
                      <div class="doc-pane bg-grey-1 q-pa-sm"
                        v-html="renderDiff(resultadoAvaliacao.texto_humano, resultadoAvaliacao.texto_sistema, 'human')">
                      </div>
                    </div>
                    <div class="col-6">
                      <div class="text-caption text-grey-8 q-mb-xs">Sistema ({{ varianteComparar }})</div>
                      <div class="doc-pane bg-grey-1 q-pa-sm"
                        v-html="renderDiff(resultadoAvaliacao.texto_sistema, resultadoAvaliacao.texto_humano, 'system')">
                      </div>
                    </div>
                  </div>
                  <div class="text-caption text-grey-8 q-mt-sm">Sintaxe habilitada: {{
                    resultadoAvaliacao.sintaxe_habilitada ? 'sim'
                    : 'não (modelo spaCy ausente)' }}</div>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <q-card flat bordered class="q-mb-md">
              <q-card-section>
                <div class="row items-center">
                  <div class="col">
                    <div class="text-subtitle2">Logs em Tempo Real</div>
                    <div class="text-caption text-grey-8">{{ eventos.length }} eventos capturados</div>
                  </div>
                  <div class="col-auto">
                    <q-btn label="Ver Logs" icon="visibility" color="primary" rounded outline @click="modalLogs = true" />
                  </div>
                </div>
              </q-card-section>
            </q-card>

            <q-dialog v-model="modalLogs" style="max-width: 800px; width: 100%; max-height: 80vh;">
              <q-card  class="q-pa-md rounded-borders">
                <q-card-section class="row items-center q-pb-none">
                  <div class="text-h6">Logs em Tempo Real</div>
                  <q-space />
                  <q-btn icon="close" flat round dense v-close-popup />
                </q-card-section>

                <q-card-section class="scroll">
                  <div v-if="!eventos.length" class="text-center text-grey-6 q-pa-lg">
                    <q-icon name="pending" size="48px" class="q-mb-md" />
                    <div class="text-h6">Aguardando eventos...</div>
                    <div class="text-caption">Os logs aparecerão aqui quando o processamento iniciar</div>
                  </div>

                  <q-list v-else bordered separator class="rounded-borders">
                    <q-expansion-item v-for="(evento, index) in eventos" :key="evento.ts" :default-opened="index === 0"
                      :label="evento.tipo"
                      :caption="`${new Date(evento.ts).toLocaleString()} - ${Object.keys(evento.dado).length} propriedades`">
                      <q-card flat>
                        <q-card-section>
                          <q-input :model-value="JSON.stringify(evento.dado, null, 2)" type="textarea" readonly outlined
                            dense :rows="Math.min(20, JSON.stringify(evento.dado, null, 2).split('\n').length)"
                            class="code-textarea" />
                          <div class="q-mt-sm text-right">
                            <q-btn label="Copiar JSON" icon="content_copy" size="sm" flat
                              @click="copiarJson(evento.dado)" />
                          </div>
                        </q-card-section>
                      </q-card>
                    </q-expansion-item>
                  </q-list>
                </q-card-section>


              </q-card>
            </q-dialog>


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
              O <strong>Glossário</strong> é o componente de controle terminológico do sistema RAG. Ele atua como uma
              "lei"
              para o modelo de tradução, definindo traduções obrigatórias para termos específicos.
            </div>

            <q-separator class="q-my-md" />

            <div class="text-h6 q-mb-sm text-grey-9">1. O Problema da Consistência</div>
            <p class="text-justify">
              Em traduções jurídicas longas, modelos de IA tendem a variar a tradução de um mesmo termo (ex: traduzir
              "Contratada" ora como <em>Contractor</em>, ora como <em>Hired Party</em>). O Glossário elimina essa
              variação,
              forçando o modelo a usar sempre o termo definido, garantindo a integridade do documento.
            </p>

            <div class="text-h6 q-mb-sm text-grey-9">2. Desambiguação Semântica (Polissemia)</div>
            <p class="text-justify">
              Uma das maiores dificuldades na tradução é a <strong>polissemia</strong>: quando uma palavra tem múltiplos
              significados dependendo do contexto. O sistema utiliza <strong>Notas de Contexto</strong> para resolver
              isso.
            </p>
            <p class="text-justify">
              Ao contrário de um simples "Localizar e Substituir", o modelo lê a nota associada a cada entrada do
              glossário
              e analisa a frase original para decidir qual tradução se encaixa melhor.
            </p>

            <div class="q-pa-md bg-grey-2 rounded-borders q-mb-md">
              <div class="text-subtitle2 q-mb-xs">Exemplo Prático: A palavra "Trecho"</div>
              <p>No banco de dados, existem múltiplas entradas para "trecho":</p>

              <q-list bordered separator dense class="bg-white rounded-borders">
                <q-item>
                  <q-item-section>
                    <q-item-label class="text-weight-bold">Opção A: "trecho"</q-item-label>
                    <q-item-label caption>Tradução: <em>excerpt</em></q-item-label>
                    <q-item-label caption class="text-primary">Nota: Usar quando designa parte específica de um
                      documento
                      jurídico (citação).</q-item-label>
                  </q-item-section>
                </q-item>
                <q-item>
                  <q-item-section>
                    <q-item-label class="text-weight-bold">Opção B: "trecho"</q-item-label>
                    <q-item-label caption>Tradução: <em>stretch</em></q-item-label>
                    <q-item-label caption class="text-primary">Nota: Usar quando indica segmento de rodovia ou ferrovia
                      (infraestrutura).</q-item-label>
                  </q-item-section>
                </q-item>
              </q-list>

              <div class="q-mt-sm text-caption text-grey-9">
                <strong>Como a IA decide?</strong><br>
                Se a frase for: <em>"Conforme o trecho da Lei 8.666..."</em> &rarr; A IA lê a nota "documento jurídico"
                e
                escolhe <strong>excerpt</strong>.<br>
                Se a frase for: <em>"O acidente ocorreu no trecho da BR-101..."</em> &rarr; A IA lê a nota "rodovia" e
                escolhe <strong>stretch</strong>.
              </div>
            </div>

            <div class="text-h6 q-mb-sm text-grey-9">3. Prioridade sobre o Modelo</div>
            <p class="text-justify">
              As instruções do Glossário têm peso maior que o conhecimento pré-treinado do modelo. Mesmo que o Google
              Gemini
              prefira traduzir "Juiz de Direito" como <em>Law Judge</em>, se o glossário mandar usar <em>State
                Judge</em>, o
              sistema obedecerá.
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
              O <strong>Corpus</strong> é o coração do sistema RAG (Retrieval-Augmented Generation). Ele atua como uma
              biblioteca dinâmica de experiências passadas, permitindo que a IA consulte como problemas de tradução
              similares foram resolvidos anteriormente por humanos especialistas.
            </div>

            <q-separator class="q-my-md" />

            <div class="text-h6 q-mb-sm text-grey-9">1. Busca Semântica (Embeddings)</div>
            <p class="text-justify">
              Diferente de uma busca tradicional (Ctrl+F) que procura palavras exatas, o Corpus utiliza
              <strong>Embeddings
                Vetoriais</strong>. O sistema converte o significado das frases em vetores matemáticos
              multidimensionais.
            </p>
            <p class="text-justify">
              Isso significa que se você enviar a frase <em>"O réu foi absolvido"</em>, o sistema pode encontrar no
              Corpus a
              frase <em>"O acusado foi inocentado"</em>, pois elas possuem representações matemáticas próximas, mesmo
              sem
              compartilhar as mesmas palavras. Isso garante que o contexto jurídico seja preservado mesmo com variações
              de
              vocabulário.
            </p>

            <div class="text-h6 q-mb-sm text-grey-9">2. Aprendizado "Few-Shot" (Exemplos)</div>
            <p class="text-justify">
              Grandes Modelos de Linguagem (LLMs) aprendem muito bem com exemplos. Ao recuperar 3 ou 5 pares de tradução
              do
              Corpus e apresentá-los ao modelo antes dele traduzir a nova frase, estamos aplicando uma técnica chamada
              <strong>Few-Shot Learning</strong>.
            </p>
            <p class="text-justify">
              Basicamente, dizemos à IA: <em>"Aqui estão 3 exemplos de como traduzimos contratos neste escritório.
                Agora,
                traduza esta nova frase seguindo este mesmo padrão."</em> Isso ajusta o comportamento do modelo sem a
              necessidade de um retreino custoso (Fine-Tuning).
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
                <div class="text-weight-bold text-green-9">Tradução de Ref: "The courts of the city of Rio de Janeiro
                  are
                  elected to settle..."</div>
              </q-card>
              <div class="text-caption text-grey-9">
                A IA percebe que a estrutura passiva <em>"The courts... are elected"</em> é preferível à tradução
                literal
                <em>"The parties elect the forum"</em>. Ela copia a estrutura sintática do exemplo, alterando apenas as
                entidades (cidades), mantendo a formalidade jurídica.
              </div>
            </div>

            <div class="text-h6 q-mb-sm text-grey-9">4. A Importância das Tags (Filtragem)</div>
            <p class="text-justify">
              O Direito é vasto e terminologias mudam drasticamente entre áreas. As <strong>Tags</strong> funcionam como
              barreiras de proteção para o contexto.
            </p>
            <ul class="q-pl-md">
              <li><strong>Civil/Contratos:</strong> "Execução" refere-se geralmente à cobrança de dívidas ou cumprimento
                de
                obrigações (<em>Enforcement</em>).</li>
              <li><strong>Penal:</strong> "Execução" pode referir-se ao cumprimento de pena (<em>Execution of
                  sentence</em>).</li>
            </ul>
            <p class="text-justify">
              Ao filtrar o Corpus por tags, impedimos que a IA use um exemplo de Direito Penal para traduzir um Contrato
              de
              Aluguel, evitando erros graves de interpretação semântica.
            </p>
          </q-card-section>
        </div> <q-card-actions align="right">
          <q-btn flat label="Fechar" color="primary" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog> </q-page>
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
// Backend removido (Google-only)
const modo = ref('doc')
const modos = ['doc', 'node', 'window']

const idioma = ref('en')
const ragTopk = ref(3)

const selectedVariantUrl = ref(null)
const selectedVariantTitle = ref('')

// Help Dialog State
const showHelp = ref(false)
const modalLogs = ref(false)
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
      mode: modo.value,
      rag_topk: ragTopk.value,
      window_size: windowSize.value,
    })
    await carregarVariantes()
    $q.notify({ type: 'positive', message: 'Processamento concluído!' })
  } catch (e) {
    $q.notify({ type: 'negative', message: 'Erro ao processar: ' + (e.message || e) })
  } finally {
    processando.value = false
  }
}
// Window size control for window mode
const windowSize = ref(3)
watch(modo, (m) => {
  if (m !== 'window') return
  if (!Number.isInteger(windowSize.value) || windowSize.value < 1) {
    windowSize.value = 3
  }
})

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
    $q.notify({ type: 'negative', message: 'Erro ao adicionar contexto: ' + (e.message || e) })
  } finally {
    submittingContext.value = false
  }
}

onMounted(async () => {
  iniciarSSE()
  await carregarDocumentos()
  if (selecionado.value) {
    await carregarVariantes()
  }
})

// Fallback de notificação quando Quasar Notify não está habilitado
function notify(opts) {
  if ($q && typeof $q.notify === 'function') {
    $q.notify(opts)
  } else {
    const msg = (opts && opts.message) ? opts.message : String(opts)
    alert(msg)
  }
}

const arquivoHumano = ref(null)
const varianteComparar = ref('adapted')
// Avaliação apenas por documento inteiro
const avaliando = ref(false)
const resultadoAvaliacao = ref(null)

async function handleAvaliar() {
  if (!selecionado.value || !arquivoHumano.value) {
    $q.notify({ type: 'warning', message: 'Selecione documento e arquivo humano.' })
    return
  }
  avaliando.value = true
  try {
    const data = await documentsStore.avaliarTraducao({
      documento: selecionado.value.replace(/\.html$/, '').replace(/InteriorTeor/, 'InteriorTeor'),
      source_lang: 'pt',
      idioma: idioma.value,
      variante: varianteComparar.value,
      file: arquivoHumano.value,
    })
    resultadoAvaliacao.value = data
    $q.notify({ type: 'positive', message: 'Avaliação concluída!' })
  } catch (e) {
    $q.notify({ type: 'negative', message: 'Erro na avaliação: ' + (e.message || e) })
  } finally {
    avaliando.value = false
  }
}

function metricColor(name, value) {
  if (value == null) return 'grey-6'
  // thresholds simples
  if (name === 'BLEU') {
    if (value < 20) return 'red-6'
    if (value < 40) return 'orange-6'
    return 'green-6'
  }
  if (name === 'chrF') {
    if (value < 40) return 'red-6'
    if (value < 60) return 'orange-6'
    return 'green-6'
  }
  if (name === 'TER') {
    if (value > 70) return 'red-6'
    if (value > 50) return 'orange-6'
    return 'green-6'
  }
  if (name === 'Jaccard' || name === 'Jaccard Médio') {
    if (value < 0.3) return 'red-6'
    if (value < 0.6) return 'orange-6'
    return 'green-6'
  }
  if (name === 'POS Acc' || name === 'POS Acc Média') {
    if (value < 0.4) return 'red-6'
    if (value < 0.7) return 'orange-6'
    return 'green-6'
  }
  return 'grey-6'
}

function tokenize(text) {
  return (text || '')
    .split(/(\s+)/)
    .filter(Boolean)
}

function renderDiff(a, b, side) {
  const ta = tokenize(a)
  const tb = tokenize(b)
  // build frequency maps for quick heuristics
  const freqA = {}
  const freqB = {}
  for (const t of ta) freqA[t] = (freqA[t] || 0) + 1
  for (const t of tb) freqB[t] = (freqB[t] || 0) + 1
  const html = ta.map(tok => {
    const isSpace = /\s+/.test(tok)
    if (isSpace) return tok
    const inOther = freqB[tok] > 0
    if (!inOther) {
      // token exclusivo deste lado: marcar em vermelho
      return `<span class="diff-bad">${escapeHtml(tok)}</span>`
    }
    // token comum: neutro
    return escapeHtml(tok)
  }).join('')
  return html
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

// SSE Logs
const eventos = ref([])
let es = null
function iniciarSSE() {
  try {
    es = new EventSource('http://localhost:8000/processar/eventos')
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data)
        eventos.value.unshift({ tipo: payload.event_type, dado: payload, ts: Date.now() })
        if (eventos.value.length > 200) eventos.value.pop()
      } catch (_) { }
    }
    es.onerror = () => { console.warn('SSE erro') }
  } catch (err) {
    console.error('Falha ao iniciar SSE', err)
  }
}
</script>

<style scoped>
.doc-pane {
  min-height: 200px;
  white-space: pre-wrap;
  line-height: 1.6;
}

.diff-bad {
  background-color: #fdecea;
  color: #c62828;
  padding: 0 2px;
  border-radius: 2px;
}
</style>
