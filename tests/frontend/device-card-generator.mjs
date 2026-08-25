import assert from "node:assert/strict";
import test from "node:test";

class FakeElement {
  constructor(tag = "element") {
    this.tagName = tag;
    this.children = [];
    this.listeners = new Map();
    this.style = {};
  }

  attachShadow() {
    this.shadowRoot = new FakeElement("shadow-root");
    return this.shadowRoot;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener(type, callback) {
    this.listeners.set(type, callback);
  }

  dispatchEvent(event) {
    this.events ??= [];
    this.events.push(event);
    this.listeners.get(event.type)?.(event);
    return true;
  }

  emit(type, detail) {
    this.listeners.get(type)?.({ detail });
  }

  find(tag) {
    if (this.tagName === tag) return this;
    for (const child of this.children) {
      const found = child.find?.(tag);
      if (found) return found;
    }
    return undefined;
  }
}

globalThis.HTMLElement = FakeElement;
globalThis.CustomEvent = class {
  constructor(type, options = {}) {
    this.type = type;
    Object.assign(this, options);
  }
};
globalThis.document = {
  createElement(tag) {
    const ElementClass = globalThis.customElements.get(tag);
    return ElementClass ? new ElementClass() : new FakeElement(tag);
  },
};
globalThis.customElements = {
  definitions: new Map(),
  define(tag, implementation) {
    this.definitions.set(tag, implementation);
  },
  get(tag) {
    return this.definitions.get(tag);
  },
};

const {
  DEVICE_CARD_EDITOR_TAG,
  DEVICE_CARD_TAG,
  ModbusDeviceCard,
  ModbusDeviceCardEditor,
} = await import(
  "../../custom_components/modbus_devices/dashboard/frontend/device-card-generator.js"
);

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

const nativeConfig = (title, entities) => ({
  type: "entities",
  title,
  show_header_toggle: false,
  entities,
});

function editorHarness(response) {
  const calls = [];
  const editor = new ModbusDeviceCardEditor();
  editor.hass = {
    async callWS(message) {
      calls.push(message);
      if (response instanceof Error) throw response;
      return structuredClone(response);
    },
  };
  editor.setConfig({ type: `custom:${DEVICE_CARD_TAG}` });
  return { calls, editor };
}

async function select(editor, deviceId) {
  editor.shadowRoot.find("ha-selector").emit("value-changed", {
    value: deviceId,
  });
  await tick();
  await tick();
}

function emittedConfig(editor) {
  const event = editor.events?.find((candidate) =>
    candidate.type === "config-changed"
  );
  return event?.detail.config;
}

test("picker registration exposes the supported custom editor entry point", () => {
  const picker = globalThis.customCards.find(
    (candidate) => candidate.type === DEVICE_CARD_TAG,
  );
  assert.equal(picker.name, "Modbus Device");
  assert.equal(globalThis.customElements.get(DEVICE_CARD_EDITOR_TAG), ModbusDeviceCardEditor);
  assert.ok(ModbusDeviceCard.getConfigElement() instanceof ModbusDeviceCardEditor);
  assert.deepEqual(ModbusDeviceCard.getStubConfig(), {});
});

test("device selector is integration-filtered and generates one complete native config", async () => {
  const generated = nativeConfig("C2000-VT Balcony", [
    { entity: "sensor.c2000_vt_temperature", name: "Temperature" },
    {
      entity: "sensor.c2000_vt_temperature_state",
      name: "Temperature state",
    },
  ]);
  const { calls, editor } = editorHarness(generated);
  const selector = editor.shadowRoot.find("ha-selector");
  assert.deepEqual(selector.selector, {
    device: { filter: { integration: "modbus_devices" } },
  });
  await select(editor, "device-vt");
  assert.deepEqual(calls, [
    {
      type: "modbus_devices/presentation/build",
      device_id: "device-vt",
    },
  ]);
  assert.deepEqual(emittedConfig(editor), generated);
  assert.equal(emittedConfig(editor).type, "entities");
  assert.notEqual(emittedConfig(editor).type, `custom:${DEVICE_CARD_TAG}`);
  assert.deepEqual(emittedConfig(editor).entities.map((row) => row.name), [
    "Temperature",
    "Temperature state",
  ]);
});

test("KPB and Owen backend results pass through without editor branching", async () => {
  const fixtures = [
    nativeConfig("KPB Hallway 9", [
      { entity: "switch.kpb_9_output_1", name: "Output 1" },
      { entity: "switch.kpb_9_output_2", name: "Output 2" },
    ]),
    nativeConfig("Owen TRM-138", [
      { entity: "sensor.owen_temperature_1", name: "Temperature 1" },
    ]),
  ];
  for (const [index, generated] of fixtures.entries()) {
    const { editor } = editorHarness(generated);
    await select(editor, `physical-device-${index}`);
    assert.deepEqual(emittedConfig(editor), generated);
  }
  assert.equal(fixtures[0].entities.some((row) => row.entity.includes("kpb_10")), false);
});

test("connection loss is caught, shown, retryable, and emits no invalid config", async () => {
  const { calls, editor } = editorHarness(new Error("Connection lost"));
  const unhandled = [];
  const listener = (reason) => unhandled.push(reason);
  process.on("unhandledRejection", listener);
  await select(editor, "device-vt");
  process.off("unhandledRejection", listener);
  assert.deepEqual(unhandled, []);
  assert.equal(emittedConfig(editor), undefined);
  assert.equal(editor.shadowRoot.find("ha-alert").textContent, "Connection lost");
  editor.shadowRoot.find("ha-button").emit("click");
  await tick();
  assert.equal(calls.length, 2);
  assert.equal(emittedConfig(editor), undefined);
});

test("empty or non-Entities response never replaces the Lovelace config", async () => {
  for (const response of [null, {}, { type: `custom:${DEVICE_CARD_TAG}` }]) {
    const { editor } = editorHarness(response);
    await select(editor, "device-vt");
    assert.equal(emittedConfig(editor), undefined);
    assert.ok(editor.shadowRoot.find("ha-alert"));
  }
});

test("legacy runtime card is stable and never builds, nests a card, or emits ll-rebuild", () => {
  const card = new ModbusDeviceCard();
  let builds = 0;
  card.setConfig({
    type: `custom:${DEVICE_CARD_TAG}`,
    device_id: "device-vt",
  });
  for (let index = 0; index < 100; index += 1) {
    card.hass = {
      callWS() {
        builds += 1;
      },
      sequence: index,
    };
  }
  assert.equal(builds, 0);
  assert.equal(card.shadowRoot.children.length, 1);
  assert.equal(card.shadowRoot.children[0].tagName, "ha-card");
  assert.equal(card.events?.some((event) => event.type === "ll-rebuild") ?? false, false);
});

test("legacy editor state converts once and emits a complete native replacement", async () => {
  const generated = nativeConfig("C2000-VT Balcony", [
    { entity: "sensor.temperature", name: "Temperature" },
  ]);
  const calls = [];
  const editor = new ModbusDeviceCardEditor();
  editor.setConfig({
    type: `custom:${DEVICE_CARD_TAG}`,
    device_id: "device-vt",
  });
  editor.hass = {
    async callWS(message) {
      calls.push(message);
      return generated;
    },
  };
  await tick();
  assert.equal(calls.length, 1);
  assert.deepEqual(emittedConfig(editor), generated);
  assert.deepEqual(emittedConfig(editor), {
    type: "entities",
    title: "C2000-VT Balcony",
    show_header_toggle: false,
    entities: [{ entity: "sensor.temperature", name: "Temperature" }],
  });
});

test("HA edit-dialog transition replaces the custom editor and saves native config", async () => {
  const generated = nativeConfig("C2000-VT Balcony", [
    { entity: "sensor.temperature", name: "Temperature" },
  ]);
  const { editor } = editorHarness(generated);
  const dialog = {
    cardConfig: { type: `custom:${DEVICE_CARD_TAG}` },
    editorType: DEVICE_CARD_EDITOR_TAG,
    handleConfigChanged(event) {
      this.cardConfig = structuredClone(event.detail.config);
      if (this.cardConfig.type !== `custom:${DEVICE_CARD_TAG}`) {
        this.editorType = "hui-entities-card-editor";
      }
    },
    save() {
      return structuredClone(this.cardConfig);
    },
  };
  editor.addEventListener("config-changed", (event) =>
    dialog.handleConfigChanged(event)
  );
  await select(editor, "device-vt");
  assert.equal(dialog.editorType, "hui-entities-card-editor");
  assert.deepEqual(dialog.save(), generated);
  assert.equal(dialog.save().type, "entities");
  assert.equal(JSON.stringify(dialog.save()).includes("modbus-device-card"), false);
});
