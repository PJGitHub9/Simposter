<template>
  <div class="panel glass">
    <p class="panel__title">Logo Overrides</p>
    <div class="fields">
      <label>
        <span>Primary Logo</span>
        <input type="text" placeholder="Upload or drop path" />
      </label>
      <label>
        <span>Placement</span>
        <select>
          <option>Bottom Center</option>
          <option>Top Left</option>
          <option>Custom</option>
        </select>
      </label>
      <label class="inline">
        <input type="checkbox" checked />
        <span>Lock aspect ratio</span>
      </label>
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

.fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
}

.inline {
  flex-direction: row;
  align-items: center;
}

input,
select {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.03);
  color: #e6edff;
}
</style>
