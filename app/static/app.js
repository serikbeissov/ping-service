// Дашборд: live-опрос /api/status, два вида (карточки/таблица), sparkline,
// поиск/фильтр/сортировка и модальный график latency.
(function () {
  "use strict";
  const REFRESH_MS = 7000;

  const state = {
    view: localStorage.getItem("dash_view") || "cards",
    sort: { key: "name", dir: 1 },
    search: "",
    zone: "",
    data: null,
  };

  // ---------- форматирование ----------
  const fmtLatency = (v) =>
    v === null || v === undefined ? "—" : Math.round(v) + " ms";
  const fmtUptime = (v) =>
    v === null || v === undefined ? "—" : v.toFixed(1) + "%";
  function statusClass(d) {
    if (d.is_up === false) return "bg-bad";
    if (d.is_up == null) return "bg-slate-500";
    return d.is_slow ? "bg-warn" : "bg-ok";
  }
  function statusTitle(d) {
    if (d.is_up === false) return "офлайн";
    if (d.is_up == null) return "нет данных";
    return d.is_slow ? "медленно" : "онлайн";
  }
  function typeLabel(d) {
    if (d.check_type === "tcp") return "TCP" + (d.port ? ":" + d.port : "");
    if (d.check_type === "http") return "HTTP";
    return "ICMP";
  }
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );

  // ---------- sparkline (inline SVG) ----------
  function sparkSVG(values, w, h) {
    w = w || 80;
    h = h || 24;
    if (!values || !values.length)
      return '<svg width="' + w + '" height="' + h + '"></svg>';
    const nums = values.filter((v) => v != null);
    const max = nums.length ? Math.max.apply(null, nums) : 1;
    const min = nums.length ? Math.min.apply(null, nums) : 0;
    const range = max - min || 1;
    const n = values.length;
    const dx = n > 1 ? w / (n - 1) : w;
    let d = "";
    let started = false;
    let ticks = "";
    for (let i = 0; i < n; i++) {
      const v = values[i];
      const x = (i * dx).toFixed(1);
      if (v == null) {
        started = false;
        ticks +=
          '<line x1="' + x + '" y1="' + (h - 2) + '" x2="' + x + '" y2="' +
          (h - 8) + '" stroke="#EF4444" stroke-width="1.2"/>';
        continue;
      }
      const y = (h - ((v - min) / range) * (h - 4) - 2).toFixed(1);
      d += (started ? " L" : "M") + x + " " + y;
      started = true;
    }
    const down = values[values.length - 1] == null;
    return (
      '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h +
      '" preserveAspectRatio="none">' +
      '<path d="' + d + '" fill="none" stroke="' + (down ? "#94a3b8" : "#22C55E") +
      '" stroke-width="1.5" stroke-linejoin="round"/>' + ticks + "</svg>"
    );
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // ---------- данные ----------
  function flatten(data) {
    const out = [];
    (data.groups || []).forEach((g) =>
      g.devices.forEach((d) => out.push(Object.assign({}, d, { group: g.name })))
    );
    (data.ungrouped || []).forEach((d) =>
      out.push(Object.assign({}, d, { group: null }))
    );
    return out;
  }

  // ---------- вид: карточки ----------
  function applyCard(d) {
    const el = document.querySelector('.device[data-device-id="' + d.id + '"]');
    if (!el) return;
    const dot = el.querySelector('[data-role="dot"]');
    if (dot) {
      dot.className = "h-2.5 w-2.5 shrink-0 rounded-full " + statusClass(d);
      dot.title = statusTitle(d);
    }
    const lat = el.querySelector('[data-role="latency"]');
    if (lat) lat.textContent = fmtLatency(d.last_latency_ms);
    const up = el.querySelector('[data-role="uptime"]');
    if (up) up.textContent = fmtUptime(d.uptime_24h);
    const sp = el.querySelector('[data-role="spark"]');
    if (sp) sp.innerHTML = sparkSVG(d.sparkline, 80, 24);
  }

  // ---------- вид: таблица ----------
  const STATUS_RANK = (u) => (u === false ? 0 : u == null ? 1 : 2);

  function sortDevices(list) {
    const { key, dir } = state.sort;
    return list.slice().sort((a, b) => {
      let va, vb;
      if (key === "status") {
        va = STATUS_RANK(a.is_up);
        vb = STATUS_RANK(b.is_up);
      } else if (key === "latency") {
        va = a.last_latency_ms == null ? Infinity : a.last_latency_ms;
        vb = b.last_latency_ms == null ? Infinity : b.last_latency_ms;
      } else if (key === "uptime") {
        va = a.uptime_24h == null ? -1 : a.uptime_24h;
        vb = b.uptime_24h == null ? -1 : b.uptime_24h;
      } else {
        va = (a[key] || "").toString().toLowerCase();
        vb = (b[key] || "").toString().toLowerCase();
      }
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }

  function matchFilter(d) {
    if (state.zone === "__none__" && d.group) return false;
    if (state.zone && state.zone !== "__none__" && d.group !== state.zone)
      return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      const hay = (d.name + " " + d.host + " " + (d.group || "")).toLowerCase();
      if (hay.indexOf(q) === -1) return false;
    }
    return true;
  }

  function renderTable() {
    const body = document.getElementById("table-body");
    if (!body || !state.data) return;
    let list = flatten(state.data).filter(matchFilter);
    list = sortDevices(list);
    const rows = list
      .map(
        (d) =>
          '<tr class="device cursor-pointer bg-card/30 hover:bg-card/70" data-device-id="' +
          d.id + '" data-role="open-chart">' +
          '<td class="px-3 py-2"><span class="inline-block h-2.5 w-2.5 rounded-full ' +
          statusClass(d) + '" title="' + statusTitle(d) + '"></span></td>' +
          '<td class="px-3 py-2 font-medium text-slate-100">' + esc(d.name) +
          (d.enabled ? "" : ' <span class="text-xs text-slate-500">(выкл.)</span>') +
          "</td>" +
          '<td class="px-3 py-2 font-mono text-slate-300">' + esc(d.host) + "</td>" +
          '<td class="px-3 py-2 text-xs text-slate-400">' + typeLabel(d) + "</td>" +
          '<td class="px-3 py-2 text-slate-300">' + esc(d.group || "—") + "</td>" +
          '<td class="px-3 py-2 text-right font-mono tabular-nums text-slate-200">' +
          fmtLatency(d.last_latency_ms) + "</td>" +
          '<td class="px-3 py-2"><div class="h-6 w-24">' +
          sparkSVG(d.sparkline, 96, 24) + "</div></td>" +
          '<td class="px-3 py-2 text-right font-mono tabular-nums text-slate-200">' +
          fmtUptime(d.uptime_24h) + "</td>" +
          "</tr>"
      )
      .join("");
    body.innerHTML = rows;
    const empty = document.getElementById("table-empty");
    if (empty) empty.classList.toggle("hidden", list.length > 0);
  }

  // ---------- экспорт CSV (текущий фильтр + сортировка) ----------
  function csvCell(v) {
    const s = v == null ? "" : String(v);
    return /[";\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function exportCSV() {
    if (!state.data) return;
    const list = sortDevices(flatten(state.data).filter(matchFilter));
    const head = [
      "Название", "Host", "Тип", "Раздел", "Статус", "Latency (ms)",
      "Порог (ms)", "Uptime 24ч (%)", "Последняя проверка",
    ];
    const rows = [head];
    list.forEach((d) => {
      rows.push([
        d.name,
        d.host,
        typeLabel(d),
        d.group || "",
        statusTitle(d),
        d.last_latency_ms == null ? "" : Math.round(d.last_latency_ms),
        d.latency_threshold || "",
        d.uptime_24h == null ? "" : d.uptime_24h,
        d.last_checked ? new Date(d.last_checked).toLocaleString() : "",
      ]);
    });
    // BOM + «;» — корректно открывается в Excel с кириллицей
    const csv =
      "﻿" + rows.map((r) => r.map(csvCell).join(";")).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const dt = new Date();
    const pad = (x) => String(x).padStart(2, "0");
    a.href = url;
    a.download =
      "devices_" + dt.getFullYear() + "-" + pad(dt.getMonth() + 1) + "-" +
      pad(dt.getDate()) + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ---------- переключение вида ----------
  function setView(view) {
    state.view = view;
    localStorage.setItem("dash_view", view);
    document.getElementById("card-view").classList.toggle("hidden", view !== "cards");
    document.getElementById("table-view").classList.toggle("hidden", view !== "table");
    document.getElementById("table-controls").classList.toggle("hidden", view !== "table");
    document.querySelectorAll(".view-btn").forEach((b) => {
      const active = b.dataset.view === view;
      b.classList.toggle("bg-ok", active);
      b.classList.toggle("text-slate-900", active);
      b.classList.toggle("text-slate-300", !active);
    });
    if (view === "table") renderTable();
  }

  // ---------- график latency (Chart.js) ----------
  let chartInstance = null;
  let currentDeviceId = null;

  function fmtTimeLabel(iso, hours) {
    const d = new Date(iso);
    const p = (x) => String(x).padStart(2, "0");
    const hm = p(d.getHours()) + ":" + p(d.getMinutes());
    return hours > 48 ? p(d.getDate()) + "." + p(d.getMonth() + 1) + " " + hm : hm;
  }

  async function loadChart(id, hours) {
    const modalCanvas = document.getElementById("lat-chart");
    const emptyEl = document.getElementById("chart-empty");
    try {
      const resp = await fetch(
        "/api/device/" + id + "/history?hours=" + hours,
        { cache: "no-store" }
      );
      if (!resp.ok) return;
      const data = await resp.json();
      setText("chart-title", data.name);
      setText("chart-sub", data.host + " · последние " + hours + " ч");
      const labels = data.points.map((p) => fmtTimeLabel(p.t, hours));
      const values = data.points.map((p) => p.latency);
      const hasData = values.some((v) => v != null);
      emptyEl.classList.toggle("hidden", hasData);
      modalCanvas.classList.toggle("hidden", !hasData);
      if (chartInstance) chartInstance.destroy();
      if (!hasData) return;
      chartInstance = new Chart(modalCanvas.getContext("2d"), {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "latency, ms",
              data: values,
              borderColor: "#22C55E",
              backgroundColor: "rgba(34,197,94,0.12)",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.25,
              fill: true,
              spanGaps: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (c) =>
                  c.parsed.y == null ? "недоступно" : Math.round(c.parsed.y) + " ms",
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "#94a3b8", maxTicksLimit: 8, maxRotation: 0 },
              grid: { color: "rgba(51,65,85,0.4)" },
            },
            y: {
              beginAtZero: true,
              title: { display: true, text: "ms", color: "#94a3b8" },
              ticks: { color: "#94a3b8" },
              grid: { color: "rgba(51,65,85,0.4)" },
            },
          },
        },
      });
    } catch (e) {
      /* пропускаем */
    }
  }

  function openChart(id) {
    currentDeviceId = id;
    const modal = document.getElementById("chart-modal");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    const hours = parseInt(document.getElementById("chart-range").value, 10) || 24;
    loadChart(id, hours);
  }

  function closeChart() {
    const modal = document.getElementById("chart-modal");
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
    currentDeviceId = null;
  }

  // ---------- опрос ----------
  async function refresh() {
    try {
      const resp = await fetch("/api/status", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      state.data = data;
      setText("sum-total", data.total);
      setText("sum-online", data.online);
      setText("sum-offline", data.offline);
      flatten(data).forEach(applyCard);
      if (state.view === "table") renderTable();
      setText("updated", new Date(data.generated_at).toLocaleTimeString());
    } catch (e) {
      /* сеть недоступна — тихо пропускаем тик */
    }
  }

  // ---------- события ----------
  function init() {
    document.querySelectorAll(".view-btn").forEach((b) =>
      b.addEventListener("click", () => setView(b.dataset.view))
    );
    const search = document.getElementById("search");
    if (search)
      search.addEventListener("input", (e) => {
        state.search = e.target.value.trim();
        renderTable();
      });
    const zone = document.getElementById("zone-filter");
    if (zone)
      zone.addEventListener("change", (e) => {
        state.zone = e.target.value;
        renderTable();
      });
    const csvBtn = document.getElementById("export-csv");
    if (csvBtn) csvBtn.addEventListener("click", exportCSV);
    document.querySelectorAll("th[data-sort]").forEach((th) =>
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (state.sort.key === key) state.sort.dir *= -1;
        else state.sort = { key: key, dir: 1 };
        renderTable();
      })
    );
    // открытие графика по клику на строку/карточку (делегирование)
    document.addEventListener("click", (e) => {
      const el = e.target.closest('[data-role="open-chart"]');
      if (el && el.dataset.deviceId) openChart(parseInt(el.dataset.deviceId, 10));
    });
    document.getElementById("chart-close").addEventListener("click", closeChart);
    document.getElementById("chart-modal").addEventListener("click", (e) => {
      if (e.target.id === "chart-modal") closeChart();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeChart();
    });
    document.getElementById("chart-range").addEventListener("change", (e) => {
      if (currentDeviceId != null)
        loadChart(currentDeviceId, parseInt(e.target.value, 10) || 24);
    });

    setView(state.view);
    refresh();
    setInterval(refresh, REFRESH_MS);
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else init();
})();
