<template>
  <div class="html-viewer-container fit column">
    <div class="col-auto q-pa-sm bg-grey-2 border-bottom row items-center justify-between" v-if="url">
      <div class="text-subtitle2 text-grey-8 ellipsis">{{ title || 'Visualização' }}</div>
      <q-btn icon="open_in_new" flat round dense size="sm" type="a" :href="url" target="_blank" title="Abrir em nova aba" />
    </div>

    <div class="col relative-position">
      <iframe
        v-if="url && srcdocHtml"
        :srcdoc="srcdocHtml"
        style="min-height:90vh;" class="fit"
        frameborder="0"
        title="Visualização do Documento"
      ></iframe>
      <div v-else class="absolute-center text-center text-grey-5">
        <q-icon name="description" size="4rem" />
        <div class="text-h6 q-mt-sm">Selecione uma variante para visualizar</div>
      </div>
    </div>

    <!-- Dialogo de edição humana por nó -->
    <q-dialog v-model="dialogNode" persistent maximized>
      <q-card class="column fit">
        <q-card-section class="row items-center bg-primary text-white">
          <div class="text-h6">Nó #{{ nodeData?.id }} (path: {{ nodeData?.node_path }})</div>
          <q-space />
          <q-btn dense flat round icon="close" @click="fecharDialog" />
        </q-card-section>
        <q-card-section class="scroll">
          <div v-if="carregandoNode" class="text-center q-pa-md">
            <q-spinner color="primary" size="2em" />
          </div>
          <div v-else-if="nodeData">
            <q-expansion-item icon="visibility" label="Texto Original" caption="Somente leitura" default-opened>
              <q-card flat bordered>
                <q-card-section>
                  <div class="original-box">{{ nodeData.original_text }}</div>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <q-expansion-item icon="compare" label="Baseline vs Adapted" caption="Referência lado a lado">
              <q-card flat bordered>
                <q-card-section>
                  <div class="row q-col-gutter-sm">
                    <div class="col-6">
                      <div class="text-caption text-grey-8">Baseline</div>
                      <q-input dense readonly type="textarea" v-model="nodeData.baseline_text" autogrow />
                    </div>
                    <div class="col-6">
                      <div class="text-caption text-grey-8">Adapted</div>
                      <q-input dense readonly type="textarea" v-model="nodeData.adapted_text" autogrow />
                    </div>
                  </div>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <q-separator class="q-my-md" />
            <div class="row items-center q-mb-sm">
              <div class="text-subtitle2">Texto Humano</div>
              <q-tooltip anchor="top middle" self="bottom middle">Preserve tags e placeholders &lt;ph data-id="PHxxxx"&gt; para não quebrar reconstrução.</q-tooltip>
              <q-btn dense flat round icon="help_outline" class="q-ml-sm" />
            </div>
            <q-input ref="inputHumano" type="textarea" autogrow v-model="textoHumano" :readonly="salvando" :loading="salvando" placeholder="Edite o texto aqui (preferência à versão adapted)" />
            <div class="text-caption text-grey-7 q-mt-xs">
              Dica: mantenha estrutura e marcadores; ajuste somente conteúdo lexical.
            </div>
            <div class="q-mt-md text-right">
              <q-btn color="primary" label="Salvar" :loading="salvando" @click="salvarHumano" />
            </div>
          </div>
          <div v-else class="text-negative">Falha ao carregar nó.</div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useDocumentsStore } from 'src/stores/documents-store'

const props = defineProps({
  url: { type: String, default: null },
  title: { type: String, default: '' }
})

const documentsStore = useDocumentsStore()
const dialogNode = ref(false)
const nodeData = ref(null)
const carregandoNode = ref(false)
const salvando = ref(false)
const textoHumano = ref('')
const iframeEl = ref(null)
const srcdocHtml = ref(null)

function fecharDialog() {
  dialogNode.value = false
  nodeData.value = null
  textoHumano.value = ''
}

async function carregarNode(id) {
  carregandoNode.value = true
  try {
    const data = await documentsStore.obterNo(id)
    nodeData.value = data
    textoHumano.value = data.human_text || data.adapted_text || data.baseline_text || ''
  } catch (e) {
    console.warn('Erro carregar nó', e)
  } finally {
    carregandoNode.value = false
  }
}

async function salvarHumano() {
  if (!nodeData.value) return
  salvando.value = true
  try {
    await documentsStore.salvarTextoHumano(nodeData.value.id, textoHumano.value)
    dialogNode.value = false
  } catch (e) {
    console.warn('Erro salvar humano', e)
  } finally {
    salvando.value = false
  }
}

function setupIframeListeners() {
  if (!iframeEl.value) {
    iframeEl.value = document.querySelector('iframe')
  }

  if (!iframeEl.value) {
    console.warn('Iframe não encontrado')
    return
  }

  // Tentativa 1: Quando o iframe carrega
  iframeEl.value.addEventListener('load', () => {
    console.log('Iframe carregado, instalando listeners...')
    installClickHandlers()
  })

  // Tentativa 2: Usar MutationObserver para detectar quando o conteúdo está pronto
  try {
    const iframeDoc = iframeEl.value.contentDocument || iframeEl.value.contentWindow.document
    if (iframeDoc.readyState === 'loading') {
      iframeDoc.addEventListener('DOMContentLoaded', () => {
        installClickHandlers()
      })
    } else {
      installClickHandlers()
    }
  } catch (e) {
    console.warn('Não foi possível acessar o documento do iframe:', e)
    // Fallback: usar postMessage
    setupPostMessageFallback()
  }
}

function installClickHandlers() {
  try {
    const iframeDoc = iframeEl.value.contentDocument || iframeEl.value.contentWindow.document

    iframeDoc.removeEventListener('click', handleIframeClick, true)

    iframeDoc.addEventListener('click', handleIframeClick, true)

    const style = iframeDoc.createElement('style')
    style.textContent = `
      [data-node-database-id] {
        cursor: pointer !important;
        transition: background-color 0.2s ease;
      }
      [data-node-database-id]:hover {
        background-color: rgba(25, 118, 210, 0.1) !important;
        outline: 2px solid rgba(25, 118, 210, 0.3) !important;
      }
    `
    iframeDoc.head.appendChild(style)

    console.log('Click handlers instalados com sucesso no iframe')
  } catch (e) {
    console.warn('Erro ao instalar click handlers:', e)
    setupPostMessageFallback()
  }
}

function handleIframeClick(ev) {
  const target = ev.target
  const clickableElement = target.closest('[data-node-database-id]')

  if (clickableElement) {
    ev.preventDefault()
    ev.stopPropagation()
    ev.stopImmediatePropagation()

    const idStr = clickableElement.getAttribute('data-node-database-id')
    if (!idStr) return

    const id = parseInt(idStr, 10)
    if (!isNaN(id)) {
      console.log('Nó clicado:', id)
      carregarNode(id).then(() => {
        dialogNode.value = true
      })
    }

    return false
  }
}

function setupPostMessageFallback() {
  console.log('Configurando fallback com postMessage')
  window.removeEventListener('message', handlePostMessage)
  window.addEventListener('message', handlePostMessage)
}

function handlePostMessage(ev) {
  if (ev.data && ev.data.type === 'tcc-node-click') {
    const id = ev.data.id
    if (typeof id === 'number') {
      carregarNode(id).then(() => {
        dialogNode.value = true
      })
    }
  }
}

async function carregarHtmlNoIframe() {
  if (!props.url) {
    srcdocHtml.value = null
    return
  }

  try {
    const resp = await fetch(props.url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const html = await resp.text()

    const injectorScript = `
<script>
(function() {
  console.log('Script de clique injetado no iframe');

  function handleClick(ev) {
    try {
      var el = ev.target.closest('[data-node-database-id]');
      if (!el) return;

      var idStr = el.getAttribute('data-node-database-id');
      if (!idStr) return;

      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation();

      var id = parseInt(idStr, 10);
      if (isNaN(id)) return;

      console.log('Enviando postMessage para nó:', id);
      window.parent.postMessage({
        type: 'tcc-node-click',
        id: id
      }, '*');

    } catch (e) {
      console.warn('Erro no handler de clique:', e);
    }
  }

  // Remove listener existente
  document.removeEventListener('click', handleClick, true);
  // Adiciona novo listener
  document.addEventListener('click', handleClick, true);

  // Estilos para feedback
  var style = document.createElement('style');
  style.textContent = \`
    [data-node-database-id] {
      cursor: pointer !important;
      transition: background-color 0.2s ease;
    }
    [data-node-database-id]:hover {
      background-color: rgba(25, 118, 210, 0.1) !important;
      outline: 2px solid rgba(25, 118, 210, 0.3) !important;
    }
  \`;
  document.head.appendChild(style);

})();
<\\/script>
`

    const injectorStyle = `
<style>
  [data-node-database-id] {
    cursor: pointer !important;
  }
  [data-node-database-id]:hover {
    background: rgba(25,118,210,0.08) !important;
  }
</style>
`

    let result = html
    // Insere antes do </body> ou no final
    if (html.includes('</body>')) {
      result = html.replace('</body>', injectorStyle + injectorScript + '</body>')
    } else {
      result = html + injectorStyle + injectorScript
    }

    srcdocHtml.value = result

    // Aguarda o próximo tick e configura os listeners
    await nextTick()
    setTimeout(() => {
      setupIframeListeners()
    }, 100)

  } catch (e) {
    console.error('Falha ao carregar HTML para srcdoc', e)
    srcdocHtml.value = null
  }
}

// Watchers e lifecycle hooks
watch(() => props.url, async (val) => {
  if (!val) {
    srcdocHtml.value = null
    return
  }
  await carregarHtmlNoIframe()
})

onMounted(async () => {
  setupPostMessageFallback() // Sempre configurar postMessage como fallback
  if (props.url) await carregarHtmlNoIframe()
})

onUnmounted(() => {
  window.removeEventListener('message', handlePostMessage)
})
</script>

<style scoped>
.html-viewer-container {
  background: white;
  border-left: 1px solid #e0e0e0;
}
.border-bottom {
  border-bottom: 1px solid #e0e0e0;
}
.original-box {
  font-family: "Courier New", monospace;
  font-size: 13px;
  background: #fafafa;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  white-space: pre-wrap;
}
</style>
