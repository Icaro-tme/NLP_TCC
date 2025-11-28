<template>
  <div class="html-viewer-container fit column">
    <div class="col-auto q-pa-sm bg-grey-2 border-bottom row items-center justify-between" v-if="url">
      <div class="text-subtitle2 text-grey-8 ellipsis">{{ title || 'Visualização' }}</div>
      <q-btn icon="open_in_new" flat round dense size="sm" type="a" :href="url" target="_blank" title="Abrir em nova aba" />
    </

    <div class="col relative-position">
      <iframe
        v-if="url"
        :src="url"
                style="min-height:90vh;" class="fit"
        frameborder="0"
        title="Visualização do Documento"
      ></iframe>
      <div v-else class="absolute-center text-center text-grey-5">
        <q-icon name="description" size="4rem" />
        <div class="text-h6 q-mt-sm">Selecione uma variante para visualizar</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  url: {
    type: String,
    default: null
  },
  title: {
    type: String,
    default: ''
  }
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
</style>
