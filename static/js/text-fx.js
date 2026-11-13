// Text FX — animasi teks per huruf/kata: wizard 4 langkah + preview + export XML.
(function () {
  "use strict";

  var STYLES = window.TF_STYLES || [];
  var MODES = window.TF_MODES || {};
  var MAPPINGS = window.TF_MAPPINGS || {};
  var FONTS = window.TF_FONTS || {};
  var CANVAS = window.TF_CANVAS || {};
  var CURVES = window.TF_CURVES || {};
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
    curve: null,
    curveId: "",
  };
  (function initCurveState() {
    var style = STYLE_MAP[state.styleId];
    if (style && style.supports_curve_edit && style.default_curve) {
      state.curve = Object.assign({}, style.default_curve);
    }
  })();
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
    if (n === 2) updateCurveSectionVisibility();
    if (n === 3) { renderPreview(); renderLayerPanel(); }
    if (n === 4) renderSummary();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ //
  // STEP 1 — kartu preset animasi (+ preview mini auto-play & loop)
  // ------------------------------------------------------------------ //
  var DEMO_UNITS = ["F", "Y", "Y"];
  var demoTimers = {};

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
        (style.supports_random ? '<span class="tc-preset-demo"><i class="fa-solid fa-dice"></i> Punya opsi Random</span>' : "") +
        '<div class="tf-card-demo" id="tfDemo-' + style.id + '"></div>';
      card.addEventListener("click", function () {
        document.querySelectorAll(".tc-preset-card").forEach(function (c) { c.classList.remove("selected"); });
        card.classList.add("selected");
        state.styleId = style.id;
        if (style.supports_curve_edit && style.default_curve) {
          state.curve = Object.assign({}, style.default_curve);
          state.curveId = "";
        } else {
          state.curve = null;
          state.curveId = "";
        }
        document.getElementById("tfNext1").disabled = false;
        toggleRandomRow();
      });
      grid.appendChild(card);
      startCardDemoLoop(style.id);
    });
  }

  function playCardDemo(styleId) {
    var container = document.getElementById("tfDemo-" + styleId);
    if (!container) return;
    container.innerHTML = "";
    var style = STYLE_MAP[styleId] || {};
    var rng = makeRng(3);
    var staggerMs = 90;
    var durationMs = 620;
    DEMO_UNITS.forEach(function (ch, idx) {
      var span = document.createElement("span");
      span.className = "tf-unit";
      span.textContent = ch;
      span.style.opacity = "0";
      container.appendChild(span);
      var kf = buildKeyframes(styleId, rng, style.default_curve, 70);
      try {
        span.animate(kf.frames, {
          duration: durationMs,
          delay: idx * staggerMs,
          easing: kf.easing || "ease-out",
          fill: "forwards",
        });
      } catch (e) { span.style.opacity = "1"; }
    });
  }

  function startCardDemoLoop(styleId) {
    if (demoTimers[styleId]) { clearTimeout(demoTimers[styleId]); }
    var cycleMs = 620 + (DEMO_UNITS.length - 1) * 90 + 900; // mainkan + jeda sebelum ulang
    function loop() {
      playCardDemo(styleId);
      demoTimers[styleId] = setTimeout(loop, cycleMs);
    }
    loop();
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
  // Curve editor (SVG, dua handle draggable) — hanya untuk preset yang
  // kurva utamanya cubicBezier tunggal (lihat style.supports_curve_edit).
  // ------------------------------------------------------------------ //
  var SVG_SIZE = 260;
  var PAD = 24;
  var INNER = SVG_SIZE - PAD * 2;
  var Y_MIN = -0.7, Y_MAX = 1.7;
  var curveSvgBuilt = false;

  function dataToPixelX(x) { return PAD + x * INNER; }
  function dataToPixelY(y) {
    var norm = (y - Y_MIN) / (Y_MAX - Y_MIN);
    return PAD + (1 - norm) * INNER;
  }
  function pixelToDataX(px) { return Math.min(1, Math.max(0, (px - PAD) / INNER)); }
  function pixelToDataY(py) {
    var norm = 1 - (py - PAD) / INNER;
    return Math.min(Y_MAX, Math.max(Y_MIN, Y_MIN + norm * (Y_MAX - Y_MIN)));
  }

  function buildCurveSvg() {
    var svg = document.getElementById("tfCurveSvg");
    if (!svg || curveSvgBuilt) return;
    curveSvgBuilt = true;
    svg.setAttribute("width", SVG_SIZE);
    svg.setAttribute("height", SVG_SIZE);
    svg.innerHTML =
      '<rect x="0" y="0" width="' + SVG_SIZE + '" height="' + SVG_SIZE + '" rx="16" fill="#0b0b0d"></rect>' +
      '<line id="tfLine0" stroke="#4b4b50" stroke-width="1.5"></line>' +
      '<line id="tfLine1" stroke="#4b4b50" stroke-width="1.5"></line>' +
      '<path id="tfCurvePath" fill="none" stroke="#0a84ff" stroke-width="3"></path>' +
      '<circle id="tfAnchorStart" r="4" fill="#8e8e93"></circle>' +
      '<circle id="tfAnchorEnd" r="4" fill="#8e8e93"></circle>' +
      '<circle id="tfHandle1" r="8" fill="#ff9f0a" style="cursor:grab"></circle>' +
      '<circle id="tfHandle2" r="8" fill="#0a84ff" style="cursor:grab"></circle>';
    bindHandleDrag(document.getElementById("tfHandle1"), function (x, y) { state.curve.x1 = x; state.curve.y1 = y; });
    bindHandleDrag(document.getElementById("tfHandle2"), function (x, y) { state.curve.x2 = x; state.curve.y2 = y; });
  }

  function bindHandleDrag(handle, onMove) {
    handle.addEventListener("pointerdown", function (ev) {
      handle.setPointerCapture(ev.pointerId);
      handle.style.cursor = "grabbing";
      function move(e) {
        var svg = document.getElementById("tfCurveSvg");
        var rect = svg.getBoundingClientRect();
        var scale = SVG_SIZE / rect.width;
        var px = (e.clientX - rect.left) * scale;
        var py = (e.clientY - rect.top) * scale;
        var x = Math.round(pixelToDataX(px) * 100) / 100;
        var y = Math.round(pixelToDataY(py) * 100) / 100;
        if (!state.curve) return;
        onMove(x, y);
        state.curveId = "";
        updateCurvePresetChips();
        syncCurveInputs();
        drawCurve();
        renderPreview();
      }
      function up() {
        handle.style.cursor = "grab";
        handle.releasePointerCapture(ev.pointerId);
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
      }
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
  }

  function drawCurve() {
    if (!state.curve) return;
    var x0 = dataToPixelX(0), y0 = dataToPixelY(0);
    var x3 = dataToPixelX(1), y3 = dataToPixelY(1);
    var x1 = dataToPixelX(state.curve.x1), y1 = dataToPixelY(state.curve.y1);
    var x2 = dataToPixelX(state.curve.x2), y2 = dataToPixelY(state.curve.y2);

    setAttrs("tfLine0", { x1: x0, y1: y0, x2: x1, y2: y1 });
    setAttrs("tfLine1", { x1: x3, y1: y3, x2: x2, y2: y2 });
    var path = document.getElementById("tfCurvePath");
    if (path) path.setAttribute("d", "M " + x0 + " " + y0 + " C " + x1 + " " + y1 + ", " + x2 + " " + y2 + ", " + x3 + " " + y3);
    setAttrs("tfAnchorStart", { cx: x0, cy: y0 });
    setAttrs("tfAnchorEnd", { cx: x3, cy: y3 });
    setAttrs("tfHandle1", { cx: x1, cy: y1 });
    setAttrs("tfHandle2", { cx: x2, cy: y2 });
  }

  function setAttrs(id, attrs) {
    var el = document.getElementById(id);
    if (!el) return;
    Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
  }

  function renderCurvePresetChips() {
    var wrap = document.getElementById("tfCurvePresets");
    if (!wrap) return;
    wrap.innerHTML = "";
    Object.keys(CURVES).forEach(function (id) {
      var curve = CURVES[id];
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "tc-chip";
      chip.dataset.curveId = id;
      chip.textContent = curve.label;
      chip.addEventListener("click", function () {
        state.curveId = id;
        state.curve = { x1: curve.x1, y1: curve.y1, x2: curve.x2, y2: curve.y2 };
        updateCurvePresetChips();
        syncCurveInputs();
        drawCurve();
        renderPreview();
      });
      wrap.appendChild(chip);
    });
    updateCurvePresetChips();
  }

  function updateCurvePresetChips() {
    document.querySelectorAll("#tfCurvePresets .tc-chip").forEach(function (chip) {
      chip.classList.toggle("active", chip.dataset.curveId === state.curveId);
    });
  }

  function syncCurveInputs() {
    if (!state.curve) return;
    document.getElementById("tfCurveX1").value = state.curve.x1;
    document.getElementById("tfCurveY1").value = state.curve.y1;
    document.getElementById("tfCurveX2").value = state.curve.x2;
    document.getElementById("tfCurveY2").value = state.curve.y2;
  }

  function bindCurveInputs() {
    function bind(id, key, isX) {
      document.getElementById(id).addEventListener("change", function (e) {
        if (!state.curve) return;
        var v = parseFloat(e.target.value);
        if (isNaN(v)) return;
        if (isX) v = Math.min(1, Math.max(0, v));
        else v = Math.min(3, Math.max(-2, v));
        state.curve[key] = v;
        state.curveId = "";
        updateCurvePresetChips();
        drawCurve();
        renderPreview();
      });
    }
    bind("tfCurveX1", "x1", true);
    bind("tfCurveY1", "y1", false);
    bind("tfCurveX2", "x2", true);
    bind("tfCurveY2", "y2", false);

    var resetBtn = document.getElementById("tfCurveReset");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        var style = STYLE_MAP[state.styleId];
        if (!style || !style.default_curve) return;
        state.curve = Object.assign({}, style.default_curve);
        state.curveId = "";
        updateCurvePresetChips();
        syncCurveInputs();
        drawCurve();
        renderPreview();
      });
    }
  }

  function updateCurveSectionVisibility() {
    var style = STYLE_MAP[state.styleId];
    var supports = !!(style && style.supports_curve_edit);
    var wrap = document.getElementById("tfCurveWrap");
    var locked = document.getElementById("tfCurveLocked");
    if (wrap) wrap.style.display = supports ? "block" : "none";
    if (locked) locked.style.display = supports ? "none" : "block";
    if (supports) {
      buildCurveSvg();
      if (!state.curve && style.default_curve) state.curve = Object.assign({}, style.default_curve);
      syncCurveInputs();
      updateCurvePresetChips();
      drawCurve();
    }
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
  // Timing per unit — mencerminkan logika stagger/duration/extend_to_end
  // di backend (build_text_fx_xml), dipakai bareng oleh preview & layer panel.
  // ------------------------------------------------------------------ //
  function computeUnitTimings(units) {
    var timings = [];
    var maxEnd = 0;
    units.forEach(function (unit, idx) {
      var start = idx * Math.max(0, state.staggerMs);
      var end = start + Math.max(300, state.durationMs);
      timings.push({ start: start, end: end });
      if (end > maxEnd) maxEnd = end;
    });
    if (state.extendToEnd) {
      timings.forEach(function (t) { t.end = maxEnd; });
    }
    return { timings: timings, totalMs: maxEnd || 1 };
  }

  // ------------------------------------------------------------------ //
  // STEP 3 — preview (simulasi Web Animations API, bukan render AM asli)
  // ------------------------------------------------------------------ //
  function easingFromCurve(curve) {
    return "cubic-bezier(" + curve.x1 + "," + curve.y1 + "," + curve.x2 + "," + curve.y2 + ")";
  }

  function buildKeyframes(styleId, rng, curveOverride, randomPctOverride) {
    var style = STYLE_MAP[styleId] || {};
    var curve = curveOverride || style.default_curve;
    var dyn = curve ? easingFromCurve(curve) : null;
    var randomPct = randomPctOverride != null ? randomPctOverride : state.randomPct;
    var dx = (rng() - 0.5) * 2 * (randomPct || 0) * 1.4;
    var dy = (rng() - 0.5) * 2 * (randomPct || 0) * 1.4;
    switch (styleId) {
      case "pop":
        return { frames: [
          { opacity: 0, transform: "scale(0)" },
          { opacity: 1, transform: "scale(1)" },
        ], easing: dyn || "cubic-bezier(.34,1.56,.64,1)" };
      case "blur":
        return { frames: [
          { opacity: 0, filter: "blur(10px)" },
          { opacity: 1, filter: "blur(0px)" },
        ], easing: "cubic-bezier(0,0,.04,1)" };
      case "blur_up":
        return { frames: [
          { opacity: 0, filter: "blur(5px)", transform: "translateY(26px)" },
          { opacity: 1, filter: "blur(0px)", transform: "translateY(0)" },
        ], easing: dyn || "cubic-bezier(0,0,.16,1)" };
      case "bounce_move":
        return { frames: [
          { opacity: 0, transform: "translateX(-40px) scale(0)" },
          { opacity: 1, transform: "translateX(0) scale(1)" },
        ], easing: dyn || "cubic-bezier(.33,1.4,.16,.9)" };
      case "random_in":
        return { frames: [
          { opacity: 0, transform: "translate(" + dx + "px," + dy + "px)" },
          { opacity: 1, transform: "translate(0,0)" },
        ], easing: dyn || "cubic-bezier(.42,0,.15,1)" };
      case "random_in_out":
        return { frames: [
          { opacity: 0, transform: "translate(" + dx + "px," + dy + "px)" },
          { opacity: 1, transform: "translate(0,0)", offset: 0.5 },
          { opacity: 0, transform: "translate(" + (-dx) + "px," + (-dy) + "px)" },
        ], easing: dyn || "cubic-bezier(.42,0,.15,1)" };
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
        ], easing: dyn || "cubic-bezier(0,0,.16,1)" };
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
    var curveOverride = (style.supports_curve_edit && state.curve) ? state.curve : null;

    units.forEach(function (unit, idx) {
      var span = document.createElement("span");
      span.className = "tf-unit";
      span.textContent = state.mode === "word" ? unit + (idx < n - 1 ? "\u00a0" : "") : unit;
      span.style.color = pickColor(idx, n);
      span.style.opacity = "0";
      el.appendChild(span);

      var kf = buildKeyframes(style.id, rng, curveOverride);
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
  // STEP 3 — panel "Layer" ala Alight Motion (timeline per unit)
  // ------------------------------------------------------------------ //
  function renderLayerPanel() {
    var rowsWrap = document.getElementById("tfLayerRows");
    var rulerWrap = document.getElementById("tfLayerRuler");
    var countEl = document.getElementById("tfLayerCount");
    if (!rowsWrap || !rulerWrap || !countEl) return;
    rowsWrap.innerHTML = "";
    rulerWrap.innerHTML = "";

    var units = getUnits();
    if (!units.length) { countEl.textContent = "0 layer"; return; }
    var n = units.length;
    var timing = computeUnitTimings(units);
    countEl.textContent = n + " layer";

    var totalSec = Math.max(1, Math.ceil(timing.totalMs / 1000));
    for (var s = 0; s <= totalSec; s++) {
      var tick = document.createElement("span");
      tick.textContent = s + "s";
      rulerWrap.appendChild(tick);
    }

    units.forEach(function (unit, idx) {
      var t = timing.timings[idx];
      var row = document.createElement("div");
      row.className = "tf-layer-row";

      // Warna panel Layer ini SENGAJA dipatenkan (bukan ikut palet warna
      // user) — mengikuti tampilan panel layer Alight Motion/Flamo Creative
      // yang dipakai sebagai acuan, supaya konsisten & mudah dibaca.
      var label = document.createElement("div");
      label.className = "tf-layer-label";
      label.textContent = unit.charAt(0);
      row.appendChild(label);

      var track = document.createElement("div");
      track.className = "tf-layer-track";
      var leftPct = (t.start / timing.totalMs) * 100;
      var widthPct = Math.max(2, ((t.end - t.start) / timing.totalMs) * 100);
      var bar = document.createElement("div");
      bar.className = "tf-layer-bar";
      bar.style.left = leftPct + "%";
      bar.style.width = widthPct + "%";
      track.appendChild(bar);
      var kf = document.createElement("div");
      kf.className = "tf-layer-kf";
      kf.style.left = leftPct + "%";
      track.appendChild(kf);
      row.appendChild(track);

      var ms = document.createElement("div");
      ms.className = "tf-layer-ms";
      ms.textContent = t.start + "ms";
      row.appendChild(ms);

      rowsWrap.appendChild(row);
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
      (style.supports_curve_edit && state.curve
        ? "<dt>Kurva</dt><dd>cubic-bezier(" + state.curve.x1 + ", " + state.curve.y1 + ", " + state.curve.x2 + ", " + state.curve.y2 + ")</dd>"
        : "") +
      "<dt>Palet warna</dt><dd>" + state.colors.join(", ") + " (" + (MAPPINGS[state.mapping] || state.mapping) + ")</dd>" +
      "</dl>";
  }

  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s == null ? "" : s;
    return div.innerHTML;
  }

  function buildPayload() {
    var style = STYLE_MAP[state.styleId] || {};
    var payload = {
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
    if (style.supports_curve_edit && state.curve) {
      payload.curve_id = state.curveId || "";
      payload.curve = state.curve;
    }
    return payload;
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
    buildCurveSvg();
    renderCurvePresetChips();
    bindCurveInputs();
    updateCurveSectionVisibility();

    document.getElementById("tfNext1").addEventListener("click", function () { goToStep(2); });
    document.getElementById("tfBack2").addEventListener("click", function () { goToStep(1); });
    document.getElementById("tfNext2").addEventListener("click", function () {
      if (!state.text.trim()) { alert("Teks tidak boleh kosong."); return; }
      goToStep(3);
    });
    document.getElementById("tfBack3").addEventListener("click", function () { goToStep(2); });
    document.getElementById("tfNext3").addEventListener("click", function () { goToStep(4); });
    document.getElementById("tfBack4").addEventListener("click", function () { goToStep(3); });
    document.getElementById("tfReplay").addEventListener("click", function () { renderPreview(); renderLayerPanel(); });
    document.getElementById("tfExportBtn").addEventListener("click", function () { generateXml("download"); });
    document.getElementById("tfCopyBtn").addEventListener("click", function () { generateXml("copy"); });
  });
})();
