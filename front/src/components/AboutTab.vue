<script setup lang="ts">
const qqImg = '/docs/qq.png'
const donateImg = '/docs/donate.png'
</script>

<template>
  <div class="card">
    <div class="card-header">关于</div>
    <div class="space-y-2">
      <p>感谢使用 GCLI2API 控制面板。</p>
      <img :src="qqImg" alt="QQ" class="w-40" />
      <img :src="donateImg" alt="Donate" class="w-40" />
    </div>
  </div>
</template>

<style scoped>
.card { @apply bg-white rounded-lg shadow p-4; }
.card-header { @apply text-lg font-semibold mb-3; }
</style>