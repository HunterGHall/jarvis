// The core: a black ring with a visualizer in the middle. Everything is SVG in a 1000 x 1000 box centred on
// (500, 500). The ring reacts to what Jarvis is doing:
//   idle       a ring of bars that slowly undulates around a breathing orb
//   listening  ripples spread across the disc
//   thinking   a pulse travels around the bars, with scan arcs outside them
//   speaking   the bars draw the audio spectrum of the voice as it plays
//   tool       a shockwave leaves the logo, a lane of the ring lights up in the tool's color with a comet running
//              along it, and the tool gets a line inside the circle. When it ends the lane fills green (or red)
//              with a second shockwave and fades.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const core = $("core");
  const svg = $("core-svg");
  const label = $("face-status");
  const calls = $("calls");

  // ---- colors ------------------------------------------------------------------------------------------------
  const TOOL_COLORS = [
    [/^(web_|search_news|get_headlines)/, [255, 190, 40]],
    [/^(get_weather|get_daily|get_hourly|get_air|get_sun|get_apod|get_iss|get_network|ping_host)/, [60, 160, 255]],
    [/^(get_earthquakes|.*recipe)/, [255, 130, 50]],
    [/^(get_stock|get_crypto|convert_currency|get_scores)/, [40, 210, 140]],
    [/^(define|calculate|convert_units|get_holidays|get_date|get_time|flip_coin|roll_dice|pick_random|random_number)/, [30, 210, 230]],
    [/^(media_|get_now_playing|get_lyrics|get_volume|set_volume)/, [245, 90, 215]],
    [/^(bash|delete_file|empty_recycle|get_recycle|set_timer|list_timers|cancel_timer)/, [255, 90, 110]],
    [/^(search_files|list_folder|read_file|write_file|move_file|copy_file|rename_file|create_folder|.*clipboard|search_images)/, [250, 165, 60]],
    [/^(get_system)/, [130, 220, 100]],
    [/^gmail_/, [255, 90, 110]],
    [/^(calendar_|docs_)/, [60, 160, 255]],
    [/^drive_/, [255, 190, 40]],
    [/^sheets_/, [40, 210, 140]],
    [/^slides_/, [250, 165, 60]],
  ];
  const DEFAULT_TOOL = [170, 120, 255];
  const GREEN = [61, 220, 151];
  const RED = [255, 90, 110];
  const toolColor = (name) => (TOOL_COLORS.find(([pattern]) => pattern.test(name)) || [null, DEFAULT_TOOL])[1];

  // color: the accent; label: the large word in the middle; sub: the small line under it
  const MODES = {
    starting: { color: [150, 190, 255], label: "STARTING UP", sub: "ONE MOMENT" },
    idle: { color: [150, 190, 255], label: "ONLINE", sub: "AT YOUR SERVICE" },
    listening: { color: [60, 220, 160], label: "LISTENING", sub: "GO AHEAD" },
    waiting: { color: [150, 190, 255], label: "STANDING BY", sub: "" }, // the sub line names the wake word
    thinking: { color: [140, 150, 255], label: "THINKING", sub: "ONE MOMENT" },
    tool: { color: DEFAULT_TOOL, label: "WORKING", sub: "ON IT" },
    speaking: { color: [120, 200, 255], label: "SPEAKING", sub: "" },
  };
  let wakeWord = "Jarvis";

  // ---- the drawing -------------------------------------------------------------------------------------------
  const C = 500;
  const rad = (deg) => (deg * Math.PI) / 180;
  const pt = (r, deg) => [C + r * Math.cos(rad(deg)), C + r * Math.sin(rad(deg))];
  const arc = (r, a0, a1) => {
    const [x0, y0] = pt(r, a0);
    const [x1, y1] = pt(r, a1);
    return `M${x0.toFixed(1)} ${y0.toFixed(1)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  };
  const SEGMENTS = [[-82, -4], [3, 66], [74, 156], [165, 248], [256, 296], [304, 350]];

  svg.innerHTML = `
    <defs>
      <clipPath id="disc"><circle cx="${C}" cy="${C}" r="320"/></clipPath>
      <radialGradient id="discBase" cx="50%" cy="42%" r="70%"><stop offset="0" stop-color="#26282c"/><stop offset=".65" stop-color="#0c0d0f"/><stop offset="1" stop-color="#000"/></radialGradient>
      <filter id="lift" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="34" stdDeviation="30" flood-color="#000" flood-opacity=".38"/></filter>
      <filter id="bloom" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>

    <g class="outer">
      <g class="spin slow"><circle cx="${C}" cy="${C}" r="452" class="ticks-ring"/></g>
      <g class="spin slow-rev">${[[-72, -28], [96, 128], [205, 252]].map(([a, b]) => `<path d="${arc(480, a, b)}" class="outer-arc"/>`).join("")}</g>
    </g>

    <g filter="url(#lift)"><g class="spin bezel-spin">
    <g class="bezel">
      ${SEGMENTS.map(([a, b], i) => `<path id="seg-${i}" d="${arc(375, a, b)}" class="bezel-seg"/>`).join("")}
      <circle cx="${C}" cy="${C}" r="335" class="bezel-inner"/>
    </g>
    <g id="lanes">
      ${SEGMENTS.map(([a, b], i) => `<g id="lane-${i}" class="lane"><path d="${arc(375, a + 4, b - 4)}" pathLength="100" class="lane-trail"/><path d="${arc(375, a + 4, b - 4)}" pathLength="100" class="lane-comet"/></g>`).join("")}
    </g>
    </g></g>
    <g class="bezel-detail">
      <g class="slider"><path d="${arc(398, 198, 292)}" class="slider-arc"/></g>
      <circle cx="${C}" cy="${C}" r="420" class="bezel-hair"/>
      <circle cx="${C}" cy="${C}" r="330" class="disc-hair"/>
      <g class="spin run-ring"><circle cx="${C}" cy="${C}" r="330" class="disc-run"/></g>
    </g>


    <g clip-path="url(#disc)" class="disc">
      <circle cx="${C}" cy="${C}" r="320" fill="url(#discBase)"/>
      <g class="spin faint-spin"><circle cx="${C}" cy="${C}" r="262" class="ring-faint"/></g>
      <g class="ripples"><circle cx="${C}" cy="${C}" r="120" class="ripple"/><circle cx="${C}" cy="${C}" r="120" class="ripple r2"/><circle cx="${C}" cy="${C}" r="120" class="ripple r3"/></g>
      <g class="scan"><g class="spin scan-a"><path d="${arc(292, 0, 70)}" class="scan-arc"/></g><g class="spin scan-b"><path d="${arc(248, 180, 232)}" class="scan-arc thin"/></g></g>
    </g>
    <g id="waves"></g>
  `;

  // ---- state -------------------------------------------------------------------------------------------------
  const state = { voice: null, busy: false, respondUntil: 0, alert: 0, tools: [], starting: true };
  const cur = { color: [150, 190, 255], env: 0 };
  let t = 0;
  let last = performance.now();
  let labelKey = "";
  const waves = $("waves");

  const rgb = (c) => `${c[0] | 0},${c[1] | 0},${c[2] | 0}`;
  const mix = (a, b, k) => a.map((v, i) => v + (b[i] - v) * k);

  function currentMode() {
    if (state.starting) return "starting"; // until the back end has reported in
    if (state.voice === "speaking") return "speaking";
    if (state.voice === "listening" || state.voice === "hearing") return "listening";
    if (state.voice === "waiting") return "waiting";
    if (state.tools.length) return "tool";
    if (state.busy || state.voice === "loading") return "thinking";
    return "idle";
  }

  function updateLabel(mode) {
    const def = MODES[mode];
    const sub = mode === "waiting" ? `SAY \u201c${wakeWord.toUpperCase()}\u201d` : mode === "listening" && state.voice === "hearing" ? "HEARING YOU" : def.sub;
    const key = def.label + "|" + sub;
    if (key === labelKey) return;
    labelKey = key;
    label.querySelector(".s-main").textContent = def.label;
    label.querySelector(".s-sub").textContent = sub;
    core.dataset.mode = mode;
    label.classList.remove("flash");
    void label.offsetWidth; // restart the animation
    label.classList.add("flash");
  }

  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) {
      last = now;
      return;
    }
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    t += dt;

    const mode = currentMode();
    const def = MODES[mode];
    const lead = state.tools[state.tools.length - 1];
    const k = 1 - Math.exp(-dt * 6);
    cur.color = mix(cur.color, state.alert > 0 ? RED : mode === "tool" ? toolColor(lead.name) : def.color, k);
    state.alert = Math.max(0, state.alert - dt);
    core.style.setProperty("--tc", rgb(cur.color));
    updateLabel(mode);

    drawViz(dt, mode);
  }

  // ---- the visualizer in the disc ----------------------------------------------------------------------------
  // Drawn on a canvas in a 640-unit box (the disc is 640 across): a ring of bars around a soft orb.
  const viz = $("viz");
  const vctx = viz.getContext("2d");
  let vdpr = 1;
  let vsize = 640;
  const BARS = 96;
  const BAND_COUNT = 40;
  const R0 = 196; // where the bars start
  const bars = new Float32Array(BARS);
  const audio = { bands: new Float32Array(BAND_COUNT), loud: 0, smoothLoud: 0 };
  let audioStamp = -10;

  function sizeViz() {
    vdpr = Math.min(window.devicePixelRatio || 1, 2);
    vsize = viz.getBoundingClientRect().width || 640;
    viz.width = Math.round(vsize * vdpr);
    viz.height = Math.round(vsize * vdpr);
  }
  new ResizeObserver(sizeViz).observe(viz);
  sizeViz();

  function drawViz(dt, mode) {
    const scale = (vsize / 640) * vdpr;
    vctx.setTransform(scale, 0, 0, scale, 0, 0);
    vctx.clearRect(0, 0, 640, 640);
    const speaking = state.voice === "speaking";
    // No sound has arrived for a moment, so the voice has gone quiet
    const sounding = speaking && t - audioStamp < 0.25;
    audio.smoothLoud += ((sounding ? audio.loud : 0) - audio.smoothLoud) * (1 - Math.exp(-dt * 14));
    const motion = 1;

    for (let i = 0; i < BARS; i++) {
      const around = (i / BARS) * Math.PI * 2;
      let v = 0.1 + 0.075 * motion * (Math.sin(around * 4 - t * 0.8) + Math.sin(around * 7 + t * 0.55) + 0.6 * Math.sin(around * 2 + t * 1.3)) / 2.6;
      if (speaking) {
        // Bass at the bottom, treble at the top, mirrored left and right
        const k = 1 - Math.min(i, BARS - i) / (BARS / 2);
        const position = k * (BAND_COUNT - 1);
        const low = Math.floor(position);
        const mixed = audio.bands[low] + (audio.bands[Math.min(BAND_COUNT - 1, low + 1)] - audio.bands[low]) * (position - low);
        v += sounding ? mixed * 0.95 : 0;
      } else if (mode === "thinking" || mode === "tool") {
        const heads = mode === "tool" ? [t * 3.4, t * 3.4 + Math.PI] : [t * 1.5];
        for (const head of heads) {
          const d = Math.abs((((around - head) % (Math.PI * 2)) + Math.PI * 3) % (Math.PI * 2) - Math.PI);
          v += 0.42 * Math.exp(-(d * d) / 0.18);
        }
      } else if (mode === "listening") {
        v += 0.12 + 0.1 * Math.sin(t * 3 + i * 0.3);
      }
      bars[i] += (v - bars[i]) * (1 - Math.exp(-dt * (v > bars[i] ? 40 : 11)));
    }

    const accent = cur.color;
    const lively = speaking || mode === "thinking" || mode === "tool";
    // The bars
    vctx.lineCap = "round";
    vctx.lineWidth = 4.2;
    for (let i = 0; i < BARS; i++) {
      const angle = -Math.PI / 2 + (i / BARS) * Math.PI * 2;
      const h = bars[i];
      const r2 = R0 + 5 + h * 98;
      const tint = lively ? Math.min(1, h * 1.3) : 0;
      const c = mix([255, 255, 255], accent, tint);
      vctx.strokeStyle = `rgba(${rgb(c)},${0.42 + Math.min(0.58, h * 1.1)})`;
      vctx.beginPath();
      vctx.moveTo(320 + Math.cos(angle) * R0, 320 + Math.sin(angle) * R0);
      vctx.lineTo(320 + Math.cos(angle) * r2, 320 + Math.sin(angle) * r2);
      vctx.stroke();
    }

    // Rings inside the bars, cut into dashes so their turning shows. They go in opposite directions, and the
    // outer one swells with the voice.
    const turning = (radius, count, fill, speed, width, color) => {
      const period = (Math.PI * 2 * radius) / count;
      vctx.lineWidth = width;
      vctx.strokeStyle = color;
      vctx.setLineDash([period * fill, period * (1 - fill)]);
      vctx.lineDashOffset = -t * speed * motion;
      vctx.beginPath();
      vctx.arc(320, 320, radius, 0, Math.PI * 2);
      vctx.stroke();
    };
    turning(R0 - 16 + audio.smoothLoud * 12, 24, 0.7, 26, 2.4, `rgba(${rgb(accent)},${0.6 + audio.smoothLoud * 0.4})`);
    turning(R0 - 42, 90, 0.18, -16, 3, "rgba(255,255,255,0.4)");
    turning(R0 - 70, 9, 0.35, 12, 1.6, "rgba(255,255,255,0.22)");
    vctx.setLineDash([]);
  }

  // ---- tool animation ----------------------------------------------------------------------------------------
  const lanesInUse = new Set();

  function shockwave(color) {
    const ring = document.createElementNS(NS, "circle");
    ring.setAttribute("cx", C);
    ring.setAttribute("cy", C);
    ring.setAttribute("r", 322);
    ring.setAttribute("class", "wave");
    ring.style.setProperty("--wc", rgb(color));
    waves.append(ring);
    setTimeout(() => ring.remove(), 1100);
  }

  function setCallsVisible() {
    core.classList.toggle("has-calls", calls.children.length > 0);
  }

  function addCall(item) {
    const row = document.createElement("div");
    row.className = "call running";
    row.style.setProperty("--cc", rgb(toolColor(item.name)));
    const mark = document.createElement("i");
    const name = document.createElement("b");
    name.textContent = item.name.toUpperCase();
    const info = document.createElement("small");
    info.textContent = Object.entries(item.input || {})
      .slice(0, 2)
      .map(([key, value]) => `${key} ${typeof value === "string" ? value : JSON.stringify(value)}`)
      .join("  ·  ");
    row.append(mark, name, info);
    calls.append(row);
    while (calls.children.length > 3) calls.firstElementChild.remove();
    item.row = row;
    setCallsVisible();
  }

  function finishCall(item, ok, seconds) {
    const row = item.row;
    if (!row) return;
    row.className = `call ${ok ? "done" : "error"}`;
    row.querySelector("small").textContent = seconds == null ? (ok ? "DONE" : "FAILED") : `${seconds.toFixed(1)} S`;
    setTimeout(() => row.classList.add("leaving"), 1500);
    setTimeout(() => {
      row.remove();
      setCallsVisible();
    }, 2100);
  }

  function lightLane(item) {
    const index = [...Array(SEGMENTS.length).keys()].find((i) => !lanesInUse.has(i)) ?? item.id % SEGMENTS.length;
    lanesInUse.add(index);
    item.lane = index;
    const lane = $(`lane-${index}`);
    lane.setAttribute("class", "lane running");
    lane.style.setProperty("--lc", rgb(toolColor(item.name)));
    $(`seg-${index}`).classList.add("active");
  }

  function settleLane(item, ok) {
    const lane = $(`lane-${item.lane}`);
    lane.style.setProperty("--lc", rgb(ok ? GREEN : RED));
    lane.setAttribute("class", `lane ${ok ? "done" : "error"}`);
    setTimeout(() => {
      lane.setAttribute("class", "lane");
      $(`seg-${item.lane}`).classList.remove("active");
      lanesInUse.delete(item.lane);
    }, 1300);
  }

  // ---- what the app calls ------------------------------------------------------------------------------------
  let counter = 0;
  window.Face = {
    color: (name) => toolColor(name).join(","),
    set(patch) {
      Object.assign(state, patch);
    },
    toolStart(name, server, input) {
      const item = { name, server, input, id: ++counter };
      state.tools.push(item);
      shockwave(toolColor(name));
      lightLane(item);
      addCall(item);
    },
    toolEnd(name, ok, seconds) {
      const index = state.tools.findIndex((item) => item.name === name);
      if (index < 0) return;
      const [item] = state.tools.splice(index, 1);
      shockwave(ok ? GREEN : RED);
      settleLane(item, ok);
      finishCall(item, ok, seconds);
    },
    setWakeWord(word) {
      if (word) wakeWord = word;
    },
    // A slice of the voice about to be heard: spectrum bands (bass first) and overall loudness, from 0 to 1.
    // `delay` is how many seconds it takes to reach the speakers, so the picture lines up with the sound.
    levels({ bands, loudness, delay }) {
      setTimeout(() => {
        for (let i = 0; i < BAND_COUNT; i++) audio.bands[i] = bands[i] ?? 0;
        audio.loud = loudness;
        audioStamp = t;
      }, Math.max(0, (delay || 0) * 1000));
    },
    alert() {
      state.alert = 1.2;
      shockwave(RED);
    },
  };

  requestAnimationFrame(frame);
})();
