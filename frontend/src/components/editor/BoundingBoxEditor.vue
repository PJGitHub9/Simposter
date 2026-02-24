<template>
  <div class="panel glass">
    <p class="panel__title">Bounding Boxes</p>
    <div class="grid">
      <div class="box">
        <p class="label">Hero</p>
        <p class="value">X: 120 • Y: 80 • W: 420 • H: 660</p>
      </div>
      <div class="box">
        <p class="label">Logo</p>
        <p class="value">X: 160 • Y: 720 • W: 300 • H: 90</p>
      </div>
      <div class="box">
        <p class="label">Overlay</p>
        <p class="value">X: 0 • Y: 0 • W: full • H: gradient</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  padding: 12px;
}

.panel__title {
  font-weight: 600;
  margin-bottom: 8px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.box {
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.label {
  color: var(--muted);
  font-size: 12px;
}

.value {
  font-weight: 600;
  color: #d8e3ff;
}
</style>
