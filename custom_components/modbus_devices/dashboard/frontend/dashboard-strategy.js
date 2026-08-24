export const STRATEGY_TAG = "ll-strategy-dashboard-modbus-devices";

export class ModbusDevicesDashboardStrategy extends HTMLElement {
  static noEditor = true;

  static async generate(_strategyConfig, hass) {
    return hass.callWS({ type: "modbus_devices/dashboard/build" });
  }
}

export function registerModbusDevicesDashboardStrategy() {
  if (!globalThis.customElements.get(STRATEGY_TAG)) {
    globalThis.customElements.define(
      STRATEGY_TAG,
      ModbusDevicesDashboardStrategy,
    );
  }
}

registerModbusDevicesDashboardStrategy();
