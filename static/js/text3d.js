// 3D Text — form real-time + preview + Layer panel + Layer Graph Controller + export XML.
(function () {
  "use strict";

  var STYLES = window.T3D_STYLES || [];
  var MODES = window.T3D_MODES || {};
  var FONTS = window.T3D_FONTS || {};
  var CANVAS = window.T3D_CANVAS || {};
  var CURVES = window.T3D_CURVES || {};
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
    canvasId: "square",
    spacing: 120,
    lineGap: 200,
    xPos: 0,
    yPos: 0,
    extrudeDepth: 50,
    border: true,
    colors: {},
    stagger: 60,
    lastStart: 500,
    endHold: 1000,
    curve: null,
    curveId: "",
  };

  function applyStyleDefaults(styleId) {
    var style = STYLE_MAP[styleId];
    if (!style) return;
    state.canvasId = style.default_canvas || state.canvasId;
    state.colors = {};
    (style.color_roles || []).forEach(function (role) { state.colors[role.key] = role.default; });
    if (style.supports_curve_edit && style.default_curve) {
      state.curve = Object.assign({}, style.default_curve);
    } else {
      state.curve = null;
    }
    state.curveId = "";
  }
  applyStyleDefaults(state.styleId);

  var lastXml = null;
  var lastFilename = null;
  var lgcBuilt = false;

  // ------------------------------------------------------------------ //
  // Preset grid (step-less: klik langsung ganti preset & render ulang)
  // ------------------------------------------------------------------ //
  var DEMO_UNITS = ["F", "Y", "Y"];
  var demoTimers = {};

  function renderStyleCards() {
    var grid = document.getElementById("t3dStyleGrid");
    grid.innerHTML = "";
    STYLES.forEach(function (style) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "tc-preset-card" + (style.id === state.styleId ? " selected" : "");
      card.innerHTML =
        '<div class="tc-preset-icon"><i class="' + style.icon + '"></i></div>' +
        "<h3>" + escapeHtml(style.name) + "</h3>" +
        "<p>" + escapeHtml(style.description.split(". Sumber:")[0]) + ".</p>" +
        '<div class="tf-card-demo" id="t3dDemo-' + style.id + '"></div>';
      card.addEventListener("click", function () {
        document.querySelectorAll("#t3dStyleGrid .tc-preset-card").forEach(function (c) { c.classList.remove("selected"); });
        card.classList.add("selected");
        state.styleId = style.id;
        applyStyleDefaults(style.id);
        renderColorRoles();
        renderCanvasOptions();
        updateExtrudeHint();
        updateLgcVisibility();
        renderAll();
      });
      grid.appendChild(card);
      startCardDemoLoop(style.id);
    });
  }

  function demoKeyframes(engine) {
    switch (engine) {
      case "flip":
        return { frames: [
          { opacity: 0, transform: "perspective(400px) rotateY(-100deg) scale(.6)" },
          { opacity: 1, transform: "perspective(400px) rotateY(0deg) scale(1)" },
        ], easing: "cubic-bezier(.3,1.4,.3,1)" };
      case "right":
        return { frames: [
          { opacity: 0, transform: "perspective(400px) translateX(46px) rotateY(35deg)" },
          { opacity: 1, transform: "perspective(400px) translateX(0) rotateY(0deg)" },
        ], easing: "cubic-bezier(0,0,.13,1)" };
      case "popup":
        return { frames: [
          { opacity: 0, transform: "perspective(400px) translateY(16px) scale(0) rotateX(40deg)" },
          { opacity: 1, transform: "perspective(400px) translateY(0) scale(1.12) rotateX(0deg)", offset: 0.7 },
          { opacity: 1, transform: "perspective(400px) translateY(0) scale(1) rotateX(0deg)" },
        ], easing: "cubic-bezier(.2,1.5,.2,1)" };
      case "longshadow":
        return { frames: [
          { opacity: 0, transform: "translateY(-34px) scale(.7)" },
          { opacity: 1, transform: "translateY(4px) scale(1.06)", offset: 0.65 },
          { opacity: 1, transform: "translateY(0) scale(1)" },
        ], easing: "cubic-bezier(.22,1.1,.3,1)" };
      case "offset":
        return { frames: [
          { opacity: 0, transform: "translateY(40px)" },
          { opacity: 1, transform: "translateY(-6px)", offset: 0.6 },
          { opacity: 1, transform: "translateY(0)" },
        ], easing: "cubic-bezier(.3,0,.2,1)" };
      default:
        return { frames: [{ opacity: 0 }, { opacity: 1 }], easing: "ease-out" };
    }
  }

  function playCardDemo(styleId) {
    var container = document.getElementById("t3dDemo-" + styleId);
    if (!container) return;
    container.innerHTML = "";
    var style = STYLE_MAP[styleId] || {};
    var staggerMs = 110;
    var durationMs = 640;
    DEMO_UNITS.forEach(function (ch, idx) {
      var span = document.createElement("span");
      span.className = "tf-unit";
      span.textContent = ch;
      span.style.opacity = "0";
      container.appendChild(span);
      var kf = demoKeyframes(style.engine);
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
    if (demoTimers[styleId]) clearTimeout(demoTimers[styleId]);
    var cycleMs = 640 + (DEMO_UNITS.length - 1) * 110 + 1000;
    function loop() {
      playCardDemo(styleId);
      demoTimers[styleId] = setTimeout(loop, cycleMs);
    }
    loop();
  }

  // ------------------------------------------------------------------ //
  // Form: font/canvas select, mode toggle, color roles, generic bindings
  // ------------------------------------------------------------------ //
  function renderFontOptions() {
    var sel = document.getElementById("t3dFont");
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
    var sel = document.getElementById("t3dCanvas");
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
    var wrap = document.getElementById("t3dModeToggle");
    wrap.querySelectorAll(".tf-mode-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        wrap.querySelectorAll(".tf-mode-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        state.mode = btn.dataset.mode;
        renderAll();
      });
    });
  }

  function renderColorRoles() {
    var wrap = document.getElementById("t3dColorRoles");
    wrap.innerHTML = "";
    var style = STYLE_MAP[state.styleId];
    if (!style) return;
    (style.color_roles || []).forEach(function (role) {
      var chip = document.createElement("div");
      chip.className = "t3d-color-role";
      var input = document.createElement("input");
      input.type = "color";
      input.value = state.colors[role.key] || role.default;
      input.addEventListener("input", function () {
        state.colors[role.key] = input.value;
        renderAll();
      });
      var label = document.createElement("span");
      label.textContent = role.label;
      chip.appendChild(input);
      chip.appendChild(label);
      wrap.appendChild(chip);
    });
  }

  function updateExtrudeHint() {
    var style = STYLE_MAP[state.styleId];
    var hint = document.getElementById("t3dExtrudeHint");
    if (!hint) return;
    var engines3d = { right: 1, popup: 1 };
    hint.textContent = (style && engines3d[style.engine])
      ? "Mengatur ketebalan extrude 3D pada huruf untuk preset ini."
      : "Hanya berpengaruh untuk preset Right & Popup Rotate Extrude (preset lain mengabaikan nilai ini).";
  }

  function bindFormFields() {
    document.getElementById("t3dText").addEventListener("input", function (e) { state.text = e.target.value; renderAll(); });
    document.getElementById("t3dFontSize").addEventListener("input", function (e) { state.fontSize = Number(e.target.value) || 90; renderAll(); });
    document.getElementById("t3dFont").addEventListener("change", function (e) { state.fontId = e.target.value; renderAll(); });
    document.getElementById("t3dWeight").addEventListener("change", function (e) { state.weight = Number(e.target.value); renderAll(); });
    document.getElementById("t3dCanvas").addEventListener("change", function (e) {
      state.canvasId = e.target.value;
      var lbl = document.getElementById("t3dPreviewCanvasLabel");
      if (lbl) lbl.textContent = (CANVAS[state.canvasId] || {}).label || state.canvasId;
      renderAll();
    });
    document.getElementById("t3dSpacing").addEventListener("input", function (e) { state.spacing = Number(e.target.value) || 120; renderAll(); });
    document.getElementById("t3dLineGap").addEventListener("input", function (e) { state.lineGap = Number(e.target.value) || 200; renderAll(); });
    document.getElementById("t3dX").addEventListener("input", function (e) { state.xPos = Number(e.target.value) || 0; renderAll(); });
    document.getElementById("t3dY").addEventListener("input", function (e) { state.yPos = Number(e.target.value) || 0; renderAll(); });
    document.getElementById("t3dExtrude").addEventListener("input", function (e) {
      state.extrudeDepth = Number(e.target.value) || 0;
      document.getElementById("t3dExtrudeLabel").textContent = state.extrudeDepth;
      renderAll();
    });
    document.getElementById("t3dBorder").addEventListener("change", function (e) { state.border = e.target.checked; renderAll(); });
    document.getElementById("t3dStagger").addEventListener("input", function (e) { state.stagger = Number(e.target.value) || 0; renderAll(); });
    document.getElementById("t3dLastStart").addEventListener("input", function (e) { state.lastStart = Number(e.target.value) || 0; renderAll(); });
    document.getElementById("t3dEndHold").addEventListener("input", function (e) { state.endHold = Number(e.target.value) || 0; renderAll(); });
  }

  // ------------------------------------------------------------------ //
  // LAYER GRAPH CONTROLLER — graph editor bergaya Alight Motion/Flamo.
  // Hanya untuk preset "right"/"popup" (kurva utamanya cubicBezier tunggal).
  // ------------------------------------------------------------------ //
  var SVG_SIZE = 320;
  var PAD = 30;
  var INNER = SVG_SIZE - PAD * 2;
  var Y_MIN = -0.8, Y_MAX = 1.8;

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

  function buildLgcSvg() {
    var svg = document.getElementById("t3dLgcSvg");
    if (!svg || lgcBuilt) return;
    lgcBuilt = true;
    svg.setAttribute("width", SVG_SIZE);
    svg.setAttribute("height", SVG_SIZE);

    var gridLines = "";
    for (var i = 0; i <= 8; i++) {
      var gx = PAD + (INNER / 8) * i;
      gridLines += '<line x1="' + gx + '" y1="' + PAD + '" x2="' + gx + '" y2="' + (SVG_SIZE - PAD) + '" stroke="#1d1d22" stroke-width="1"></line>';
    }
    for (var j = 0; j <= 8; j++) {
      var gy = PAD + (INNER / 8) * j;
      gridLines += '<line x1="' + PAD + '" y1="' + gy + '" x2="' + (SVG_SIZE - PAD) + '" y2="' + gy + '" stroke="#1d1d22" stroke-width="1"></line>';
    }
    var zeroY = dataToPixelY(0);
    var oneY = dataToPixelY(1);

    svg.innerHTML =
      '<rect x="0" y="0" width="' + SVG_SIZE + '" height="' + SVG_SIZE + '" fill="#0a0a0c"></rect>' +
      gridLines +
      '<line x1="' + PAD + '" y1="' + zeroY + '" x2="' + (SVG_SIZE - PAD) + '" y2="' + zeroY + '" stroke="#38383f" stroke-width="1.5" stroke-dasharray="3,3"></line>' +
      '<line x1="' + PAD + '" y1="' + oneY + '" x2="' + (SVG_SIZE - PAD) + '" y2="' + oneY + '" stroke="#38383f" stroke-width="1.5" stroke-dasharray="3,3"></line>' +
      '<text x="' + (PAD - 6) + '" y="' + (zeroY + 4) + '" text-anchor="end" font-size="11" fill="#6b6b72">0</text>' +
      '<text x="' + (PAD - 6) + '" y="' + (oneY + 4) + '" text-anchor="end" font-size="11" fill="#6b6b72">1</text>' +
      '<line id="t3dLgcLine0" stroke="#4b4b53" stroke-width="2"></line>' +
      '<line id="t3dLgcLine1" stroke="#4b4b53" stroke-width="2"></line>' +
      '<path id="t3dLgcPath" fill="none" stroke="#0a84ff" stroke-width="3.5"></path>' +
      '<circle id="t3dLgcAnchorStart" r="5" fill="#8e8e96"></circle>' +
      '<circle id="t3dLgcAnchorEnd" r="5" fill="#8e8e96"></circle>' +
      '<circle id="t3dLgcDot" r="6" fill="#ffd60a" style="display:none"></circle>' +
      '<circle id="t3dLgcHandle1" r="9" fill="#ff9f0a" stroke="#000" stroke-width="1" style="cursor:grab"></circle>' +
      '<circle id="t3dLgcHandle2" r="9" fill="#0a84ff" stroke="#000" stroke-width="1" style="cursor:grab"></circle>';

    bindLgcDrag(document.getElementById("t3dLgcHandle1"), function (x, y) { state.curve.x1 = x; state.curve.y1 = y; });
    bindLgcDrag(document.getElementById("t3dLgcHandle2"), function (x, y) { state.curve.x2 = x; state.curve.y2 = y; });
  }

  function bindLgcDrag(handle, onMove) {
    handle.addEventListener("pointerdown", function (ev) {
      handle.setPointerCapture(ev.pointerId);
      handle.style.cursor = "grabbing";
      function move(e) {
        var svg = document.getElementById("t3dLgcSvg");
        var rect = svg.getBoundingClientRect();
        var scale = SVG_SIZE / rect.width;
        var px = (e.clientX - rect.left) * scale;
        var py = (e.clientY - rect.top) * scale;
        var x = Math.round(pixelToDataX(px) * 100) / 100;
        var y = Math.round(pixelToDataY(py) * 100) / 100;
        if (!state.curve) return;
        onMove(x, y);
        state.curveId = "";
        updateLgcPresetChips();
        syncLgcInputs();
        drawLgcCurve();
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

  function drawLgcCurve() {
    if (!state.curve) return;
    var x0 = dataToPixelX(0), y0 = dataToPixelY(0);
    var x3 = dataToPixelX(1), y3 = dataToPixelY(1);
    var x1 = dataToPixelX(state.curve.x1), y1 = dataToPixelY(state.curve.y1);
    var x2 = dataToPixelX(state.curve.x2), y2 = dataToPixelY(state.curve.y2);

    setAttrs("t3dLgcLine0", { x1: x0, y1: y0, x2: x1, y2: y1 });
    setAttrs("t3dLgcLine1", { x1: x3, y1: y3, x2: x2, y2: y2 });
    var path = document.getElementById("t3dLgcPath");
    if (path) path.setAttribute("d", "M " + x0 + " " + y0 + " C " + x1 + " " + y1 + ", " + x2 + " " + y2 + ", " + x3 + " " + y3);
    setAttrs("t3dLgcAnchorStart", { cx: x0, cy: y0 });
    setAttrs("t3dLgcAnchorEnd", { cx: x3, cy: y3 });
    setAttrs("t3dLgcHandle1", { cx: x1, cy: y1 });
    setAttrs("t3dLgcHandle2", { cx: x2, cy: y2 });

    var h1 = document.getElementById("t3dLgcH1Read");
    var h2 = document.getElementById("t3dLgcH2Read");
    if (h1) h1.textContent = state.curve.x1.toFixed(2) + ", " + state.curve.y1.toFixed(2);
    if (h2) h2.textContent = state.curve.x2.toFixed(2) + ", " + state.curve.y2.toFixed(2);
  }

  function setAttrs(id, attrs) {
    var el = document.getElementById(id);
    if (!el) return;
    Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
  }

  function renderLgcPresetChips() {
    var wrap = document.getElementById("t3dLgcPresets");
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
        updateLgcPresetChips();
        syncLgcInputs();
        drawLgcCurve();
        renderPreview();
      });
      wrap.appendChild(chip);
    });
    updateLgcPresetChips();
  }

  function updateLgcPresetChips() {
    document.querySelectorAll("#t3dLgcPresets .tc-chip").forEach(function (chip) {
      chip.classList.toggle("active", chip.dataset.curveId === state.curveId);
    });
  }

  function syncLgcInputs() {
    if (!state.curve) return;
    document.getElementById("t3dLgcX1").value = state.curve.x1;
    document.getElementById("t3dLgcY1").value = state.curve.y1;
    document.getElementById("t3dLgcX2").value = state.curve.x2;
    document.getElementById("t3dLgcY2").value = state.curve.y2;
  }

  function bindLgcInputs() {
    function bind(id, key, isX) {
      document.getElementById(id).addEventListener("change", function (e) {
        if (!state.curve) return;
        var v = parseFloat(e.target.value);
        if (isNaN(v)) return;
        if (isX) v = Math.min(1, Math.max(0, v));
        else v = Math.min(3, Math.max(-2, v));
        state.curve[key] = v;
        state.curveId = "";
        updateLgcPresetChips();
        drawLgcCurve();
        renderPreview();
      });
    }
    bind("t3dLgcX1", "x1", true);
    bind("t3dLgcY1", "y1", false);
    bind("t3dLgcX2", "x2", true);
    bind("t3dLgcY2", "y2", false);

    document.getElementById("t3dLgcReset").addEventListener("click", function () {
      var style = STYLE_MAP[state.styleId];
      if (!style || !style.default_curve) return;
      state.curve = Object.assign({}, style.default_curve);
      state.curveId = "";
      updateLgcPresetChips();
      syncLgcInputs();
      drawLgcCurve();
      renderPreview();
    });

    document.getElementById("t3dLgcPlay").addEventListener("click", function () {
      playLgcDot();
      renderPreview();
    });
  }

  function playLgcDot() {
    if (!state.curve) return;
    var dot = document.getElementById("t3dLgcDot");
    var path = document.getElementById("t3dLgcPath");
    if (!dot || !path) return;
    dot.style.display = "block";
    var len = path.getTotalLength();
    var start = performance.now();
    var durationMs = 900;
    function step(now) {
      var t = Math.min(1, (now - start) / durationMs);
      var pt = path.getPointAtLength(t * len);
      dot.setAttribute("cx", pt.x);
      dot.setAttribute("cy", pt.y);
      if (t < 1) requestAnimationFrame(step);
      else setTimeout(function () { dot.style.display = "none"; }, 220);
    }
    requestAnimationFrame(step);
  }

  function updateLgcVisibility() {
    var style = STYLE_MAP[state.styleId];
    var supports = !!(style && style.supports_curve_edit);
    var wrap = document.getElementById("t3dLgcWrap");
    var locked = document.getElementById("t3dLgcLocked");
    if (wrap) wrap.style.display = supports ? "block" : "none";
    if (locked) locked.style.display = supports ? "none" : "block";
    if (supports) {
      buildLgcSvg();
      if (!state.curve && style.default_curve) state.curve = Object.assign({}, style.default_curve);
      syncLgcInputs();
      updateLgcPresetChips();
      drawLgcCurve();
    }
  }

  // ------------------------------------------------------------------ //
  // Layout (mirror backend _layout_units): baris, unit, posisi, stagger.
  // ------------------------------------------------------------------ //
  function getLines() {
    var raw = state.text.replace(/\r/g, "").split("\n");
    var lines = raw.map(function (ln) { return ln.replace(/\s+/g, " ").trim(); }).filter(Boolean);
    return lines.slice(0, 3);
  }

  function getLineUnits(lines) {
    return lines.map(function (ln) {
      if (state.mode === "character") return ln.split("").filter(function (c) { return c !== " "; });
      return ln.split(" ").filter(Boolean);
    }).filter(function (u) { return u.length; });
  }

  function layoutFlat() {
    var lines = getLines();
    var lineUnits = getLineUnits(lines);
    var flat = [];
    var totalUnits = 0;
    lineUnits.forEach(function (u) { totalUnits += u.length; });
    var staggerMs = Math.max(0, state.stagger);
    var lastStartMs = Math.max(0, state.lastStart);
    var idx = 0;
    lineUnits.forEach(function (units, li) {
      units.forEach(function (unit) {
        var rawStart = idx * staggerMs;
        var start = totalUnits > 1 ? Math.min(rawStart, lastStartMs) : 0;
        flat.push({ unit: unit, line: li, start: start, idx: idx });
        idx++;
      });
    });
    return { flat: flat, lineUnits: lineUnits, totalUnits: totalUnits };
  }

  // ------------------------------------------------------------------ //
  // Preview — simulasi CSS Web Animations per-engine (bukan render AM asli).
  // ------------------------------------------------------------------ //
  function easingFromCurve(curve) {
    return "cubic-bezier(" + curve.x1 + "," + curve.y1 + "," + curve.x2 + "," + curve.y2 + ")";
  }

  function unitKeyframes(engine, curve) {
    var dyn = curve ? easingFromCurve(curve) : null;
    switch (engine) {
      case "flip":
        return { frames: [
          { opacity: 0, transform: "perspective(600px) rotateY(-120deg) scale(.5)" },
          { opacity: 1, transform: "perspective(600px) rotateY(10deg) scale(1.06)", offset: 0.75 },
          { opacity: 1, transform: "perspective(600px) rotateY(0deg) scale(1)" },
        ], easing: "cubic-bezier(.28,1.35,.3,1)" };
      case "right":
        return { frames: [
          { opacity: 0, transform: "perspective(700px) translateX(70px) rotateY(45deg)" },
          { opacity: 1, transform: "perspective(700px) translateX(0) rotateY(0deg)" },
        ], easing: dyn || "cubic-bezier(0,0,.13,1)" };
      case "popup":
        return { frames: [
          { opacity: 0, transform: "perspective(700px) translateY(22px) scale(0) rotateX(50deg)" },
          { opacity: 1, transform: "perspective(700px) translateY(0) scale(1.14) rotateX(0deg)", offset: 0.68 },
          { opacity: 1, transform: "perspective(700px) translateY(0) scale(1) rotateX(0deg)" },
        ], easing: dyn || "cubic-bezier(.2,1.5,.2,1)" };
      case "longshadow":
        return { frames: [
          { opacity: 0, transform: "translateY(-46px) scale(.65)" },
          { opacity: 1, transform: "translateY(6px) scale(1.08)", offset: 0.6 },
          { opacity: 1, transform: "translateY(0) scale(1)" },
        ], easing: "cubic-bezier(.22,1.15,.3,1)" };
      case "offset":
        return { frames: [
          { opacity: 0, transform: "translateY(54px)" },
          { opacity: 1, transform: "translateY(-8px)", offset: 0.62 },
          { opacity: 1, transform: "translateY(0)" },
        ], easing: "cubic-bezier(.3,0,.2,1)" };
      default:
        return { frames: [{ opacity: 0 }, { opacity: 1 }], easing: "ease-out" };
    }
  }

  function applyExtrudeShadow(span, style) {
    var engines3d = { right: 1, popup: 1 };
    if (!engines3d[style.engine]) return;
    var depth = Math.max(0, Math.min(100, state.extrudeDepth));
    var layers = Math.max(1, Math.round(depth / 12));
    var extrudeColor = state.colors.extrude || state.colors.extrude_a || "#7E170E";
    var shadow = [];
    for (var i = 1; i <= layers; i++) {
      shadow.push(i + "px " + i + "px 0 " + extrudeColor);
    }
    span.style.textShadow = shadow.join(",");
  }

  function renderPreview() {
    var el = document.getElementById("t3dPreviewText");
    if (!el) return;
    el.innerHTML = "";
    el.style.fontFamily = FONT_STACK[state.fontId] || FONT_STACK.inter;
    el.style.fontWeight = state.weight;

    var style = STYLE_MAP[state.styleId] || STYLES[0];
    if (!style) return;
    var layout = layoutFlat();
    if (!layout.flat.length) return;

    var previewFontSize = Math.max(14, Math.min(state.fontSize * 0.42, 52));
    var curve = (style.supports_curve_edit && state.curve) ? state.curve : null;

    layout.lineUnits.forEach(function (units, li) {
      var lineEl = document.createElement("div");
      lineEl.className = "t3d-line";
      lineEl.style.marginTop = li > 0 ? Math.min(14, state.lineGap * 0.05) + "px" : "0";
      units.forEach(function () {});
      el.appendChild(lineEl);
    });
    var lineEls = el.querySelectorAll(".t3d-line");

    layout.flat.forEach(function (item) {
      var lineEl = lineEls[item.line];
      if (!lineEl) return;
      var span = document.createElement("span");
      span.className = "t3d-unit";
      span.textContent = state.mode === "word" ? item.unit + "\u00a0" : item.unit;
      span.style.color = state.colors.base || "#FFFFFF";
      span.style.fontSize = previewFontSize + "px";
      span.style.opacity = "0";
      applyExtrudeShadow(span, style);
      lineEl.appendChild(span);

      var kf = unitKeyframes(style.engine, curve);
      try {
        span.animate(kf.frames, {
          duration: 700,
          delay: item.start,
          easing: kf.easing || "ease-out",
          fill: "forwards",
        });
      } catch (e) { span.style.opacity = "1"; }
    });
  }

  // ------------------------------------------------------------------ //
  // Layer panel — real-time (tanpa step), mengikuti stagger/last-start/end-hold.
  // ------------------------------------------------------------------ //
  function renderLayerPanel() {
    var rowsWrap = document.getElementById("t3dLayerRows");
    var rulerWrap = document.getElementById("t3dLayerRuler");
    var countEl = document.getElementById("t3dLayerCount");
    if (!rowsWrap || !rulerWrap || !countEl) return;
    rowsWrap.innerHTML = "";
    rulerWrap.innerHTML = "";

    var layout = layoutFlat();
    var n = layout.flat.length;
    if (!n) { countEl.textContent = "0 layer"; return; }
    countEl.textContent = n + " layer" + (layout.lineUnits.length > 1 ? " (" + layout.lineUnits.length + " baris)" : "");

    var ownDurationMs = 900;
    var endHold = Math.max(0, state.endHold);
    var maxEnd = 0;
    layout.flat.forEach(function (item) {
      var end = item.start + ownDurationMs;
      if (end > maxEnd) maxEnd = end;
    });
    var totalMs = maxEnd + endHold || 1;

    var totalSec = Math.max(1, Math.ceil(totalMs / 1000));
    for (var s = 0; s <= totalSec; s++) {
      var tick = document.createElement("span");
      tick.textContent = s + "s";
      rulerWrap.appendChild(tick);
    }

    layout.flat.forEach(function (item) {
      var end = item.start + ownDurationMs + endHold;
      var row = document.createElement("div");
      row.className = "tf-layer-row";

      var label = document.createElement("div");
      label.className = "tf-layer-label";
      label.textContent = item.unit.charAt(0);
      row.appendChild(label);

      var track = document.createElement("div");
      track.className = "tf-layer-track";
      var leftPct = (item.start / totalMs) * 100;
      var widthPct = Math.max(2, ((end - item.start) / totalMs) * 100);
      var bar = document.createElement("div");
      bar.className = "tf-layer-bar";
      bar.style.left = leftPct + "%";
      bar.style.width = widthPct + "%";
      track.appendChild(bar);
      var kfDot = document.createElement("div");
      kfDot.className = "tf-layer-kf";
      kfDot.style.left = leftPct + "%";
      track.appendChild(kfDot);
      row.appendChild(track);

      var ms = document.createElement("div");
      ms.className = "tf-layer-ms";
      ms.textContent = item.start + "ms";
      row.appendChild(ms);

      rowsWrap.appendChild(row);
    });
  }

  // ------------------------------------------------------------------ //
  // Summary + payload + export
  // ------------------------------------------------------------------ //
  function renderSummary() {
    var box = document.getElementById("t3dSummary");
    if (!box) return;
    var style = STYLE_MAP[state.styleId] || {};
    var layout = layoutFlat();
    box.innerHTML =
      "<dl>" +
      "<dt>Preset</dt><dd>" + escapeHtml(style.name || "-") + "</dd>" +
      "<dt>Teks</dt><dd>" + escapeHtml(state.text) + "</dd>" +
      "<dt>Mode</dt><dd>" + (MODES[state.mode] || state.mode) + "</dd>" +
      "<dt>Unit</dt><dd>" + layout.totalUnits + " layer</dd>" +
      "<dt>Font</dt><dd>" + ((FONTS[state.fontId] || {}).label || state.fontId) + ", weight " + state.weight + "</dd>" +
      "<dt>Ukuran</dt><dd>" + state.fontSize + " px</dd>" +
      "<dt>Kanvas</dt><dd>" + ((CANVAS[state.canvasId] || {}).label || state.canvasId) + "</dd>" +
      "<dt>Extrude</dt><dd>" + state.extrudeDepth + "%</dd>" +
      "<dt>Timing</dt><dd>stagger " + state.stagger + "ms, last-start " + state.lastStart + "ms, end-hold " + state.endHold + "ms</dd>" +
      (style.supports_curve_edit && state.curve
        ? "<dt>Layer Graph</dt><dd>cubic-bezier(" + state.curve.x1 + ", " + state.curve.y1 + ", " + state.curve.x2 + ", " + state.curve.y2 + ")</dd>"
        : "") +
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
      text: state.text,
      mode: state.mode,
      style_id: state.styleId,
      font_size: state.fontSize,
      font_id: state.fontId,
      font_weight: state.weight,
      canvas_id: state.canvasId,
      spacing: state.spacing,
      line_gap: state.lineGap,
      x_position: state.xPos,
      y_position: state.yPos,
      extrude_depth: state.extrudeDepth,
      border: state.border,
      colors: state.colors,
      stagger_ms: state.stagger,
      last_start_ms: state.lastStart,
      end_hold_ms: state.endHold,
    };
    if (style.supports_curve_edit && state.curve) {
      payload.curve_id = state.curveId || "";
      payload.curve = state.curve;
    }
    return payload;
  }

  function showResult(ok, message) {
    var box = document.getElementById("t3dResult");
    box.className = "tc-result " + (ok ? "ok" : "err");
    box.innerHTML = (ok ? '<i class="fa-solid fa-circle-check"></i> ' : '<i class="fa-solid fa-triangle-exclamation"></i> ') + message;
  }

  function generateXml(action) {
    fetch("/api/tools/3d-text/generate", {
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
        lastFilename = match ? match[1] : "fyymotion-3dtext.xml";
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
  // Render orchestration — real-time, dipanggil di setiap perubahan param.
  // ------------------------------------------------------------------ //
  function renderAll() {
    renderPreview();
    renderLayerPanel();
    renderSummary();
  }

  // ------------------------------------------------------------------ //
  // Drawer mobile
  // ------------------------------------------------------------------ //
  function bindMobileDrawer() {
    var btn = document.getElementById("t3dDrawerBtn");
    var drawer = document.getElementById("t3dDrawer");
    var backdrop = document.getElementById("t3dDrawerBackdrop");
    var closeBtn = document.getElementById("t3dDrawerClose");
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
    renderFontOptions();
    renderCanvasOptions();
    bindModeToggle();
    renderColorRoles();
    bindFormFields();
    updateExtrudeHint();
    buildLgcSvg();
    renderLgcPresetChips();
    bindLgcInputs();
    updateLgcVisibility();

    var lbl = document.getElementById("t3dPreviewCanvasLabel");
    if (lbl) lbl.textContent = (CANVAS[state.canvasId] || {}).label || state.canvasId;

    document.getElementById("t3dReplay").addEventListener("click", renderAll);
    document.getElementById("t3dExportBtn").addEventListener("click", function () { generateXml("download"); });
    document.getElementById("t3dCopyBtn").addEventListener("click", function () { generateXml("copy"); });

    renderAll();
  });
})();
