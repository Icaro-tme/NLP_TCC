import { defineStore, acceptHMRUpdate } from 'pinia'
import { api } from 'boot/axios'

function normalizeError(err) {
  if (err?.response?.data?.detail) {
    return Array.isArray(err.response.data.detail)
      ? err.response.data.detail.map((d) => d.msg || d).join(', ')
      : err.response.data.detail
  }
  return err?.message || 'Erro desconhecido'
}

export const useDocumentsStore = defineStore('documents', {
  state: () => ({
    documentos: [],
    carregando: false,
    erro: null,
    processamento: null,
    variantes: [],
  }),

  actions: {
    async listarDocumentos() {
      this.carregando = true
      this.erro = null
      try {
        const { data } = await api.get('/documentos')
        this.documentos = data
        return data
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      } finally {
        this.carregando = false
      }
    },

    async uploadDocumento(file, nomeAlvo) {
      if (!file) {
        throw new Error('Selecione um arquivo HTML')
      }
      const formData = new FormData()
      formData.append('arquivo', file)
      if (nomeAlvo) {
        formData.append('nome_alvo', nomeAlvo)
      }
      try {
        const { data } = await api.post('/documentos/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        await this.listarDocumentos()
        return data
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      }
    },

    async processarDocumento(payload) {
      this.erro = null
      try {
        const body = {
          input: payload.input,
          language: payload.language || 'en',
          source_lang: payload.source_lang || 'pt',
          mode: payload.mode || 'doc',
          rag_topk: payload.rag_topk ?? 0,
        }
        const { data } = await api.post('/processar', body)
        this.processamento = data
        return data
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      }
    },

    async listarVariantes(documento, idioma) {
      if (!documento) {
        return []
      }
      try {
        const { data } = await api.get(`/documentos/${encodeURIComponent(documento)}/variantes`, {
          params: { idioma: idioma || 'en' },
        })
        this.variantes = data.variantes
        return this.variantes
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      }
    },

    async adicionarGlossario(payload) {
      try {
        const { data } = await api.post('/glossario/entradas', payload)
        return data
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      }
    },

    async adicionarCorpus(payload) {
      try {
        const { data } = await api.post('/corpus/trechos', payload)
        return data
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      }
    },

    async avaliarTraducao(payload) {
      // payload: { documento, source_lang, idioma, variante, file }
      if (!payload?.file) {
        throw new Error('Arquivo humano é obrigatório')
      }
      const form = new FormData()
      form.append('documento', payload.documento)
      form.append('source_lang', payload.source_lang || 'pt')
      form.append('idioma', payload.idioma || 'en')
      form.append('variante', payload.variante || 'adapted')
      form.append('arquivo', payload.file)
      try {
        const { data } = await api.post('/avaliar', form)
        return data
      } catch (err) {
        this.erro = normalizeError(err)
        throw err
      }
    }
  },
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useDocumentsStore, import.meta.hot))
}
