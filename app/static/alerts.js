// Визуальные алерты в браузере (для изолированной сети без интернета).
// Полностью клиентские: тосты при смене статуса + счётчик в заголовке вкладки +
// красная точка на фавиконе. Без внешних зависимостей. Используется дашбордом и NOC.
window.createAlertCenter = function (opts) {
  opts = opts || {};
  var storageKey = opts.storageKey || "alerts_enabled";
  var baseTitle = opts.baseTitle || document.title;
  var prev = null; // Map<id, {st, name, host}>
  var enabled = localStorage.getItem(storageKey) !== "0"; // по умолчанию вкл.

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function container() {
    var c = document.getElementById("toast-container");
    if (!c) {
      c = document.createElement("div");
      c.id = "toast-container";
      c.className =
        "fixed top-4 right-4 z-[60] flex w-80 max-w-[90vw] flex-col gap-2";
      document.body.appendChild(c);
    }
    return c;
  }

  function toast(kind, text, sticky) {
    if (!enabled) return;
    var colors = {
      bad: "border-bad/50 bg-bad/20 text-bad",
      warn: "border-warn/50 bg-warn/20 text-warn",
      ok: "border-ok/50 bg-ok/20 text-ok",
    };
    var el = document.createElement("div");
    el.className =
      "flex items-start justify-between gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-lg backdrop-blur " +
      (colors[kind] || colors.bad);
    el.setAttribute("role", "alert");
    var span = document.createElement("span");
    span.innerHTML = text;
    var btn = document.createElement("button");
    btn.className = "shrink-0 opacity-70 hover:opacity-100";
    btn.setAttribute("aria-label", "Закрыть");
    btn.textContent = "✕";
    btn.onclick = function () {
      el.remove();
    };
    el.appendChild(span);
    el.appendChild(btn);
    container().appendChild(el);
    if (!sticky) setTimeout(function () { el.remove(); }, 10000);
  }

  function setFavicon(alarm) {
    try {
      var c = document.createElement("canvas");
      c.width = 32;
      c.height = 32;
      var ctx = c.getContext("2d");
      // фон + «пульс» (как в шапке)
      ctx.fillStyle = "#0F172A";
      ctx.fillRect(0, 0, 32, 32);
      ctx.strokeStyle = "#22C55E";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(3, 18);
      ctx.lineTo(10, 18);
      ctx.lineTo(14, 28);
      ctx.lineTo(20, 6);
      ctx.lineTo(24, 18);
      ctx.lineTo(29, 18);
      ctx.stroke();
      if (alarm) {
        ctx.fillStyle = "#EF4444";
        ctx.beginPath();
        ctx.arc(24, 8, 7, 0, 2 * Math.PI);
        ctx.fill();
      }
      var link = document.querySelector("link[rel='icon']");
      if (!link) {
        link = document.createElement("link");
        link.rel = "icon";
        document.head.appendChild(link);
      }
      link.href = c.toDataURL("image/png");
    } catch (e) {
      /* canvas недоступен — пропускаем */
    }
  }

  function setTitle(offline) {
    document.title =
      enabled && offline > 0 ? "(" + offline + ") ⚠ " + baseTitle : baseTitle;
  }

  function statusOf(d) {
    if (d.is_up === false) return "down";
    if (d.is_up == null) return "unknown";
    return d.is_slow ? "slow" : "ok";
  }

  function process(devices) {
    var cur = new Map();
    var offline = 0;
    devices.forEach(function (d) {
      cur.set(d.id, { st: statusOf(d), name: d.name, host: d.host });
      if (d.is_up === false) offline++;
    });
    if (prev !== null && enabled) {
      cur.forEach(function (v, id) {
        var p = prev.get(id);
        if (!p || p.st === v.st) return;
        if (v.st === "down")
          toast("bad", "🔴 <b>" + esc(v.name) + "</b> (" + esc(v.host) + ") недоступно", true);
        else if (v.st === "slow")
          toast("warn", "🟡 <b>" + esc(v.name) + "</b> — медленный отклик", false);
        else if (v.st === "ok" && (p.st === "down" || p.st === "slow"))
          toast("ok", "🟢 <b>" + esc(v.name) + "</b> восстановлено", false);
      });
    }
    prev = cur; // обновляем снимок всегда (чтобы при включении не было лавины)
    setTitle(offline);
    setFavicon(enabled && offline > 0);
  }

  function setEnabled(v) {
    enabled = !!v;
    localStorage.setItem(storageKey, v ? "1" : "0");
    if (!v) {
      setTitle(0);
      setFavicon(false);
    }
  }

  function isEnabled() {
    return enabled;
  }

  return { process: process, setEnabled: setEnabled, isEnabled: isEnabled };
};
