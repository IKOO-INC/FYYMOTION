// Text FX — animasi teks per huruf/kata: wizard 4 langkah + preview + export XML.
(function () {
  "use strict";

  var STYLES = window.TF_STYLES || [];
  var MODES = window.TF_MODES || {};
  var MAPPINGS = window.TF_MAPPINGS || {};
  var FONTS = window.TF_FONTS || {};
  var CANVAS = window.TF_CANVAS || {};
  var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  var FONT_STACK = {
    inter: '"Inter", -apple-system, sans-serif',
    roboto: '"Roboto", -apple-system, sans-serif',
    open_sans: '"Open Sans", -apple-system, sans-serif',
    montserrat: '"Montserrat", -apple-system, sans-serif',
    poppins: '"Poppins", -apple-system, sans-serif',
  };

  var STYLE_MAP = {};
  STYLES.forEach(function (s) { STYLE_MAP[s.id] = s; });

  var state = {
    styleId: STYLES.length ? STYLES[0].id : null,
    text: "FYY MOTION",
    mode: "character",
    fontSize: 90,
    fontId: "inter",
    weight: 700,
    canvasId: "portrait",
    staggerMs: 80,
    durationMs: 1100,
    randomPct: 60,
    seed: 7,
    extendToEnd: true,
    colors: ["#ff5a5f", "#2ecc71", "#5b8def"],
    mapping: "cycle",
  };
  var lastXml = null;
  var lastFilename = null;

  // ------------------------------------------------------------------ //
  // Seeded RNG (deterministic preview, mirrors seed-based feel of backend)
  // ------------------------------------------------------------------ //
  function makeRng(seed) {
    var s = (Number(seed) || 0) % 2147483647;
    if (s <= 0) s += 2147483646;
    return function () {
      s = (s * 16807) % 2147483647;
      return (s - 1) / 2147483646;
    };
  }

  // ------------------------------------------------------------------ //
  // Step navigation
  // ------------------------------------------------------------------ //
  function goToStep(n) {
    document.querySelectorAll(".tc-panel").forEach(function (panel) {
      panel.classList.toggle("active", Number(panel.dataset.panel) === n);
    });
    document.querySelectorAll(".tc-step-pill").forEach(function (pill) {
      var step = Number(pill.dataset.step);
      pill.classList.toggle("active", step === n);
      pill.classList.toggle("done", step < n);
    });
    if (n === 3) renderPreview();
    if (n === 4) renderSummary();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ //
  // STEP 1 — kartu preset animasi
  // ------------------------------------------------------------------ //
  function renderStyleCards() {
    var grid = document.getElementById("tfStyleGrid");
    grid.innerHTML = "";
    STYLES.forEach(function (style) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "tc-preset-card" + (style.id === state.styleId ? " selected" : "");
      card.innerHTML =
        '<div class="tc-preset-icon"><i class="' + style.icon + '"></i></div>' +
        "<h3>" + escapeHtml(style.name) + "</h3>" +
        "<p>" + escapeHtml(style.description) + "</p>" +
        (style.supports_random ? '<span class="tc-preset-demo"><i class="fa-solid fa-dice"></i> Punya opsi Random</span>' : "");
      card.addEventListener("click", function () {
        document.querySelectorAll(".tc-preset-card").forEach(function (c) { c.classList.remove("selected"); });
        card.classList.add("selected");
        state.styleId = style.id;
        document.getElementById("tfNext1").disabled = false;
        toggleRandomRow();
      });
      grid.appendChild(card);
    });
  }

  function toggleRandomRow() {
    var style = STYLE_MAP[state.styleId];
    var row = document.getElementById("tfRandomRow");
    row.style.display = style && style.supports_random ? "grid" : "none";
  }

  // ------------------------------------------------------------------ //
  // STEP 2 — teks, mode, font, warna, timing
  // ------------------------------------------------------------------ //
  function renderFontOptions() {
    var sel = document.getElementById("tfFont");
    sel.innerHTML = "";
    Object.keys(FONTS).forEach(function (id) {
      var opt = document.createElement("option");
      opt.value = id;
      opt.textContent = FONTS[id].label;
      if (id === state.fontId) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function renderCanvasOptions() {
    var sel = document.getElementById("tfCanvas");
    sel.innerHTML = "";
    Object.keys(CANVAS).forEach(function (id) {
      var opt = document.createElement("option");
      opt.value = id;
      opt.textContent = CANVAS[id].label;
      if (id === state.canvasId) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function bindModeToggle() {
    var wrap = document.getElementById("tfModeToggle");
    wrap.querySelectorAll(".tf-mode-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        wrap.querySelectorAll(".tf-mode-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        state.mode = btn.dataset.mode;
      });
    });
  }

  function renderColorList() {
    var wrap = document.getElementById("tfColorList");
    wrap.innerHTML = "";
    state.colors.forEach(function (color, idx) {
      var chip = document.createElement("div");
      chip.className = "tf-color-chip";
      var input = document.createElement("input");
      input.type = "color";
      input.value = color;
      input.addEventListener("input", function () { state.colors[idx] = input.value; });
      chip.appendChild(input);
      if (state.colors.length > 1) {
        var removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "tf-color-remove";
        removeBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        removeBtn.addEventListener("click", function () {
          state.colors.splice(idx, 1);
          renderColorList();
        });
        chip.appendChild(removeBtn);
      }
      wrap.appendChild(chip);
    });
  }

  function bindFormFields() {
    document.getElementById("tfText").addEventListener("input", function (e) { state.text = e.target.value; });
    document.getElementById("tfFontSize").addEventListener("input", function (e) { state.fontSize = Number(e.target.value) || 90; });
    document.getElementById("tfFont").addEventListener("change", function (e) { state.fontId = e.target.value; });
    document.getElementById("tfWeight").addEventListener("change", function (e) { state.weight = Number(e.target.value); });
    document.getElementById("tfCanvas").addEventListener("change", function (e) { state.canvasId = e.target.value; });
    document.getElementById("tfStagger").addEventListener("input", function (e) { state.staggerMs = Number(e.target.value) || 0; });
    document.getElementById("tfDuration").addEventListener("input", function (e) { state.durationMs = Number(e.target.value) || 1100; });
    document.getElementById("tfSeed").addEventListener("input", function (e) { state.seed = Number(e.target.value) || 0; });
    document.getElementById("tfExtendToEnd").addEventListener("change", function (e) { state.extendToEnd = e.target.checked; });
    document.getElementById("tfMapping").addEventListener("change", function (e) { state.mapping = e.target.value; });
    var randomSlider = document.getElementById("tfRandomPct");
    randomSlider.addEventListener("input", function (e) {
      state.randomPct = Number(e.target.value) || 0;
      document.getElementById("tfRandomPctLabel").textContent = state.randomPct;
    });
    document.getElementById("tfAddColor").addEventListener("click", function () {
      if (state.colors.length >= 6) { alert("Maksimal 6 warna dalam satu palet."); return; }
      state.colors.push("#ffffff");
      renderColorList();
    });
  }

  // ------------------------------------------------------------------ //
  // Unit splitting + color mapping (mirror backend _pick_color logic)
  // ------------------------------------------------------------------ //
  function getUnits() {
    var text = state.text.replace(/\s+/g, " ").trim();
    if (!text) return [];
    if (state.mode === "character") {
      return text.split("").filter(function (c) { return c !== " "; });
    }
    return text.split(" ").filter(Boolean);
  }

  function pickColor(idx, n) {
    var colors = state.colors;
    if (colors.length === 1 || state.mapping === "single") return colors[0];
    if (state.mapping === "mirror" && colors.length > 1) {
      var period = (colors.length - 1) * 2;
      var pos = period ? idx % period : 0;
      if (pos >= colors.length) pos = period - pos;
      return colors[pos];
    }
    return colors[idx % colors.length];
  }

  // ------------------------------------------------------------------ //
  // STEP 3 — preview (simulasi Web Animations API, bukan render AM asli)
  // ------------------------------------------------------------------ //
  function buildKeyframes(styleId, rng) {
    var dx = (rng() - 0.5) * 2 * (state.randomPct || 0) * 1.4;
    var dy = (rng() - 0.5) * 2 * (state.randomPct || 0) * 1.4;
    switch (styleId) {
      case "pop":
        return { frames: [
          { opacity: 0, transform: "scale(0)" },
          { opacity: 1, transform: "scale(1)" },
        ], easing: "cubic-bezier(.34,1.56,.64,1)", fadeOnly: false };
      case "blur":
        return { frames: [
          { opacity: 0, filter: "blur(10px)" },
          { opacity: 1, filter: "blur(0px)" },
        ], easing: "cubic-bezier(0,0,.04,1)" };
      case "blur_up":
        return { frames: [
          { opacity: 0, filter: "blur(5px)", transform: "translateY(26px)" },
          { opacity: 1, filter: "blur(0px)", transform: "translateY(0)" },
        ], easing: "cubic-bezier(0,0,.16,1)" };
      case "bounce_move":
        return { frames: [
          { opacity: 0, transform: "translateX(-40px) scale(0)" },
          { opacity: 1, transform: "translateX(0) scale(1)" },
        ], easing: "cubic-bezier(.33,1.4,.16,.9)" };
      case "random_in":
        return { frames: [
          { opacity: 0, transform: "translate(" + dx + "px," + dy + "px)" },
          { opacity: 1, transform: "translate(0,0)" },
        ], easing: "cubic-bezier(.42,0,.15,1)" };
      case "random_in_out":
        return { frames: [
          { opacity: 0, transform: "translate(" + dx + "px," + dy + "px)" },
          { opacity: 1, transform: "translate(0,0)", offset: 0.5 },
          { opacity: 0, transform: "translate(" + (-dx) + "px," + (-dy) + "px)" },
        ], easing: "cubic-bezier(.42,0,.15,1)" };
      case "squish_up":
        return { frames: [
          { opacity: 0, transform: "translateY(34px) scale(0) rotate(-46deg)" },
          { opacity: 1, transform: "translateY(0) scale(1) rotate(0deg)" },
        ], easing: "cubic-bezier(.17,1.3,0,1)" };
      case "up":
        return { frames: [
          { opacity: 1, transform: "translateY(20px) scale(0) rotate(-30deg)" },
          { opacity: 1, transform: "translateY(0) scale(1) rotate(0deg)" },
        ], easing: "cubic-bezier(.17,1.3,0,1)" };
      case "elastic":
        return { frames: [
          { opacity: 1, transform: "translateY(18px) scale(0) rotate(28deg)" },
          { opacity: 1, transform: "translateY(0) scale(1) rotate(0deg)" },
        ], easing: "cubic-bezier(.2,1.4,.1,1)" };
      case "squish_rot":
        return { frames: [
          { opacity: 0, transform: "translateY(34px) scale(0) rotate(52deg)" },
          { opacity: 1, transform: "translateY(0) scale(1) rotate(0deg)" },
        ], easing: "cubic-bezier(.17,1.3,0,1)" };
      case "stretch_half":
        return { frames: [
          { opacity: 0, transform: "translateY(20px) scaleY(0)" },
          { opacity: 1, transform: "translateY(0) scaleY(2.1)", offset: 0.35 },
          { opacity: 1, transform: "translateY(0) scaleY(1)", offset: 0.55 },
          { opacity: 1, transform: "translateY(0) scaleY(0.9)", offset: 0.75 },
          { opacity: 1, transform: "translateY(0) scaleY(1)" },
        ], easing: "cubic-bezier(0,0,.16,1)" };
      default:
        return { frames: [
          { opacity: 0 },
          { opacity: 1 },
        ], easing: "ease-out" };
    }
  }

  function renderPreview() {
    var el = document.getElementById("tfPreviewText");
    if (!el) return;
    el.innerHTML = "";
    el.style.fontFamily = FONT_STACK[state.fontId] || FONT_STACK.inter;
    el.style.fontWeight = state.weight;
    el.style.fontSize = Math.max(16, Math.min(state.fontSize, 56)) + "px";

    var units = getUnits();
    if (!units.length) return;
    var n = units.length;
    var style = STYLE_MAP[state.styleId] || STYLES[0];
    var rng = makeRng(state.seed);
    var durationMs = Math.max(150, state.durationMs);

    units.forEach(function (unit, idx) {
      var span = document.createElement("span");
      span.className = "tf-unit";
      span.textContent = state.mode === "word" ? unit + (idx < n - 1 ? "\u00a0" : "") : unit;
      span.style.color = pickColor(idx, n);
      span.style.opacity = "0";
      el.appendChild(span);

      var kf = buildKeyframes(style.id, rng);
      var delay = idx * Math.max(0, state.staggerMs);
      try {
        span.animate(kf.frames, {
          duration: durationMs,
          delay: delay,
          easing: kf.easing || "ease-out",
          fill: "forwards",
        });
      } catch (e) {
        span.style.opacity = "1";
      }
    });
  }

  // ------------------------------------------------------------------ //
  // STEP 4 — ringkasan + generate/export XML
  // ------------------------------------------------------------------ //
  function renderSummary() {
    var box = document.getElementById("tfSummary");
    var style = STYLE_MAP[state.styleId] || {};
    box.innerHTML =
      "<dl>" +
      "<dt>Animasi</dt><dd>" + escapeHtml(style.name || "-") + "</dd>" +
      "<dt>Teks</dt><dd>" + escapeHtml(state.text) + "</dd>" +
      "<dt>Mode</dt><dd>" + (MODES[state.mode] || state.mode) + "</dd>" +
      "<dt>Font</dt><dd>" + (FONTS[state.fontId] || {}).label + ", weight " + state.weight + "</dd>" +
      "<dt>Ukuran</dt><dd>" + state.fontSize + " px</dd>" +
      "<dt>Kanvas</dt><dd>" + (CANVAS[state.canvasId] || {}).label + "</dd>" +
      "<dt>Jeda antar unit</dt><dd>" + state.staggerMs + " ms</dd>" +
      "<dt>Lama tampil</dt><dd>" + state.durationMs + " ms</dd>" +
      (style.supports_random ? "<dt>Random</dt><dd>" + state.randomPct + "%, seed " + state.seed + "</dd>" : "") +
      "<dt>Palet warna</dt><dd>" + state.colors.join(", ") + " (" + (MAPPINGS[state.mapping] || state.mapping) + ")</dd>" +
      "</dl>";
  }

  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s == null ? "" : s;
    return div.innerHTML;
  }

  function buildPayload() {
    return {
      style_id: state.styleId,
      text: state.text,
      mode: state.mode,
      font_size: state.fontSize,
      font_id: state.fontId,
      font_weight: state.weight,
      canvas_id: state.canvasId,
      stagger_ms: state.staggerMs,
      layer_duration_ms: state.durationMs,
      random_pct: state.randomPct,
      seed: state.seed,
      extend_to_end: state.extendToEnd,
      colors: state.colors,
      color_mapping: state.mapping,
    };
  }

  function showResult(ok, message) {
    var box = document.getElementById("tfResult");
    box.className = "tc-result " + (ok ? "ok" : "err");
    box.innerHTML = (ok ? '<i class="fa-solid fa-circle-check"></i> ' : '<i class="fa-solid fa-triangle-exclamation"></i> ') + message;
  }

  function generateXml(action) {
    fetch("/api/tools/text-fx/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify(buildPayload()),
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().catch(function () { return { error: "Gagal membuat XML." }; }).then(function (data) {
            throw new Error(data.error || "Gagal membuat XML.");
          });
        }
        var disposition = resp.headers.get("Content-Disposition") || "";
        var match = disposition.match(/filename="([^"]+)"/);
        lastFilename = match ? match[1] : "fyymotion-textfx.xml";
        return resp.text();
      })
      .then(function (text) {
        lastXml = text;
        if (action === "download") {
          var blob = new Blob([text], { type: "application/xml" });
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url;
          a.download = lastFilename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
          showResult(true, "File " + lastFilename + " berhasil diunduh.");
        } else {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard
              .writeText(text)
              .then(function () { showResult(true, "XML berhasil disalin ke clipboard."); })
              .catch(function () { showResult(false, "Browser menolak akses clipboard. Silakan gunakan Export XML untuk mengunduh file."); });
          } else {
            showResult(false, "Clipboard tidak didukung browser ini. Silakan gunakan Export XML untuk mengunduh file.");
          }
        }
      })
      .catch(function (err) {
        showResult(false, err.message || "Gagal membuat XML.");
      });
  }

  // ------------------------------------------------------------------ //
  // Navigasi — drawer mobile
  // ------------------------------------------------------------------ //
  function bindMobileDrawer() {
    var btn = document.getElementById("tfDrawerBtn");
    var drawer = document.getElementById("tfDrawer");
    var backdrop = document.getElementById("tfDrawerBackdrop");
    var closeBtn = document.getElementById("tfDrawerClose");
    if (!btn || !drawer || !backdrop) return;

    function openDrawer() {
      drawer.classList.add("show");
      backdrop.classList.add("show");
      drawer.setAttribute("aria-hidden", "false");
      btn.setAttribute("aria-expanded", "true");
      document.body.style.overflow = "hidden";
    }
    function closeDrawer() {
      drawer.classList.remove("show");
      backdrop.classList.remove("show");
      drawer.setAttribute("aria-hidden", "true");
      btn.setAttribute("aria-expanded", "false");
      document.body.style.overflow = "";
    }

    btn.addEventListener("click", openDrawer);
    backdrop.addEventListener("click", closeDrawer);
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    drawer.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", closeDrawer); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && drawer.classList.contains("show")) closeDrawer();
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 991 && drawer.classList.contains("show")) closeDrawer();
    });
  }

  // ------------------------------------------------------------------ //
  // Init
  // ------------------------------------------------------------------ //
  document.addEventListener("DOMContentLoaded", function () {
    bindMobileDrawer();
    renderStyleCards();
    toggleRandomRow();
    renderFontOptions();
    renderCanvasOptions();
    bindModeToggle();
    renderColorList();
    bindFormFields();

    document.getElementById("tfNext1").addEventListener("click", function () { goToStep(2); });
    document.getElementById("tfBack2").addEventListener("click", function () { goToStep(1); });
    document.getElementById("tfNext2").addEventListener("click", function () {
      if (!state.text.trim()) { alert("Teks tidak boleh kosong."); return; }
      goToStep(3);
    });
    document.getElementById("tfBack3").addEventListener("click", function () { goToStep(2); });
    document.getElementById("tfNext3").addEventListener("click", function () { goToStep(4); });
    document.getElementById("tfBack4").addEventListener("click", function () { goToStep(3); });
    document.getElementById("tfReplay").addEventListener("click", renderPreview);
    document.getElementById("tfExportBtn").addEventListener("click", function () { generateXml("download"); });
    document.getElementById("tfCopyBtn").addEventListener("click", function () { generateXml("copy"); });
  });
})();
