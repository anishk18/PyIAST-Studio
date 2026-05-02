const colors = ["#0d7b83", "#c48518", "#b65353", "#30805a", "#5f6db3"];
const defaultComponents = [
  {
    name: "Ethane",
    method: "model",
    model: "Langmuir",
    fill_value: null,
    data: [
      { pressure: 1, loading: 1.72 },
      { pressure: 5, loading: 6.8 },
      { pressure: 15, loading: 13.2 },
      { pressure: 35, loading: 20.8 },
      { pressure: 65, loading: 27.4 },
    ],
  },
  {
    name: "Methane",
    method: "model",
    model: "Langmuir",
    fill_value: null,
    data: [
      { pressure: 1, loading: 0.61 },
      { pressure: 5, loading: 2.85 },
      { pressure: 15, loading: 6.9 },
      { pressure: 35, loading: 10.9 },
      { pressure: 65, loading: 13.7 },
    ],
  },
];

let state = {
  mode: "forward",
  models: ["Langmuir", "Quadratic", "BET", "Henry", "DSLangmuir", "TemkinApprox"],
  components: structuredClone(defaultComponents),
  fractions: [0.05, 0.95],
  result: null,
};

const componentsEl = document.querySelector("#components");
const fractionsEl = document.querySelector("#fractions");
const runButton = document.querySelector("#run-button");
const addComponentButton = document.querySelector("#add-component");
const normalizeButton = document.querySelector("#normalize-button");
const forwardButton = document.querySelector("#forward-mode");
const reverseButton = document.querySelector("#reverse-mode");
const totalPressureInput = document.querySelector("#total-pressure");
const messageEl = document.querySelector("#message");
const resultTableEl = document.querySelector("#result-table");
const paramsTableEl = document.querySelector("#params-table");
const chart = document.querySelector("#fit-chart");

async function boot() {
  try {
    const response = await fetch("/api/models");
    if (response.ok) {
      const payload = await response.json();
      if (payload.models?.length) state.models = payload.models;
    }
  } catch {
    setMessage("Model list unavailable until the backend dependencies are installed.");
  }
  render();
  drawChart();
}

function render() {
  renderMode();
  renderComponents();
  renderFractions();
  renderResults();
}

function renderMode() {
  forwardButton.classList.toggle("active", state.mode === "forward");
  reverseButton.classList.toggle("active", state.mode === "reverse");
  document.querySelector("#composition-label").textContent =
    state.mode === "forward" ? "Gas phase mole fractions" : "Adsorbed phase mole fractions";
  runButton.textContent = state.mode === "forward" ? "Run IAST" : "Run Reverse IAST";
}

function renderComponents() {
  componentsEl.replaceChildren();
  state.components.forEach((component, index) => {
    const node = document.querySelector("#component-template").content.cloneNode(true);
    const card = node.querySelector(".component-card");
    card.style.borderTop = `4px solid ${colors[index % colors.length]}`;

    const name = node.querySelector(".component-name");
    name.value = component.name;
    name.addEventListener("input", () => {
      component.name = name.value || `Component ${index + 1}`;
      renderFractions();
    });

    const method = node.querySelector(".component-method");
    method.value = component.method;
    method.addEventListener("change", () => {
      component.method = method.value;
      render();
    });

    const model = node.querySelector(".component-model");
    state.models.forEach((modelName) => {
      const option = document.createElement("option");
      option.value = modelName;
      option.textContent = modelName;
      model.append(option);
    });
    model.value = component.model;
    model.disabled = component.method === "interpolator";
    model.addEventListener("change", () => {
      component.model = model.value;
    });

    const fill = node.querySelector(".component-fill");
    fill.value = component.fill_value ?? "";
    fill.disabled = component.method === "model";
    fill.addEventListener("input", () => {
      component.fill_value = fill.value === "" ? null : Number(fill.value);
    });

    node.querySelector(".remove-component").disabled = state.components.length <= 2;
    node.querySelector(".remove-component").addEventListener("click", () => {
      state.components.splice(index, 1);
      state.fractions.splice(index, 1);
      normalizeFractions();
      state.result = null;
      render();
      drawChart();
    });

    node.querySelector(".add-row").addEventListener("click", () => {
      const last = component.data.at(-1) ?? { pressure: 1, loading: 1 };
      component.data.push({
        pressure: Number((last.pressure * 1.5).toFixed(3)),
        loading: Number((last.loading * 1.1).toFixed(3)),
      });
      render();
    });

    node.querySelector(".component-file").addEventListener("change", async (event) => {
      const file = event.target.files?.[0];
      if (file) await importCsv(component, file);
    });

    node.querySelector(".data-table-wrap").append(makeDataTable(component));
    componentsEl.append(node);
  });
}

function makeDataTable(component) {
  const table = document.createElement("table");
  table.innerHTML = `
    <thead>
      <tr><th>Pressure</th><th>Loading</th><th></th></tr>
    </thead>
    <tbody></tbody>
  `;
  const body = table.querySelector("tbody");
  component.data.forEach((point, rowIndex) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input type="number" min="0" step="0.001" value="${point.pressure}"></td>
      <td><input type="number" min="0" step="0.001" value="${point.loading}"></td>
      <td><button class="row-remove" type="button" title="Remove row">×</button></td>
    `;
    const [pressureInput, loadingInput] = row.querySelectorAll("input");
    pressureInput.addEventListener("input", () => {
      point.pressure = Number(pressureInput.value);
    });
    loadingInput.addEventListener("input", () => {
      point.loading = Number(loadingInput.value);
    });
    row.querySelector("button").disabled = component.data.length <= 2;
    row.querySelector("button").addEventListener("click", () => {
      component.data.splice(rowIndex, 1);
      render();
    });
    body.append(row);
  });
  return table;
}

function renderFractions() {
  fractionsEl.replaceChildren();
  state.components.forEach((component, index) => {
    const item = document.createElement("label");
    item.className = "fraction-item";
    item.innerHTML = `
      <span>${component.name || `Component ${index + 1}`}</span>
      <input type="number" min="0" max="1" step="0.001" value="${state.fractions[index] ?? 0}">
    `;
    const input = item.querySelector("input");
    input.addEventListener("input", () => {
      state.fractions[index] = Number(input.value);
    });
    fractionsEl.append(item);
  });
}

function renderResults() {
  if (!state.result) return;
  const resultRows = state.result.components
    .map(
      (row) => `
      <tr>
        <td>${row.name}</td>
        <td>${formatNumber(row.partial_pressure)}</td>
        <td>${formatNumber(row.loading)}</td>
        <td>${formatNumber(row.gas_fraction)}</td>
        <td>${formatNumber(row.adsorbed_fraction ?? "")}</td>
      </tr>`,
    )
    .join("");

  resultTableEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Component</th>
          <th>Partial P</th>
          <th>Loading</th>
          <th>Gas y</th>
          <th>Adsorbed x</th>
        </tr>
      </thead>
      <tbody>${resultRows}</tbody>
    </table>
    <p class="metric">Total loading: ${formatNumber(state.result.total_loading)}</p>
  `;

  paramsTableEl.innerHTML = `
    <table>
      <thead><tr><th>Component</th><th>Model</th><th>Parameters</th></tr></thead>
      <tbody>
        ${state.result.fits
          .map(
            (fit) => `
          <tr>
            <td>${fit.name}</td>
            <td>${fit.model}</td>
            <td>${formatParams(fit.params)}</td>
          </tr>`,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function importCsv(component, file) {
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/parse-csv", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail ?? "CSV import failed");
    const pressureColumn = findColumn(payload.columns, ["pressure", "p"]);
    const loadingColumn = findColumn(payload.columns, ["loading", "uptake", "q"]);
    if (!pressureColumn || !loadingColumn) {
      throw new Error("CSV needs pressure and loading columns.");
    }
    component.data = payload.rows
      .map((row) => ({
        pressure: Number(row[pressureColumn]),
        loading: Number(row[loadingColumn]),
      }))
      .filter((row) => Number.isFinite(row.pressure) && Number.isFinite(row.loading));
    if (component.data.length < 2) throw new Error("CSV needs at least two valid rows.");
    setMessage("");
    render();
  } catch (error) {
    setMessage(error.message);
  }
}

function findColumn(columns, candidates) {
  return columns.find((column) => {
    const normalized = column.toLowerCase();
    return candidates.some((candidate) => normalized.includes(candidate));
  });
}

function normalizeFractions() {
  const total = state.fractions.reduce((sum, value) => sum + Number(value || 0), 0);
  if (!total) {
    state.fractions = state.components.map(() => 1 / state.components.length);
    return;
  }
  state.fractions = state.components.map((_, index) =>
    Number(((state.fractions[index] || 0) / total).toFixed(6)),
  );
}

async function runCalculation() {
  normalizeFractions();
  renderFractions();
  setMessage("");
  const payload = {
    components: state.components,
    total_pressure: Number(totalPressureInput.value),
  };
  if (state.mode === "forward") {
    payload.gas_fractions = state.fractions;
  } else {
    payload.adsorbed_fractions = state.fractions;
  }

  const endpoint = state.mode === "forward" ? "/api/iast" : "/api/reverse-iast";
  runButton.disabled = true;
  runButton.textContent = "Running";
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail ?? "Calculation failed");
    state.result = result;
    renderResults();
    drawChart();
  } catch (error) {
    setMessage(error.message);
  } finally {
    runButton.disabled = false;
    renderMode();
  }
}

function drawChart() {
  const context = chart.getContext("2d");
  const width = chart.width;
  const height = chart.height;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#fbfdfc";
  context.fillRect(0, 0, width, height);

  const fits = state.result?.fits ?? state.components.map((component) => ({ ...component, fit: [] }));
  const allPoints = fits.flatMap((fit) => [
    ...(fit.data ?? componentDataForName(fit.name)),
    ...(fit.fit ?? []),
  ]);
  const maxX = Math.max(1, ...allPoints.map((point) => point.pressure));
  const maxY = Math.max(1, ...allPoints.map((point) => point.loading));
  const plot = { left: 58, top: 22, right: width - 22, bottom: height - 46 };

  context.strokeStyle = "#cfd9d8";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(plot.left, plot.top);
  context.lineTo(plot.left, plot.bottom);
  context.lineTo(plot.right, plot.bottom);
  context.stroke();

  context.fillStyle = "#68747a";
  context.font = "12px Inter, sans-serif";
  context.fillText("Loading", 12, 22);
  context.fillText("Pressure", width - 82, height - 14);

  fits.forEach((fit, index) => {
    const color = colors[index % colors.length];
    const data = fit.data ?? componentDataForName(fit.name);
    const line = fit.fit ?? [];
    context.strokeStyle = color;
    context.lineWidth = 2;
    if (line.length) {
      context.beginPath();
      line.forEach((point, pointIndex) => {
        const x = scale(point.pressure, 0, maxX, plot.left, plot.right);
        const y = scale(point.loading, 0, maxY, plot.bottom, plot.top);
        if (pointIndex === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.stroke();
    }
    context.fillStyle = color;
    data.forEach((point) => {
      const x = scale(point.pressure, 0, maxX, plot.left, plot.right);
      const y = scale(point.loading, 0, maxY, plot.bottom, plot.top);
      context.beginPath();
      context.arc(x, y, 4, 0, Math.PI * 2);
      context.fill();
    });
    context.fillText(fit.name, plot.left + 12, plot.top + 18 + index * 18);
  });
}

function componentDataForName(name) {
  return state.components.find((component) => component.name === name)?.data ?? [];
}

function scale(value, min, max, targetMin, targetMax) {
  return targetMin + ((value - min) / (max - min || 1)) * (targetMax - targetMin);
}

function setMessage(message) {
  messageEl.textContent = Array.isArray(message)
    ? message.map((item) => item.msg ?? item).join(" ")
    : message;
}

function formatNumber(value) {
  if (value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toLocaleString(undefined, { maximumSignificantDigits: 6 });
}

function formatParams(params) {
  const entries = Object.entries(params ?? {});
  if (!entries.length) return "n/a";
  return entries.map(([key, value]) => `${key}: ${formatNumber(value)}`).join(", ");
}

forwardButton.addEventListener("click", () => {
  state.mode = "forward";
  state.result = null;
  render();
  drawChart();
});

reverseButton.addEventListener("click", () => {
  state.mode = "reverse";
  state.result = null;
  render();
  drawChart();
});

addComponentButton.addEventListener("click", () => {
  const nextIndex = state.components.length + 1;
  state.components.push({
    name: `Component ${nextIndex}`,
    method: "model",
    model: "Langmuir",
    fill_value: null,
    data: [
      { pressure: 1, loading: 1 },
      { pressure: 10, loading: 4 },
      { pressure: 50, loading: 8 },
    ],
  });
  state.fractions.push(0);
  normalizeFractions();
  state.result = null;
  render();
  drawChart();
});

normalizeButton.addEventListener("click", () => {
  normalizeFractions();
  renderFractions();
});

runButton.addEventListener("click", runCalculation);
window.addEventListener("resize", drawChart);

boot();
