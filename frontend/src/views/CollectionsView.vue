<template>
  <div class="view glass">
    <div class="header">
      <div>
        <p class="label">Collections</p>
        <h2>Curate bundles</h2>
      </div>
      <button class="ghost">New Collection</button>
    </div>
    <div class="list">
      <div class="row">
        <div>
          <p class="name">Villeneuve Pack</p>
          <p class="muted">Dune • Arrival • Blade Runner 2049</p>
        </div>
        <span class="pill">Auto-sync</span>
      </div>
      <div class="row">
        <div>
          <p class="name">Space Horror</p>
          <p class="muted">Alien • Aliens • Prometheus • Covenant</p>
        </div>
        <span class="pill">Manual</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.view {
  padding: 16px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.label {
  text-transform: uppercase;
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 1px;
}

.ghost {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
  color: #dce6ff;
  cursor: pointer;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}

.name {
  font-weight: 600;
}

.muted {
  color: var(--muted);
}

.pill {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(91, 141, 238, 0.18);
  color: #dbe6ff;
  font-size: 12px;
}
</style>
