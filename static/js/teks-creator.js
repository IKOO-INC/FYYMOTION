// Teks Creator — wizard 4 langkah + curve editor + generate/export XML.
(function () {
  "use strict";

  var PRESETS = window.TC_PRESETS || {};
  var PRESET_GROUPS = window.TC_PRESET_GROUPS || {};
  var CATEGORY_LABELS = window.TC_CATEGORY_LABELS || {};
  var CURVES = window.TC_CURVES || {};
  var FONTS = window.TC_FONTS || {};
  var CANVAS = window.TC_CANVAS || {};
  var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var CATEGORY_ORDER = ["hand_crafted", "one_click"];

  var FONT_STACK = {
    inter: '"Inter", -apple-system, sans-serif',
    roboto: '"Roboto", -apple-system, sans-serif',
    open_sans: '"Open Sans", -apple-system, sans-serif',
    montserrat: '"Montserrat", -apple-system, sans-serif',
    poppins: '"Poppins", -apple-system, sans-serif',
  };

  var state = {
    presetId: null,
    text: "FYY MOTION",
    fontSize: 80,
    color: "#f5f5f7",
    fontId: "inter",
    weight: 700,
    align: "center",
    durationMs: 900,
    canvasId: "portrait",
    curveId: "apple_ease",
    curve: { x1: 0.25, y1: 0.1, x2: 0.25, y2: 1.0 },
  };
  var lastXml = null;
  var lastFilename = null;

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
    if (n === 2) renderPreview("tcPreviewText2");
    if (n === 3) renderPreview("tcPreviewText3");
    if (n === 4) renderSummary();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ //
  // STEP 1 — kategori tab (Hand-Crafted / One-Click) + preset cards
  // ------------------------------------------------------------------ //
  function selectPresetCard(id, card) {
    document.querySelectorAll(".tc-preset-card").forEach(function (c) { c.classList.remove("selected"); });
    if (card) card.classList.add("selected");
    var preset = PRESETS[id];
    state.presetId = id;
    state.durationMs = preset.default_duration_ms;
    state.text = preset.demo_text || state.text;
    var curveArr = preset.curve;
    if (curveArr && curveArr.length === 4) {
      state.curve = { x1: curveArr[0], y1: curveArr[1], x2: curveArr[2], y2: curveArr[3] };
    }
    state.curveId = "";
    document.getElementById("tcNext1").disabled = false;
  }

  function renderPresetCards() {
    var tabsWrap = document.getElementById("tcCatTabs");
    var panelsWrap = document.getElementById("tcCatPanels");
    tabsWrap.innerHTML = "";
    panelsWrap.innerHTML = "";

    CATEGORY_ORDER.forEach(function (catId, idx) {
      var items = PRESET_GROUPS[catId] || [];
      if (!items.length) return;
      var label = CATEGORY_LABELS[catId] || catId;

      var tab = document.createElement("button");
      tab.type = "button";
      tab.className = "tc-cat-tab" + (idx === 0 ? " active" : "");
      tab.dataset.catId = catId;
      tab.innerHTML = label + ' <span class="tc-cat-count">' + items.length + "</span>";
      tab.addEventListener("click", function () {
        document.querySelectorAll(".tc-cat-tab").forEach(function (t) { t.classList.remove("active"); });
        document.querySelectorAll(".tc-cat-panel").forEach(function (p) { p.classList.remove("active"); });
        tab.classList.add("active");
        document.getElementById("tcCatPanel-" + catId).classList.add("active");
      });
      tabsWrap.appendChild(tab);

      var panel = document.createElement("div");
      panel.className = "tc-cat-panel" + (idx === 0 ? " active" : "");
      panel.id = "tcCatPanel-" + catId;
      var grid = document.createElement("div");
      grid.className = "tc-preset-grid";

      items.forEach(function (item) {
        var card = document.createElement("button");
        card.type = "button";
        card.className = "tc-preset-card";
        card.dataset.presetId = item.id;
        card.innerHTML =
          '<span class="tc-preset-icon"><i class="' + item.icon + '"></i></span>' +
          "<h3>" + item.name + "</h3>" +
          "<p>" + item.description + "</p>" +
          (item.demo_text ? '<span class="tc-preset-demo">"' + escapeHtml(item.demo_text) + '"</span>' : "") +
          (item.note ? '<div class="tc-preset-note"><i class="fa-solid fa-circle-info"></i> ' + item.note + "</div>" : "");
        card.addEventListener("click", function () { selectPresetCard(item.id, card); });
        grid.appendChild(card);
      });

      panel.appendChild(grid);
      panelsWrap.appendChild(panel);
    });
  }

  // ------------------------------------------------------------------ //
  // STEP 2 — form fields
  // ------------------------------------------------------------------ //
  function renderFontOptions() {
    var select = document.getElementById("tcFont");
    select.innerHTML = "";
    Object.keys(FONTS).forEach(function (id) {
      var opt = document.createElement("option");
      opt.value = id;
      opt.textContent = FONTS[id].label;
      select.appendChild(opt);
    });
    select.value = state.fontId;
  }

  function renderCanvasOptions() {
    var select = document.getElementById("tcCanvas");
    select.innerHTML = "";
    Object.keys(CANVAS).forEach(function (id) {
      var opt = document.createElement("option");
      opt.value = id;
      opt.textContent = CANVAS[id].label;
      select.appendChild(opt);
    });
    select.value = state.canvasId;
  }

  function bindFormFields() {
    var text = document.getElementById("tcText");
    var fontSize = document.getElementById("tcFontSize");
    var color = document.getElementById("tcColor");
    var colorText = document.getElementById("tcColorText");
    var font = document.getElementById("tcFont");
    var weight = document.getElementById("tcWeight");
    var align = document.getElementById("tcAlign");
    var duration = document.getElementById("tcDuration");
    var canvas = document.getElementById("tcCanvas");

    text.addEventListener("input", function () { state.text = text.value; renderPreview("tcPreviewText2"); });
    fontSize.addEventListener("input", function () { state.fontSize = Number(fontSize.value) || 80; renderPreview("tcPreviewText2"); });
    color.addEventListener("input", function () { state.color = color.value; colorText.value = color.value; renderPreview("tcPreviewText2"); });
    colorText.addEventListener("change", function () {
      var v = colorText.value.trim();
      if (/^#[0-9a-fA-F]{6}$/.test(v)) { state.color = v; color.value = v; renderPreview("tcPreviewText2"); }
    });
    font.addEventListener("change", function () { state.fontId = font.value; renderPreview("tcPreviewText2"); });
    weight.addEventListener("change", function () { state.weight = Number(weight.value); renderPreview("tcPreviewText2"); });
    align.addEventListener("change", function () { state.align = align.value; });
    duration.addEventListener("input", function () { state.durationMs = Number(duration.value) || 900; });
    canvas.addEventListener("change", function () { state.canvasId = canvas.value; });
  }

  function syncFormFromState() {
    document.getElementById("tcText").value = state.text;
    document.getElementById("tcFontSize").value = state.fontSize;
    document.getElementById("tcColor").value = state.color;
    document.getElementById("tcColorText").value = state.color;
    document.getElementById("tcFont").value = state.fontId;
    document.getElementById("tcWeight").value = String(state.weight);
    document.getElementById("tcAlign").value = state.align;
    document.getElementById("tcDuration").value = state.durationMs;
    document.getElementById("tcCanvas").value = state.canvasId;
  }

  // ------------------------------------------------------------------ //
  // Preview (approximasi di browser, bukan render asli Alight Motion)
  // ------------------------------------------------------------------ //
  function renderPreview(targetId) {
    var el = document.getElementById(targetId);
    if (!el || !state.presetId) return;
    var preset = PRESETS[state.presetId];
    el.style.fontFamily = FONT_STACK[state.fontId] || FONT_STACK.inter;
    el.style.fontWeight = state.weight;
    el.style.color = state.color;
    el.style.fontSize = Math.max(18, Math.min(state.fontSize, 64)) + "px";
    el.style.textAlign = state.align;
    el.innerHTML = "";

    var dur = state.durationMs;
    var easing = "cubic-bezier(" + state.curve.x1 + "," + state.curve.y1 + "," + state.curve.x2 + "," + state.curve.y2 + ")";
    var engine = preset.engine;

    if (engine === "letter_pop") {
      var letters = state.text.split("").filter(function (c) { return c !== "\n"; });
      var rotationDeg = (preset.params && preset.params.rotation_deg) || 0;
      var staggerMs = (preset.params && preset.params.stagger_ms) || 100;
      letters.forEach(function (ch, i) {
        var span = document.createElement("span");
        span.textContent = ch === " " ? "\u00a0" : ch;
        span.style.display = "inline-block";
        span.style.opacity = "0";
        el.appendChild(span);
        try {
          span.animate(
            [
              { opacity: 0, transform: "scale(0) rotate(" + rotationDeg + "deg)" },
              { opacity: 1, transform: "scale(1) rotate(0deg)" },
            ],
            { duration: Math.max(200, dur * 0.6), delay: i * staggerMs, easing: easing, fill: "both" }
          );
        } catch (e) { span.style.opacity = "1"; }
      });
    } else if (engine === "texttransform" || engine === "wipe") {
      var isMirror = preset.params && preset.params.mirror;
      var units = state.text.split(/(\s+)/);
      units.forEach(function (chunk, i) {
        var span = document.createElement("span");
        span.textContent = chunk === " " ? "\u00a0" : chunk;
        span.style.display = "inline-block";
        span.style.opacity = "0";
        el.appendChild(span);
        try {
          span.animate(
            [
              { opacity: 0, transform: isMirror ? "scaleX(-1) translateX(20px)" : "translateY(14px)" },
              { opacity: 1, transform: isMirror ? "scaleX(1) translateX(0)" : "translateY(0)" },
            ],
            { duration: Math.max(180, dur * 0.6), delay: i * 90, easing: easing, fill: "both" }
          );
        } catch (e) { span.style.opacity = "1"; }
      });
    } else if (engine === "typewriter") {
      el.textContent = "";
      var chars = state.text.split("");
      var perChar = Math.max(30, dur / Math.max(1, chars.length));
      chars.forEach(function (ch, i) {
        setTimeout(function () { el.textContent += ch; }, i * perChar);
      });
    } else {
      el.textContent = state.text;
      var keyframes;
      if (engine === "blur_pop") {
        keyframes = [
          { opacity: 0, filter: "blur(8px)", transform: "scale(0.9)" },
          { opacity: 1, filter: "blur(0px)", transform: "scale(1)" },
        ];
      } else if (engine === "fade_slide") {
        keyframes = [
          { opacity: 0, transform: "translateY(30px)" },
          { opacity: 1, transform: "translateY(0)" },
        ];
      } else if (engine === "distort") {
        keyframes = [
          { opacity: 0, transform: "scale(1.4)" },
          { opacity: 1, transform: "scale(1)" },
        ];
      } else if (engine === "mask_slide") {
        keyframes = [
          { opacity: 0, transform: "translateX(-60px)" },
          { opacity: 1, transform: "translateX(0)" },
        ];
      } else {
        keyframes = [
          { opacity: 0, transform: "scale(0)" },
          { opacity: 1, transform: "scale(1)" },
        ];
      }
      try {
        el.animate(keyframes, { duration: dur, easing: easing, fill: "both" });
      } catch (e) { /* older browser fallback: static */ }
    }
  }

  // ------------------------------------------------------------------ //
  // STEP 3 — curve editor (SVG, dua handle draggable)
  // ------------------------------------------------------------------ //
  var SVG_SIZE = 260;
  var PAD = 24;
  var INNER = SVG_SIZE - PAD * 2;
  var Y_MIN = -0.7, Y_MAX = 1.7;

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
    var svg = document.getElementById("tcCurveSvg");
    svg.innerHTML =
      '<rect x="0" y="0" width="' + SVG_SIZE + '" height="' + SVG_SIZE + '" rx="16" fill="#0b0b0d"></rect>' +
      '<line id="tcLine0" stroke="#4b4b50" stroke-width="1.5"></line>' +
      '<line id="tcLine1" stroke="#4b4b50" stroke-width="1.5"></line>' +
      '<path id="tcCurvePath" fill="none" stroke="#0a84ff" stroke-width="3"></path>' +
      '<circle id="tcAnchorStart" r="4" fill="#8e8e93"></circle>' +
      '<circle id="tcAnchorEnd" r="4" fill="#8e8e93"></circle>' +
      '<circle id="tcHandle1" r="8" fill="#ff9f0a" style="cursor:grab"></circle>' +
      '<circle id="tcHandle2" r="8" fill="#0a84ff" style="cursor:grab"></circle>';
    bindHandleDrag(document.getElementById("tcHandle1"), function (x, y) { state.curve.x1 = x; state.curve.y1 = y; });
    bindHandleDrag(document.getElementById("tcHandle2"), function (x, y) { state.curve.x2 = x; state.curve.y2 = y; });
  }

  function bindHandleDrag(handle, onMove) {
    handle.addEventListener("pointerdown", function (ev) {
      handle.setPointerCapture(ev.pointerId);
      handle.style.cursor = "grabbing";
      function move(e) {
        var svg = document.getElementById("tcCurveSvg");
        var rect = svg.getBoundingClientRect();
        var scale = SVG_SIZE / rect.width;
        var px = (e.clientX - rect.left) * scale;
        var py = (e.clientY - rect.top) * scale;
        var x = Math.round(pixelToDataX(px) * 100) / 100;
        var y = Math.round(pixelToDataY(py) * 100) / 100;
        onMove(x, y);
        state.curveId = "";
        updateCurvePresetChips();
        syncCurveInputs();
        drawCurve();
        renderPreview("tcPreviewText3");
      }
      function up(e) {
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
    var x0 = dataToPixelX(0), y0 = dataToPixelY(0);
    var x3 = dataToPixelX(1), y3 = dataToPixelY(1);
    var x1 = dataToPixelX(state.curve.x1), y1 = dataToPixelY(state.curve.y1);
    var x2 = dataToPixelX(state.curve.x2), y2 = dataToPixelY(state.curve.y2);

    document.getElementById("tcLine0").setAttribute("x1", x0); document.getElementById("tcLine0").setAttribute("y1", y0);
    document.getElementById("tcLine0").setAttribute("x2", x1); document.getElementById("tcLine0").setAttribute("y2", y1);
    document.getElementById("tcLine1").setAttribute("x1", x3); document.getElementById("tcLine1").setAttribute("y1", y3);
    document.getElementById("tcLine1").setAttribute("x2", x2); document.getElementById("tcLine1").setAttribute("y2", y2);
    document.getElementById("tcCurvePath").setAttribute("d", "M " + x0 + " " + y0 + " C " + x1 + " " + y1 + ", " + x2 + " " + y2 + ", " + x3 + " " + y3);
    document.getElementById("tcAnchorStart").setAttribute("cx", x0); document.getElementById("tcAnchorStart").setAttribute("cy", y0);
    document.getElementById("tcAnchorEnd").setAttribute("cx", x3); document.getElementById("tcAnchorEnd").setAttribute("cy", y3);
    document.getElementById("tcHandle1").setAttribute("cx", x1); document.getElementById("tcHandle1").setAttribute("cy", y1);
    document.getElementById("tcHandle2").setAttribute("cx", x2); document.getElementById("tcHandle2").setAttribute("cy", y2);
  }

  function renderCurvePresetChips() {
    var wrap = document.getElementById("tcCurvePresets");
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
        renderPreview("tcPreviewText3");
      });
      wrap.appendChild(chip);
    });
    updateCurvePresetChips();
  }

  function updateCurvePresetChips() {
    document.querySelectorAll(".tc-chip").forEach(function (chip) {
      chip.classList.toggle("active", chip.dataset.curveId === state.curveId);
    });
  }

  function syncCurveInputs() {
    document.getElementById("tcX1").value = state.curve.x1;
    document.getElementById("tcY1").value = state.curve.y1;
    document.getElementById("tcX2").value = state.curve.x2;
    document.getElementById("tcY2").value = state.curve.y2;
  }

  function bindCurveInputs() {
    function bind(id, key, isX) {
      document.getElementById(id).addEventListener("change", function (e) {
        var v = parseFloat(e.target.value);
        if (isNaN(v)) return;
        if (isX) v = Math.min(1, Math.max(0, v));
        else v = Math.min(3, Math.max(-2, v));
        state.curve[key] = v;
        state.curveId = "";
        updateCurvePresetChips();
        drawCurve();
        renderPreview("tcPreviewText3");
      });
    }
    bind("tcX1", "x1", true);
    bind("tcY1", "y1", false);
    bind("tcX2", "x2", true);
    bind("tcY2", "y2", false);
  }

  // ------------------------------------------------------------------ //
  // STEP 4 — summary & export
  // ------------------------------------------------------------------ //
  function renderSummary() {
    var preset = PRESETS[state.presetId] || {};
    var box = document.getElementById("tcSummary");
    box.innerHTML =
      "<dl>" +
      "<dt>Preset</dt><dd>" + preset.name + "</dd>" +
      "<dt>Teks</dt><dd>" + escapeHtml(state.text) + "</dd>" +
      "<dt>Font</dt><dd>" + (FONTS[state.fontId] || {}).label + ", weight " + state.weight + "</dd>" +
      "<dt>Ukuran</dt><dd>" + state.fontSize + " px, warna " + state.color + "</dd>" +
      "<dt>Durasi</dt><dd>" + state.durationMs + " ms</dd>" +
      "<dt>Kanvas</dt><dd>" + (CANVAS[state.canvasId] || {}).label + "</dd>" +
      "<dt>Kurva</dt><dd>cubic-bezier(" + state.curve.x1 + ", " + state.curve.y1 + ", " + state.curve.x2 + ", " + state.curve.y2 + ")</dd>" +
      "</dl>";
  }

  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function buildPayload() {
    return {
      preset_id: state.presetId,
      text: state.text,
      font_size: state.fontSize,
      color: state.color,
      font_id: state.fontId,
      font_weight: state.weight,
      align: state.align,
      duration_ms: state.durationMs,
      canvas_id: state.canvasId,
      curve_id: state.curveId || "",
      curve: state.curve,
    };
  }

  function showResult(ok, message) {
    var box = document.getElementById("tcResult");
    box.className = "tc-result " + (ok ? "ok" : "err");
    box.innerHTML = (ok ? '<i class="fa-solid fa-circle-check"></i> ' : '<i class="fa-solid fa-triangle-exclamation"></i> ') + message;
  }

  function generateXml(action) {
    fetch("/api/teks-creator/generate", {
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
        lastFilename = match ? match[1] : "fyymotion-teks.xml";
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
  // Init
  // ------------------------------------------------------------------ //
  document.addEventListener("DOMContentLoaded", function () {
    renderPresetCards();
    renderFontOptions();
    renderCanvasOptions();
    bindFormFields();
    buildCurveSvg();
    renderCurvePresetChips();
    bindCurveInputs();

    document.getElementById("tcNext1").addEventListener("click", function () { goToStep(2); syncFormFromState(); });
    document.getElementById("tcBack2").addEventListener("click", function () { goToStep(1); });
    document.getElementById("tcNext2").addEventListener("click", function () {
      if (!state.text.trim()) { alert("Teks tidak boleh kosong."); return; }
      updateCurvePresetChips();
      syncCurveInputs();
      drawCurve();
      goToStep(3);
    });
    document.getElementById("tcBack3").addEventListener("click", function () { goToStep(2); });
    document.getElementById("tcNext3").addEventListener("click", function () { goToStep(4); });
    document.getElementById("tcBack4").addEventListener("click", function () { goToStep(3); });
    document.getElementById("tcReplay").addEventListener("click", function () { renderPreview("tcPreviewText3"); });
    document.getElementById("tcExportBtn").addEventListener("click", function () { generateXml("download"); });
    document.getElementById("tcCopyBtn").addEventListener("click", function () { generateXml("copy"); });
  });
})();
