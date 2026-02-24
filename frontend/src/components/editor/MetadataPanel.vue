<template>
  <div class="panel glass">
    <p class="panel__title">Metadata</p>
    <div class="rows">
      <div class="row">
        <span class="label">Studio</span>
        <span class="value">Warner Bros</span>
      </div>
      <div class="row">
        <span class="label">Language</span>
        <span class="value">EN</span>
      </div>
      <div class="row">
        <span class="label">Status</span>
        <span class="pill success">Ready</span>
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

.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  justify-content: space-between;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
}

.label {
  color: var(--muted);
  font-size: 13px;
}

.value {
  font-weight: 600;
}

.pill {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
}

.success {
  background: rgba(61, 214, 183, 0.15);
  color: #b4ffe5;
}
</style>
