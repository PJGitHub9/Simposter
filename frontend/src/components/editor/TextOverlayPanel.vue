<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  enabled: boolean
  customText: string
  fontFamily: string
  fontSize: number
  fontWeight: string
  textColor: string
  textAlign: string
  textTransform: string
  letterSpacing: number
  lineHeight: number
  positionY: number
  shadowEnabled: boolean
  shadowBlur: number
  shadowOffsetX: number
  shadowOffsetY: number
  shadowColor: string
  shadowOpacity: number
  strokeEnabled: boolean
  strokeWidth: number
  strokeColor: string
  availableFonts: string[]
}>()

const emit = defineEmits<{
  (e: 'update:enabled', value: boolean): void
  (e: 'update:customText', value: string): void
  (e: 'update:fontFamily', value: string): void
  (e: 'update:fontSize', value: number): void
  (e: 'update:fontWeight', value: string): void
  (e: 'update:textColor', value: string): void
  (e: 'update:textAlign', value: string): void
  (e: 'update:textTransform', value: string): void
  (e: 'update:letterSpacing', value: number): void
  (e: 'update:lineHeight', value: number): void
  (e: 'update:positionY', value: number): void
  (e: 'update:shadowEnabled', value: boolean): void
  (e: 'update:shadowBlur', value: number): void
  (e: 'update:shadowOffsetX', value: number): void
  (e: 'update:shadowOffsetY', value: number): void
  (e: 'update:shadowColor', value: string): void
  (e: 'update:shadowOpacity', value: number): void
  (e: 'update:strokeEnabled', value: boolean): void
  (e: 'update:strokeWidth', value: number): void
  (e: 'update:strokeColor', value: string): void
}>()

const fontWeights = ['100', '200', '300', '400', '500', '600', '700', '800', '900']
const textAlignments = ['left', 'center', 'right']
const textTransforms = ['none', 'uppercase', 'lowercase', 'capitalize']
</script>

<template>
  <div class="text-overlay-panel">
    <div class="panel-header">
      <div class="panel-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 7V4h16v3M9 20h6M12 4v16"/>
        </svg>
        Custom Text Overlay
      </div>
      <label class="toggle-switch">
        <input
          type="checkbox"
          :checked="enabled"
          @change="emit('update:enabled', ($event.target as HTMLInputElement).checked)"
        />
        <span class="toggle-slider"></span>
      </label>
    </div>

    <div v-if="enabled" class="panel-content">
      <!-- Text Input -->
      <div class="field-group">
        <label class="field-label">
          Text Content
          <input
            :value="customText"
            @input="emit('update:customText', ($event.target as HTMLInputElement).value)"
            type="text"
            placeholder="Enter custom text..."
            class="text-input"
          />
        </label>
        <div class="field-hint">
          Use template variables: {title}, {year}, {season}
        </div>
      </div>

      <hr class="mini-divider" />

      <!-- Font Settings -->
      <div class="field-group">
        <div class="subsection-title">Font Settings</div>

        <label class="field-label">
          Font Family
          <select :value="fontFamily" @change="emit('update:fontFamily', ($event.target as HTMLSelectElement).value)">
            <optgroup label="System Fonts">
              <option value="Arial">Arial</option>
              <option value="Helvetica">Helvetica</option>
              <option value="Times New Roman">Times New Roman</option>
              <option value="Georgia">Georgia</option>
              <option value="Verdana">Verdana</option>
              <option value="Courier New">Courier New</option>
              <option value="Impact">Impact</option>
            </optgroup>
            <optgroup v-if="availableFonts.length > 0" label="Custom Fonts">
              <option v-for="font in availableFonts" :key="font" :value="font">{{ font }}</option>
            </optgroup>
          </select>
        </label>

        <div class="slider">
          <label>Font Size</label>
          <div class="slider-row">
            <input
              :value="fontSize"
              @input="emit('update:fontSize', Number(($event.target as HTMLInputElement).value))"
              type="range"
              min="20"
              max="400"
            />
            <input
              :value="fontSize"
              @input="emit('update:fontSize', Number(($event.target as HTMLInputElement).value))"
              type="number"
              min="20"
              max="400"
              class="slider-num"
            />
          </div>
        </div>

        <label class="field-label">
          Font Weight
          <select :value="fontWeight" @change="emit('update:fontWeight', ($event.target as HTMLSelectElement).value)">
            <option v-for="weight in fontWeights" :key="weight" :value="weight">
              {{ weight === '400' ? 'Normal (400)' : weight === '700' ? 'Bold (700)' : weight }}
            </option>
          </select>
        </label>

        <label class="field-label">
          Text Color
          <input
            :value="textColor"
            @input="emit('update:textColor', ($event.target as HTMLInputElement).value)"
            type="color"
          />
        </label>
      </div>

      <hr class="mini-divider" />

      <!-- Text Styling -->
      <div class="field-group">
        <div class="subsection-title">Text Styling</div>

        <label class="field-label">
          Text Align
          <div class="button-group">
            <button
              v-for="align in textAlignments"
              :key="align"
              :class="['align-btn', { active: textAlign === align }]"
              @click="emit('update:textAlign', align)"
            >
              <svg v-if="align === 'left'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="17" y1="10" x2="3" y2="10"/>
                <line x1="21" y1="6" x2="3" y2="6"/>
                <line x1="21" y1="14" x2="3" y2="14"/>
                <line x1="17" y1="18" x2="3" y2="18"/>
              </svg>
              <svg v-else-if="align === 'center'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="10" x2="6" y2="10"/>
                <line x1="21" y1="6" x2="3" y2="6"/>
                <line x1="21" y1="14" x2="3" y2="14"/>
                <line x1="18" y1="18" x2="6" y2="18"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="21" y1="10" x2="7" y2="10"/>
                <line x1="21" y1="6" x2="3" y2="6"/>
                <line x1="21" y1="14" x2="3" y2="14"/>
                <line x1="21" y1="18" x2="7" y2="18"/>
              </svg>
            </button>
          </div>
        </label>

        <label class="field-label">
          Text Transform
          <select :value="textTransform" @change="emit('update:textTransform', ($event.target as HTMLSelectElement).value)">
            <option v-for="transform in textTransforms" :key="transform" :value="transform">
              {{ transform.charAt(0).toUpperCase() + transform.slice(1) }}
            </option>
          </select>
        </label>

        <div class="slider">
          <label>Letter Spacing</label>
          <div class="slider-row">
            <input
              :value="letterSpacing"
              @input="emit('update:letterSpacing', Number(($event.target as HTMLInputElement).value))"
              type="range"
              min="-5"
              max="20"
            />
            <input
              :value="letterSpacing"
              @input="emit('update:letterSpacing', Number(($event.target as HTMLInputElement).value))"
              type="number"
              min="-5"
              max="20"
              class="slider-num"
            />
          </div>
        </div>

        <div class="slider">
          <label>Line Height</label>
          <div class="slider-row">
            <input
              :value="lineHeight"
              @input="emit('update:lineHeight', Number(($event.target as HTMLInputElement).value))"
              type="range"
              min="80"
              max="200"
            />
            <input
              :value="lineHeight"
              @input="emit('update:lineHeight', Number(($event.target as HTMLInputElement).value))"
              type="number"
              min="80"
              max="200"
              class="slider-num"
            />
          </div>
        </div>

        <div class="slider">
          <label>Vertical Position %</label>
          <div class="slider-row">
            <input
              :value="positionY"
              @input="emit('update:positionY', Number(($event.target as HTMLInputElement).value))"
              type="range"
              min="0"
              max="100"
            />
            <input
              :value="positionY"
              @input="emit('update:positionY', Number(($event.target as HTMLInputElement).value))"
              type="number"
              min="0"
              max="100"
              class="slider-num"
            />
          </div>
        </div>
      </div>

      <hr class="mini-divider" />

      <!-- Text Shadow -->
      <div class="field-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            :checked="shadowEnabled"
            @change="emit('update:shadowEnabled', ($event.target as HTMLInputElement).checked)"
          />
          <span>Enable Text Shadow</span>
        </label>

        <div v-if="shadowEnabled" class="shadow-controls">
          <div class="slider">
            <label>Shadow Blur</label>
            <div class="slider-row">
              <input
                :value="shadowBlur"
                @input="emit('update:shadowBlur', Number(($event.target as HTMLInputElement).value))"
                type="range"
                min="0"
                max="50"
              />
              <input
                :value="shadowBlur"
                @input="emit('update:shadowBlur', Number(($event.target as HTMLInputElement).value))"
                type="number"
                min="0"
                max="50"
                class="slider-num"
              />
            </div>
          </div>

          <div class="slider">
            <label>Shadow Offset X</label>
            <div class="slider-row">
              <input
                :value="shadowOffsetX"
                @input="emit('update:shadowOffsetX', Number(($event.target as HTMLInputElement).value))"
                type="range"
                min="-30"
                max="30"
              />
              <input
                :value="shadowOffsetX"
                @input="emit('update:shadowOffsetX', Number(($event.target as HTMLInputElement).value))"
                type="number"
                min="-30"
                max="30"
                class="slider-num"
              />
            </div>
          </div>

          <div class="slider">
            <label>Shadow Offset Y</label>
            <div class="slider-row">
              <input
                :value="shadowOffsetY"
                @input="emit('update:shadowOffsetY', Number(($event.target as HTMLInputElement).value))"
                type="range"
                min="-30"
                max="30"
              />
              <input
                :value="shadowOffsetY"
                @input="emit('update:shadowOffsetY', Number(($event.target as HTMLInputElement).value))"
                type="number"
                min="-30"
                max="30"
                class="slider-num"
              />
            </div>
          </div>

          <label class="field-label">
            Shadow Color
            <input
              :value="shadowColor"
              @input="emit('update:shadowColor', ($event.target as HTMLInputElement).value)"
              type="color"
            />
          </label>

          <div class="slider">
            <label>Shadow Opacity %</label>
            <div class="slider-row">
              <input
                :value="shadowOpacity"
                @input="emit('update:shadowOpacity', Number(($event.target as HTMLInputElement).value))"
                type="range"
                min="0"
                max="100"
              />
              <input
                :value="shadowOpacity"
                @input="emit('update:shadowOpacity', Number(($event.target as HTMLInputElement).value))"
                type="number"
                min="0"
                max="100"
                class="slider-num"
              />
            </div>
          </div>
        </div>
      </div>

      <hr class="mini-divider" />

      <!-- Text Stroke -->
      <div class="field-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            :checked="strokeEnabled"
            @change="emit('update:strokeEnabled', ($event.target as HTMLInputElement).checked)"
          />
          <span>Enable Text Outline</span>
        </label>

        <div v-if="strokeEnabled" class="stroke-controls">
          <div class="slider">
            <label>Outline Width</label>
            <div class="slider-row">
              <input
                :value="strokeWidth"
                @input="emit('update:strokeWidth', Number(($event.target as HTMLInputElement).value))"
                type="range"
                min="1"
                max="20"
              />
              <input
                :value="strokeWidth"
                @input="emit('update:strokeWidth', Number(($event.target as HTMLInputElement).value))"
                type="number"
                min="1"
                max="20"
                class="slider-num"
              />
            </div>
          </div>

          <label class="field-label">
            Outline Color
            <input
              :value="strokeColor"
              @input="emit('update:strokeColor', ($event.target as HTMLInputElement).value)"
              type="color"
            />
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.text-overlay-panel {
  background: rgba(61, 214, 183, 0.04);
  border: 1px solid rgba(61, 214, 183, 0.2);
  border-radius: 12px;
  overflow: hidden;
  margin-top: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: rgba(61, 214, 183, 0.08);
  border-bottom: 1px solid rgba(61, 214, 183, 0.15);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
}

.panel-title svg {
  flex-shrink: 0;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  cursor: pointer;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.1);
  border: 1px solid var(--border);
  transition: 0.3s;
  border-radius: 24px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: #dce6ff;
  transition: 0.3s;
  border-radius: 50%;
}

input:checked + .toggle-slider {
  background-color: var(--accent);
  border-color: var(--accent);
}

input:checked + .toggle-slider:before {
  transform: translateX(20px);
  background-color: white;
}

.panel-content {
  padding: 14px;
}

.field-group {
  margin-bottom: 12px;
}

.subsection-title {
  font-size: 12px;
  font-weight: 600;
  color: #c9d6ff;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mini-divider {
  border: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  margin: 12px 0;
}

.field-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 500;
  color: #c4cceb;
}

.field-hint {
  font-size: 11px;
  color: rgba(61, 214, 183, 0.7);
  margin-top: 4px;
  font-style: italic;
}

.text-input,
.field-label select,
.field-label input[type='color'] {
  width: 100%;
  padding: 8px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
  transition: all 0.2s;
}

.text-input:focus,
.field-label select:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(255, 255, 255, 0.06);
}

.field-label input[type='color'] {
  height: 38px;
  cursor: pointer;
}

.button-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}

.align-btn {
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: #c4cceb;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.align-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(61, 214, 183, 0.3);
}

.align-btn.active {
  background: rgba(61, 214, 183, 0.15);
  border-color: var(--accent);
  color: var(--accent);
}

.slider {
  margin-bottom: 12px;
}

.slider label {
  font-size: 12px;
  font-weight: 500;
  color: #c4cceb;
  margin-bottom: 6px;
  display: block;
}

.slider-row {
  display: grid;
  grid-template-columns: 1fr 70px;
  gap: 8px;
  align-items: center;
}

.slider-row input[type='range'] {
  width: 100%;
}

.slider-num {
  width: 100%;
  padding: 6px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 12px;
  text-align: center;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #dce6ff;
  cursor: pointer;
  margin-bottom: 10px;
}

.checkbox-label input[type='checkbox'] {
  cursor: pointer;
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.shadow-controls,
.stroke-controls {
  margin-top: 10px;
  padding-left: 12px;
  border-left: 2px solid rgba(61, 214, 183, 0.2);
}
</style>
