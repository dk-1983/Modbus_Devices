export const DEVICE_CARD_TAG = "modbus-device-card";
export const DEVICE_CARD_EDITOR_TAG = "modbus-device-card-editor";

export class ModbusDeviceCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(DEVICE_CARD_EDITOR_TAG);
  }

  static getStubConfig() {
    return {};
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    const message = document.createElement("ha-card");
    message.textContent =
      "Edit this legacy card and select a Modbus Device to convert it to a native Entities card.";
    message.style.padding = "16px";
    this.shadowRoot.replaceChildren(message);
  }

  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;
  }
}

export class ModbusDeviceCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._generation = 0;
  }

  setConfig(config) {
    this._config = config;
    if (config.device_id && !this._deviceId) {
      this._deviceId = config.device_id;
      this._generateWhenReady = true;
    }
    this._render();
    this._maybeGenerateLegacyConfig();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._maybeGenerateLegacyConfig();
  }

  _maybeGenerateLegacyConfig() {
    if (this._generateWhenReady && this._hass && this._deviceId) {
      this._generateWhenReady = false;
      void this._generate(this._deviceId);
    }
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    const container = document.createElement("div");
    container.style.display = "grid";
    container.style.gap = "12px";

    const selector = document.createElement("ha-selector");
    selector.hass = this._hass;
    selector.selector = {
      device: { filter: { integration: "modbus_devices" } },
    };
    selector.value = this._deviceId;
    selector.label = "Modbus Device";
    selector.addEventListener("value-changed", (event) => {
      const deviceId = event.detail?.value;
      if (deviceId === this._deviceId) {
        return;
      }
      this._deviceId = deviceId;
      if (!deviceId) {
        this._generation += 1;
        this._loading = false;
        this._error = undefined;
        this._render();
        return;
      }
      void this._generate(deviceId);
    });
    container.append(selector);

    if (this._loading) {
      const progress = document.createElement("ha-linear-progress");
      progress.indeterminate = true;
      container.append(progress);
    }
    if (this._error) {
      const error = document.createElement("ha-alert");
      error.alertType = "error";
      error.textContent = this._error;
      container.append(error);
      const retry = document.createElement("ha-button");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._generate(this._deviceId);
      });
      container.append(retry);
    }
    this.shadowRoot.replaceChildren(container);
  }

  async _generate(deviceId) {
    if (!this._hass || !deviceId) {
      return;
    }
    const generation = ++this._generation;
    this._loading = true;
    this._error = undefined;
    this._render();
    try {
      const generatedConfig = await this._hass.callWS({
        type: "modbus_devices/presentation/build",
        device_id: deviceId,
      });
      if (generation !== this._generation) {
        return;
      }
      if (
        !generatedConfig ||
        generatedConfig.type !== "entities" ||
        !Array.isArray(generatedConfig.entities)
      ) {
        throw new Error("The selected device did not produce an Entities card");
      }
      this.dispatchEvent(
        new CustomEvent("config-changed", {
          detail: { config: generatedConfig },
          bubbles: true,
          composed: true,
        }),
      );
    } catch (error) {
      if (generation === this._generation) {
        this._error =
          error instanceof Error ? error.message : "Unable to generate card";
      }
    } finally {
      if (generation === this._generation) {
        this._loading = false;
        this._render();
      }
    }
  }
}

export function registerModbusDeviceCard() {
  if (!globalThis.customElements.get(DEVICE_CARD_EDITOR_TAG)) {
    globalThis.customElements.define(
      DEVICE_CARD_EDITOR_TAG,
      ModbusDeviceCardEditor,
    );
  }
  if (!globalThis.customElements.get(DEVICE_CARD_TAG)) {
    globalThis.customElements.define(DEVICE_CARD_TAG, ModbusDeviceCard);
  }
  globalThis.customCards = globalThis.customCards ?? [];
  if (!globalThis.customCards.some((card) => card.type === DEVICE_CARD_TAG)) {
    globalThis.customCards.push({
      type: DEVICE_CARD_TAG,
      name: "Modbus Device",
      description: "Generate a native Entities card for a Modbus Device",
      preview: true,
    });
  }
}

registerModbusDeviceCard();
