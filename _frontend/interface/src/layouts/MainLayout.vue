<template>
  <q-layout view="lHh Lpr lFf">
    <q-header flat>
      <q-toolbar>

        <q-toolbar-title>
          <div class="q-ml-lg text-title text-caption">          Tradução Automatizada de Documentos Jurídicos
</div>
        </q-toolbar-title>

        <div>Quasar v{{ $q.version }}</div>
      </q-toolbar>
    </q-header>



    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { ref } from 'vue'

</script>
