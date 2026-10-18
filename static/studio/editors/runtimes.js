(function (root) {
  function walkValue(visual, walk, startId, dotted) {
    const node = walk(visual, startId, dotted);
    if (!node || !node.properties) return "";
    return node.properties.has_value ? node.properties.value : "";
  }

  function num(visual, walk, rec, key, fallback) {
    const n = Number(walkValue(visual, walk, rec.id, key));
    return Number.isFinite(n) ? n : fallback;
  }

  function str(visual, walk, rec, key, fallback) {
    const v = walkValue(visual, walk, rec.id, key);
    return v === "" || v == null ? fallback : String(v);
  }

  function clearMount(mount) {
    if (!mount) return;
    if (mount._raf) {
      root.cancelAnimationFrame(mount._raf);
      mount._raf = 0;
    }
    mount.textContent = "";
  }

  function playing(mount) {
    const host = mount && mount.closest && mount.closest("[data-playing]");
    if (!host) return true;
    return host.getAttribute("data-playing") !== "0";
  }

  function arrayLength(visual, walk, startId, dotted) {
    const node = walk(visual, startId, dotted);
    if (!node || node.kind !== "array") return 0;
    return Number(node.properties && node.properties.length) || 0;
  }

  function childRecords(visual, walk, startId, dotted) {
    const node = walk(visual, startId, dotted);
    if (!node) return [];
    return ((visual && visual.edges) || [])
      .filter(function (edge) {
        return edge.source === node.id;
      })
      .map(function (edge) {
        return ((visual.nodes || []).find(function (item) {
          return item.id === edge.target;
        }) || null);
      })
      .filter(Boolean);
  }

  function addCanvas(mount, w, h) {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.className = "me-runtime-canvas me-runtime-canvas--wide";
    mount.appendChild(canvas);
    return canvas.getContext("2d");
  }

  function addPre(mount, text) {
    const pre = document.createElement("pre");
    pre.className = "me-runtime-pre";
    pre.textContent = text;
    mount.appendChild(pre);
    return pre;
  }

  function project(x, y, z, cam) {
    const cz = z - (cam.z || 8);
    const f = (cam.fov || 60) * 0.02;
    const d = Math.max(0.4, -cz * f + 1.2);
    return { x: 180 + (x - (cam.x || 0)) * 28 * d, y: 130 - (y - (cam.y || 0)) * 28 * d, s: d };
  }

  function drawGrid(g, w, h, on) {
    g.fillStyle = "#141418";
    g.fillRect(0, 0, w, h);
    if (!on) return;
    g.strokeStyle = "#2a2a32";
    g.lineWidth = 1;
    for (let i = 0; i <= 12; i += 1) {
      g.beginPath();
      g.moveTo(20, 20 + i * ((h - 40) / 12));
      g.lineTo(w - 20, 20 + i * ((h - 40) / 12));
      g.stroke();
      g.beginPath();
      g.moveTo(20 + i * ((w - 40) / 12), 20);
      g.lineTo(20 + i * ((w - 40) / 12), h - 20);
      g.stroke();
    }
    g.strokeStyle = "#c44";
    g.beginPath();
    g.moveTo(20, h / 2);
    g.lineTo(w - 20, h / 2);
    g.stroke();
    g.strokeStyle = "#4a4";
    g.beginPath();
    g.moveTo(w / 2, 20);
    g.lineTo(w / 2, h - 20);
    g.stroke();
  }

  function drawGizmo(g, ox, oy) {
    g.strokeStyle = "#e55";
    g.beginPath();
    g.moveTo(ox, oy);
    g.lineTo(ox + 36, oy);
    g.stroke();
    g.strokeStyle = "#5d5";
    g.beginPath();
    g.moveTo(ox, oy);
    g.lineTo(ox, oy - 36);
    g.stroke();
    g.strokeStyle = "#59f";
    g.beginPath();
    g.moveTo(ox, oy);
    g.lineTo(ox + 18, oy - 18);
    g.stroke();
  }

  function drawMesh(g, mesh, p, size) {
    const s = size * (p.s || 1);
    g.strokeStyle = "#dde";
    g.lineWidth = 1.5;
    if (mesh === "sphere") {
      g.beginPath();
      g.arc(p.x, p.y, s, 0, Math.PI * 2);
      g.stroke();
      g.beginPath();
      g.ellipse(p.x, p.y, s, s * 0.35, 0, 0, Math.PI * 2);
      g.stroke();
    } else if (mesh === "plane") {
      g.strokeRect(p.x - s * 1.4, p.y - 4, s * 2.8, 8);
    } else if (mesh === "cylinder" || mesh === "capsule") {
      g.strokeRect(p.x - s * 0.5, p.y - s, s, s * 2);
      g.beginPath();
      g.ellipse(p.x, p.y - s, s * 0.5, 6, 0, 0, Math.PI * 2);
      g.stroke();
    } else {
      g.strokeRect(p.x - s, p.y - s, s * 2, s * 2);
      g.beginPath();
      g.moveTo(p.x - s, p.y - s);
      g.lineTo(p.x, p.y - s * 1.6);
      g.lineTo(p.x + s, p.y - s);
      g.stroke();
    }
  }

  function gridOn(mount) {
    const box = mount.closest && mount.closest("[data-viewport]");
    const el = box && box.querySelector("[data-viewport-grid]");
    return !el || el.checked;
  }

  function gizmoOn(mount) {
    const box = mount.closest && mount.closest("[data-viewport]");
    const el = box && box.querySelector("[data-viewport-gizmo]");
    return !el || el.checked;
  }

  function hostTool(mount) {
    const host = mount && mount.closest && mount.closest("[data-tool]");
    return (host && host.getAttribute("data-tool")) || "";
  }

  function writeDotted(ctx, visual, walk, rec, dotted, typeName, raw) {
    if (!ctx || typeof ctx.applyVisual !== "function" || !rec) return;
    const node = walk(visual, rec.id, dotted);
    if (!node || node.kind !== "literal") return;
    const next = JSON.parse(JSON.stringify(visual));
    next.nodes = (next.nodes || []).map(function (item) {
      if (item.id !== node.id) return item;
      const stored = typeName || (item.properties || {}).type || "float";
      let value = raw;
      if (stored === "int") value = parseInt(raw, 10) || 0;
      else if (stored === "float") value = parseFloat(raw) || 0;
      else if (stored === "bool") value = raw === true || raw === "true" || raw === "1";
      return Object.assign({}, item, {
        properties: Object.assign({}, item.properties || {}, { has_value: true, type: stored, value: value }),
      });
    });
    ctx.applyVisual(next);
  }

  function writeMerge(ctx, field, desc) {
    if (!ctx || typeof ctx.applyCode !== "function") return;
    ctx.applyCode(desc, { merge: true, field: field });
  }

  function shader(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const source = str(visual, walk, rec, "glsl", "void main() { gl_FragColor = vec4(1.0); }");
    const precision = str(visual, walk, rec, "precision", "mediump");
    const vertex = str(
      visual,
      walk,
      rec,
      "vertex",
      "attribute vec2 a; void main() { gl_Position = vec4(a, 0.0, 1.0); }"
    );
    const canvas = document.createElement("canvas");
    canvas.width = 320;
    canvas.height = 200;
    canvas.className = "me-runtime-canvas me-runtime-canvas--wide";
    mount.appendChild(canvas);
    const gl = canvas.getContext("webgl");
    if (!gl) {
      addPre(mount, "WebGL unavailable");
      return;
    }
    function compile(type, src) {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      const ok = gl.getShaderParameter(sh, gl.COMPILE_STATUS);
      return { shader: sh, log: ok ? "" : gl.getShaderInfoLog(sh) || "compile error" };
    }
    const vs = compile(gl.VERTEX_SHADER, vertex);
    const fs = compile(gl.FRAGMENT_SHADER, "precision " + precision + " float;\n" + source);
    if (vs.log || fs.log) {
      addPre(mount, (vs.log || "") + "\n" + (fs.log || ""));
      return;
    }
    const prog = gl.createProgram();
    gl.attachShader(prog, vs.shader);
    gl.attachShader(prog, fs.shader);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      addPre(mount, gl.getProgramInfoLog(prog) || "link error");
      return;
    }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a");
    if (loc >= 0) {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    }
    const timeLoc = gl.getUniformLocation(prog, "u_time");
    const colorLoc = gl.getUniformLocation(prog, "u_color");
    const t0 = Date.now();
    function tick() {
      const t = (Date.now() - t0) / 1000;
      if (timeLoc) gl.uniform1f(timeLoc, t);
      if (colorLoc) gl.uniform4f(colorLoc, 1, 1, 1, 1);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (playing(mount)) mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    addPre(mount, precision + " · uniforms u_time / u_color");
  }

  function quantum(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const n = Math.max(1, Math.min(5, parseInt(walkValue(visual, walk, rec.id, "qubit"), 10) || 1));
    const dim = 1 << n;
    const amps = new Array(dim).fill(0);
    amps[0] = 1;
    const gate = str(visual, walk, rec, "hadamard", "q0");
    const q = Math.max(0, parseInt(String(gate).replace(/\D/g, ""), 10) || 0);
    if (q < n) {
      const next = amps.slice();
      const inv = 1 / Math.SQRT2;
      for (let i = 0; i < dim; i += 1) {
        if (((i >> q) & 1) === 0) {
          const j = i | (1 << q);
          const a = amps[i];
          const b = amps[j];
          next[i] = inv * (a + b);
          next[j] = inv * (a - b);
        }
      }
      for (let i = 0; i < dim; i += 1) amps[i] = next[i];
    }
    const g = addCanvas(mount, 320, 120);
    g.fillStyle = "#111";
    g.fillRect(0, 0, 320, 120);
    const barW = 300 / dim;
    amps.forEach(function (amp, i) {
      g.fillStyle = "#6af";
      g.fillRect(10 + i * barW, 110 - Math.abs(amp) * 90, Math.max(2, barW - 2), Math.abs(amp) * 90);
    });
    g.strokeStyle = "#8af";
    g.beginPath();
    g.arc(292, 28, 16, 0, Math.PI * 2);
    g.stroke();
    g.beginPath();
    g.moveTo(292, 28);
    g.lineTo(292 + (amps[0] || 0) * 12, 28 - (amps[1] || 0) * 12);
    g.stroke();
    addPre(
      mount,
      amps
        .map(function (amp, i) {
          return "|" + i.toString(2).padStart(n, "0") + "> " + amp.toFixed(3);
        })
        .join("\n")
    );
  }

  function map(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const lat = num(visual, walk, rec, "lat", 0);
    const lng = num(visual, walk, rec, "lng", 0);
    const zoom = num(visual, walk, rec, "zoom", 2);
    const g = addCanvas(mount, 320, 200);
    g.fillStyle = "#c5dcc8";
    g.fillRect(0, 0, 320, 200);
    g.strokeStyle = "#385";
    const cells = Math.max(4, Math.min(16, zoom * 2));
    for (let i = 0; i <= cells; i += 1) {
      g.beginPath();
      g.moveTo((i * 320) / cells, 0);
      g.lineTo((i * 320) / cells, 200);
      g.moveTo(0, (i * 200) / cells);
      g.lineTo(320, (i * 200) / cells);
      g.stroke();
    }
    const x = ((lng + 180) / 360) * 320;
    const y = ((90 - lat) / 180) * 200;
    g.fillStyle = "#c00";
    g.beginPath();
    g.arc(x, y, 6, 0, Math.PI * 2);
    g.fill();
    addPre(mount, lat.toFixed(4) + ", " + lng.toFixed(4) + " · z" + zoom + " · " + str(visual, walk, rec, "tile", "osm"));
  }

  function bitmap(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const w = Math.max(32, Math.min(256, parseInt(walkValue(visual, walk, rec.id, "width"), 10) || 128));
    const h = Math.max(32, Math.min(256, parseInt(walkValue(visual, walk, rec.id, "height"), 10) || 128));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.className = "me-runtime-canvas";
    const g = canvas.getContext("2d");
    const cols = 16;
    const cw = w / cols;
    const ch = h / cols;
    g.fillStyle = "#111";
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#eee";
    for (let y = 0; y < cols; y += 1) {
      for (let x = 0; x < cols; x += 1) {
        if ((x + y) % 2 === 0) g.fillRect(x * cw, y * ch, cw, ch);
      }
    }
    canvas.addEventListener("pointerdown", function (event) {
      const rect = canvas.getBoundingClientRect();
      const x = Math.floor(((event.clientX - rect.left) / rect.width) * cols);
      const y = Math.floor(((event.clientY - rect.top) / rect.height) * cols);
      g.fillStyle = "#4af";
      g.fillRect(x * cw, y * ch, cw, ch);
    });
    mount.appendChild(canvas);
    addPre(mount, str(visual, walk, rec, "src", "hero.png") + " · " + w + "×" + h);
  }

  function audio(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const g = addCanvas(mount, 320, 80);
    const hz = num(visual, walk, rec, "hz", 441);
    const gain = num(visual, walk, rec, "gain", 0.2);
    const pitch = num(visual, walk, rec, "pitch", 1);
    g.fillStyle = "#111";
    g.fillRect(0, 0, 320, 80);
    g.strokeStyle = "#6af";
    g.beginPath();
    for (let x = 0; x < 320; x += 1) {
      const y = 40 + Math.sin((x / 320) * Math.PI * 8 * pitch) * 28 * Math.min(1, gain);
      if (x === 0) g.moveTo(x, y);
      else g.lineTo(x, y);
    }
    g.stroke();
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "me-btn";
    btn.textContent = "Play tone";
    btn.addEventListener("click", function () {
      const ctxAudio = new (root.AudioContext || root.webkitAudioContext)();
      const osc = ctxAudio.createOscillator();
      const gn = ctxAudio.createGain();
      osc.frequency.value = hz * pitch;
      gn.gain.value = Math.min(1, Math.max(0, gain));
      osc.connect(gn);
      gn.connect(ctxAudio.destination);
      osc.start();
      root.setTimeout(function () {
        osc.stop();
        ctxAudio.close();
      }, 400);
    });
    mount.appendChild(btn);
  }

  function particle(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const n = Math.max(4, Math.min(200, parseInt(walkValue(visual, walk, rec.id, "emit"), 10) || 16));
    const life = num(visual, walk, rec, "lifetime", 1);
    const speed = num(visual, walk, rec, "speed", 1);
    const grav = num(visual, walk, rec, "gravity", 0.2);
    const g = addCanvas(mount, 320, 180);
    const parts = [];
    for (let i = 0; i < n; i += 1) {
      parts.push({ x: 160, y: 160, vx: (Math.random() - 0.5) * 4 * speed, vy: -Math.random() * 6 * speed, t: Math.random() * life });
    }
    function tick() {
      g.fillStyle = "rgba(10,10,12,0.35)";
      g.fillRect(0, 0, 320, 180);
      g.fillStyle = "#fc6";
      parts.forEach(function (p) {
        if (!playing(mount)) return;
        p.vy += grav * 0.15;
        p.x += p.vx;
        p.y += p.vy;
        p.t -= 0.016;
        if (p.t <= 0 || p.y > 180) {
          p.x = 160;
          p.y = 160;
          p.vx = (Math.random() - 0.5) * 4 * speed;
          p.vy = -Math.random() * 6 * speed;
          p.t = life;
        }
        g.fillRect(p.x, p.y, 2, 2);
      });
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
  }

  function terrain(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const height = num(visual, walk, rec, "height", 12);
    const noise = num(visual, walk, rec, "noise", 0.4);
    const octaves = Math.max(1, Math.min(6, parseInt(walkValue(visual, walk, rec.id, "octaves"), 10) || 2));
    const seed = num(visual, walk, rec, "seed", 1);
    const g = addCanvas(mount, 320, 140);
    g.fillStyle = "#9cf";
    g.fillRect(0, 0, 320, 140);
    g.fillStyle = "#3a4";
    g.beginPath();
    g.moveTo(0, 140);
    for (let x = 0; x <= 320; x += 2) {
      let y = 0;
      for (let o = 0; o < octaves; o += 1) {
        const f = Math.pow(2, o);
        y += Math.sin((x + seed * 13) * noise * 0.04 * f) * (18 / f);
      }
      g.lineTo(x, 140 - (height + y));
    }
    g.lineTo(320, 140);
    g.fill();
  }

  function scene(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const mesh = str(visual, walk, rec, "mesh", "cube");
    const cam = {
      x: num(visual, walk, rec, "camera.x", 0),
      y: num(visual, walk, rec, "camera.y", 0),
      z: num(visual, walk, rec, "camera.z", 8),
      fov: num(visual, walk, rec, "camera.fov", 60),
    };
    const px = num(visual, walk, rec, "transform.px", 0);
    const py = num(visual, walk, rec, "transform.py", 0);
    const pz = num(visual, walk, rec, "transform.pz", 0);
    const sx = num(visual, walk, rec, "transform.sx", 1);
    const lightI = num(visual, walk, rec, "light.intensity", 1);
    const duration = Math.max(0.1, num(visual, walk, rec, "duration", 2));
    const keys = childRecords(visual, walk, rec.id, "keyframes").map(function (row) {
      return {
        t: Number(walkValue(visual, walk, row.id, "t")) || 0,
        px: Number(walkValue(visual, walk, row.id, "px")) || 0,
        py: Number(walkValue(visual, walk, row.id, "py")) || 0,
        pz: Number(walkValue(visual, walk, row.id, "pz")) || 0,
        easing: walkValue(visual, walk, row.id, "easing") || "linear",
        c1x: Number(walkValue(visual, walk, row.id, "c1x")),
        c1y: Number(walkValue(visual, walk, row.id, "c1y")),
        c2x: Number(walkValue(visual, walk, row.id, "c2x")),
        c2y: Number(walkValue(visual, walk, row.id, "c2y")),
      };
    });
    const g = addCanvas(mount, 360, 260);
    let t = 0;
    const dt = 1 / 60;
    function tick() {
      if (playing(mount)) t += dt;
      if (t > duration) t = 0;
      const solvers = root.ZintriqSolvers;
      const source = keys.length
        ? keys
        : [
            { t: 0, px: px, py: py, pz: pz },
            { t: duration, px: px, py: py, pz: pz },
          ];
      const played =
        playing(mount) && solvers && solvers.playKeys
          ? solvers.playKeys(source, t)
          : { px: px, py: py, pz: pz };
      drawGrid(g, 360, 260, gridOn(mount));
      const p = project(played.px || px, played.py || py, played.pz || pz, cam);
      g.globalAlpha = Math.min(1, 0.35 + lightI * 0.5);
      drawMesh(g, mesh, p, 28 * sx);
      g.globalAlpha = 1;
      if (gizmoOn(mount)) drawGizmo(g, p.x, p.y);
      const lx = num(visual, walk, rec, "light.x", 2);
      const ly = num(visual, walk, rec, "light.y", 4);
      const lp = project(lx, ly, 0, cam);
      g.fillStyle = "#ffd";
      g.beginPath();
      g.arc(lp.x, lp.y, 4, 0, Math.PI * 2);
      g.fill();
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    const canvas = mount.querySelector("canvas");
    if (canvas) {
      canvas.style.cursor = "grab";
      let drag = null;
      canvas.addEventListener("pointerdown", function (ev) {
        if (playing(mount)) return;
        const tool = hostTool(mount) || "move";
        drag = { tool: tool, x: ev.offsetX, y: ev.offsetY, px: px, py: py, sx: sx, cx: cam.x, cy: cam.y, cz: cam.z };
        canvas.setPointerCapture(ev.pointerId);
      });
      canvas.addEventListener("pointermove", function (ev) {
        if (!drag || playing(mount)) return;
        const dx = (ev.offsetX - drag.x) / 40;
        const dy = (drag.y - ev.offsetY) / 40;
        if (drag.tool === "camera" || ev.altKey) {
          writeDotted(ctx, visual, walk, rec, "camera.x", "float", drag.cx - dx);
          writeDotted(ctx, visual, walk, rec, "camera.y", "float", drag.cy - dy);
        } else if (drag.tool === "scale") {
          writeDotted(ctx, visual, walk, rec, "transform.sx", "float", Math.max(0.05, drag.sx + dx));
        } else if (drag.tool === "rotate") {
          writeDotted(ctx, visual, walk, rec, "transform.rz", "float", dx);
        } else {
          writeDotted(ctx, visual, walk, rec, "transform.px", "float", drag.px + dx);
          writeDotted(ctx, visual, walk, rec, "transform.py", "float", drag.py + dy);
        }
      });
      canvas.addEventListener("pointerup", function () {
        if (drag && drag.tool === "move" && !playing(mount) && ctx && typeof ctx.applyCode === "function") {
          const lastEase = keys.length ? keys[keys.length - 1] : { easing: "linear", c1x: 0.25, c1y: 0.1, c2x: 0.25, c2y: 1 };
          const nextKeys = keys.concat([{
            t: t,
            px: num(visual, walk, rec, "transform.px", drag.px),
            py: num(visual, walk, rec, "transform.py", drag.py),
            pz: pz,
            easing: lastEase.easing || "linear",
            c1x: lastEase.c1x,
            c1y: lastEase.c1y,
            c2x: lastEase.c2x,
            c2y: lastEase.c2y,
          }]);
          writeMerge(ctx, "keyframes", {
            form: "sequence",
            items: nextKeys.map(function (key) {
              return {
                form: "struct",
                fields: {
                  t: { form: "atom", type: "float", value: Number(key.t) || 0 },
                  px: { form: "atom", type: "float", value: Number(key.px) || 0 },
                  py: { form: "atom", type: "float", value: Number(key.py) || 0 },
                  pz: { form: "atom", type: "float", value: Number(key.pz) || 0 },
                  easing: { form: "atom", type: "string", value: String(key.easing || "linear") },
                  c1x: { form: "atom", type: "float", value: Number.isFinite(Number(key.c1x)) ? Number(key.c1x) : 0.25 },
                  c1y: { form: "atom", type: "float", value: Number.isFinite(Number(key.c1y)) ? Number(key.c1y) : 0.1 },
                  c2x: { form: "atom", type: "float", value: Number.isFinite(Number(key.c2x)) ? Number(key.c2x) : 0.25 },
                  c2y: { form: "atom", type: "float", value: Number.isFinite(Number(key.c2y)) ? Number(key.c2y) : 1 },
                },
              };
            }),
          });
        }
        drag = null;
      });
    }
    addPre(
      mount,
      "hierarchy · camera · lights · " +
        mesh +
        " · fov " +
        cam.fov +
        " · objs " +
        arrayLength(visual, walk, rec.id, "objects") +
        " · instances " +
        arrayLength(visual, walk, rec.id, "instances") +
        " · play/stop · prefab · Move samples keyframes · Play reads Desc"
    );
  }

  function model3d(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const mesh = str(visual, walk, rec, "mesh", "body");
    const lod = str(visual, walk, rec, "lod", "high");
    const scale = num(visual, walk, rec, "scale", 1);
    const rx = num(visual, walk, rec, "rx", 0);
    const g = addCanvas(mount, 320, 220);
    let t = 0;
    function tick() {
      t += playing(mount) ? 0.02 : 0;
      drawGrid(g, 320, 220, gridOn(mount));
      const cam = { x: 0, y: 0, z: 8, fov: 55 };
      const p = project(Math.sin(t + rx) * 0.2, 0, 0, cam);
      drawMesh(g, mesh === "body" ? "cube" : mesh, p, 32 * scale);
      if (gizmoOn(mount)) drawGizmo(g, p.x, p.y);
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    addPre(mount, str(visual, walk, rec, "gltf", "model.gltf") + " · lod " + lod);
  }

  function material(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    let albedo = str(visual, walk, rec, "albedo", "#888888");
    if (!/^#/.test(albedo)) albedo = "#888888";
    const metal = num(visual, walk, rec, "metal", 0);
    const rough = num(visual, walk, rec, "rough", 0.5);
    const emit = num(visual, walk, rec, "emission", 0);
    const g = addCanvas(mount, 280, 140);
    const grd = g.createRadialGradient(110, 50, 10, 140, 70, 90);
    grd.addColorStop(0, albedo);
    grd.addColorStop(1, "#111");
    g.fillStyle = grd;
    g.beginPath();
    g.arc(140, 70, 54, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "rgba(255,255,255," + (metal * 0.5).toFixed(2) + ")";
    g.beginPath();
    g.arc(120, 50, 18, 0, Math.PI * 2);
    g.fill();
    g.globalAlpha = rough;
    g.strokeStyle = "#000";
    for (let i = 0; i < 12; i += 1) g.strokeRect(90 + i * 3, 40 + i, 2, 2);
    g.globalAlpha = 1;
    if (emit > 0) {
      g.strokeStyle = "rgba(255,220,120," + emit + ")";
      g.lineWidth = 6;
      g.beginPath();
      g.arc(140, 70, 58, 0, Math.PI * 2);
      g.stroke();
    }
    addPre(mount, "M " + metal.toFixed(2) + "  R " + rough.toFixed(2) + "  E " + emit.toFixed(2));
  }

  function circuit(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const solvers = root.ZintriqSolvers;
    const gate = str(visual, walk, rec, "gate", "and");
    const clk = num(visual, walk, rec, "clock", 1);
    const nets = childRecords(visual, walk, rec.id, "nets");
    const clearance = num(visual, walk, rec, "clearance", 4);
    const minWidth = num(visual, walk, rec, "min_width", 0.15);
    function pinXY(name, index) {
      const label = String(name || "").toLowerCase();
      if (label === "in") return [24, 70];
      if (label === "out") return [296, 70];
      if (label === "gate") return [135, 70];
      return [24, 36 + index * 28];
    }
    const traces = [];
    if (nets.length) {
      nets.forEach(function (row, i) {
        const from = walkValue(visual, walk, row.id, "from") || "in";
        const to = walkValue(visual, walk, row.id, "to") || "out";
        const a = pinXY(from, i);
        const b = pinXY(to, i);
        traces.push({
          net: walkValue(visual, walk, row.id, "name") || "n" + (i + 1),
          from: from,
          to: to,
          layer: Number(walkValue(visual, walk, row.id, "layer")) || 0,
          width: minWidth,
          path: solvers ? solvers.manhattanRoute(a[0], a[1], b[0], b[1]) : [a, b],
        });
      });
    } else {
      traces.push({
        net: str(visual, walk, rec, "net", "n1"),
        width: minWidth,
        layer: 0,
        path: solvers ? solvers.manhattanRoute(24, 70, 296, 70) : [[24, 70], [296, 70]],
      });
    }
    const vias = [];
    nets.forEach(function (row) {
      const netName = walkValue(visual, walk, row.id, "name") || "n1";
      childRecords(visual, walk, row.id, "via").forEach(function (via) {
        vias.push({
          net: netName,
          x: Number(walkValue(visual, walk, via.id, "x")) || 0,
          y: Number(walkValue(visual, walk, via.id, "y")) || 0,
          from_layer: Number(walkValue(visual, walk, via.id, "from_layer")) || 0,
          to_layer: Number(walkValue(visual, walk, via.id, "to_layer")) || 0,
        });
      });
    });
    childRecords(visual, walk, rec.id, "vias").forEach(function (via) {
      vias.push({
        net: walkValue(visual, walk, via.id, "net") || "n1",
        x: Number(walkValue(visual, walk, via.id, "x")) || 0,
        y: Number(walkValue(visual, walk, via.id, "y")) || 0,
        from_layer: Number(walkValue(visual, walk, via.id, "from_layer")) || 0,
        to_layer: Number(walkValue(visual, walk, via.id, "to_layer")) || 0,
      });
    });
    const keepouts = childRecords(visual, walk, rec.id, "keepout").map(function (row) {
      const points = childRecords(visual, walk, row.id, "points").map(function (pt) {
        return { x: Number(walkValue(visual, walk, pt.id, "x")) || 0, y: Number(walkValue(visual, walk, pt.id, "y")) || 0 };
      });
      const holes = childRecords(visual, walk, row.id, "holes").map(function (hole) {
        return {
          points: childRecords(visual, walk, hole.id, "points").map(function (pt) {
            return { x: Number(walkValue(visual, walk, pt.id, "x")) || 0, y: Number(walkValue(visual, walk, pt.id, "y")) || 0 };
          }),
        };
      });
      return {
        layer: Number(walkValue(visual, walk, row.id, "layer")) || 0,
        x0: Number(walkValue(visual, walk, row.id, "x0")),
        y0: Number(walkValue(visual, walk, row.id, "y0")),
        x1: Number(walkValue(visual, walk, row.id, "x1")),
        y1: Number(walkValue(visual, walk, row.id, "y1")),
        x2: Number(walkValue(visual, walk, row.id, "x2")),
        y2: Number(walkValue(visual, walk, row.id, "y2")),
        x3: Number(walkValue(visual, walk, row.id, "x3")),
        y3: Number(walkValue(visual, walk, row.id, "y3")),
        points: points,
        holes: holes,
      };
    });
    const issues = solvers ? solvers.routeDrc(traces, clearance, minWidth, vias, keepouts) : [];
    const g = addCanvas(mount, 320, 140);
    let t = 0;
    function tick() {
      t += playing(mount) ? 0.05 * clk : 0;
      g.fillStyle = "#f7f7f4";
      g.fillRect(0, 0, 320, 140);
      g.strokeStyle = "#222";
      g.strokeRect(90, 46, 90, 48);
      g.fillStyle = "#222";
      g.font = "12px ui-monospace, monospace";
      g.fillText(gate.toUpperCase(), 108, 74);
      keepouts.forEach(function (zone) {
        const pts = solvers && solvers.keepoutPoints ? solvers.keepoutPoints(zone) : [];
        if (pts.length < 3) return;
        const layer = Number(zone.layer) || 0;
        const drawKey = "draw_l" + String(layer);
        const flag = walkValue(visual, walk, rec.id, drawKey);
        if (flag === false || flag === "false" || flag === 0 || flag === "0") return;
        g.fillStyle = layer ? "rgba(180,90,40,0.28)" : "rgba(40,90,180,0.28)";
        g.beginPath();
        pts.forEach(function (pt, i) {
          if (i === 0) g.moveTo(pt[0], pt[1]);
          else g.lineTo(pt[0], pt[1]);
        });
        g.closePath();
        const holes = solvers && solvers.keepoutHoles ? solvers.keepoutHoles(zone) : [];
        holes.forEach(function (hole) {
          hole.forEach(function (pt, i) {
            if (i === 0) g.moveTo(pt[0], pt[1]);
            else g.lineTo(pt[0], pt[1]);
          });
          g.closePath();
        });
        g.fill("evenodd");
      });
      traces.forEach(function (trace, i) {
        const path = trace.path || trace;
        g.strokeStyle = issues.length ? "#c33" : i ? "#36a" : "#222";
        g.lineWidth = Math.max(1, (trace.width || minWidth) * 8);
        g.beginPath();
        path.forEach(function (pt, pi) {
          if (pi === 0) g.moveTo(pt[0], pt[1]);
          else g.lineTo(pt[0], pt[1]);
        });
        g.stroke();
      });
      const on = Math.sin(t) > 0;
      g.fillStyle = on ? "#3c3" : "#999";
      g.fillRect(24, 62, 10, 16);
      g.fillRect(286, 62, 10, 16);
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    const canvas = mount.querySelector("canvas");
    if (canvas) {
      canvas.addEventListener("pointerdown", function (ev) {
        if ((hostTool(mount) || "route") !== "route") return;
        const rows = traces.map(function (trace) {
          const path = trace.path || [];
          return {
            form: "struct",
            fields: {
              name: { form: "atom", type: "string", value: String(trace.net || "n1") },
              from: { form: "atom", type: "string", value: String(trace.from || "in") },
              to: { form: "atom", type: "string", value: String(trace.to || "out") },
              layer: { form: "atom", type: "int", value: Number(trace.layer) || 0 },
              via: {
                form: "sequence",
                items: vias
                  .filter(function (via) {
                    return via.net === trace.net;
                  })
                  .map(function (via) {
                    return {
                      form: "struct",
                      fields: {
                        x: { form: "atom", type: "float", value: Number(via.x) || 0 },
                        y: { form: "atom", type: "float", value: Number(via.y) || 0 },
                        from_layer: { form: "atom", type: "int", value: Number(via.from_layer) || 0 },
                        to_layer: { form: "atom", type: "int", value: Number(via.to_layer) || 0 },
                      },
                    };
                  }),
              },
              path: {
                form: "sequence",
                items: path.map(function (pt) {
                  return {
                    form: "struct",
                    fields: {
                      x: { form: "atom", type: "float", value: pt[0] },
                      y: { form: "atom", type: "float", value: pt[1] },
                    },
                  };
                }),
              },
            },
          };
        });
        writeMerge(ctx, "nets", { form: "sequence", items: rows });
        writeMerge(ctx, "vias", {
          form: "sequence",
          items: vias.map(function (via) {
            return {
              form: "struct",
              fields: {
                net: { form: "atom", type: "string", value: String(via.net || "n1") },
                x: { form: "atom", type: "float", value: Number(via.x) || 0 },
                y: { form: "atom", type: "float", value: Number(via.y) || 0 },
                from_layer: { form: "atom", type: "int", value: Number(via.from_layer) || 0 },
                to_layer: { form: "atom", type: "int", value: Number(via.to_layer) || 0 },
              },
            };
          }),
        });
        writeMerge(ctx, "keepout", {
          form: "sequence",
          items: keepouts.map(function (zone) {
            const pts = zone.points && zone.points.length
              ? zone.points
              : [
                  { x: zone.x0, y: zone.y0 },
                  { x: zone.x1, y: zone.y1 },
                  { x: zone.x2, y: zone.y2 },
                  { x: zone.x3, y: zone.y3 },
                ].filter(function (pt) { return Number.isFinite(Number(pt.x)) && Number.isFinite(Number(pt.y)); });
            return {
              form: "struct",
              fields: {
                layer: { form: "atom", type: "int", value: Number(zone.layer) || 0 },
                points: {
                  form: "sequence",
                  items: pts.map(function (pt) {
                    return {
                      form: "struct",
                      fields: {
                        x: { form: "atom", type: "float", value: Number(pt.x) || 0 },
                        y: { form: "atom", type: "float", value: Number(pt.y) || 0 },
                      },
                    };
                  }),
                },
                holes: {
                  form: "sequence",
                  items: (zone.holes || []).map(function (hole) {
                    const holePts = (hole && hole.points) || [];
                    return {
                      form: "struct",
                      fields: {
                        points: {
                          form: "sequence",
                          items: holePts.map(function (pt) {
                            return {
                              form: "struct",
                              fields: {
                                x: { form: "atom", type: "float", value: Number(pt.x) || 0 },
                                y: { form: "atom", type: "float", value: Number(pt.y) || 0 },
                              },
                            };
                          }),
                        },
                      },
                    };
                  }),
                },
              },
            };
          }),
        });
        writeMerge(ctx, "drc", {
          form: "sequence",
          items: (issues || []).map(function (hit) {
            const row = hit && typeof hit === "object" ? hit : { layer: 0, issue: String(hit) };
            return {
              form: "struct",
              fields: {
                layer: { form: "atom", type: "int", value: Number(row.layer) || 0 },
                from_layer: { form: "atom", type: "int", value: Number(row.from_layer) || 0 },
                to_layer: { form: "atom", type: "int", value: Number(row.to_layer) || 0 },
                issue: { form: "atom", type: "string", value: String(row.issue || "") },
              },
            };
          }),
        });
      });
    }
    addPre(
      mount,
      "route " +
        traces.length +
        " net(s) · DRC " +
        (issues.length ? issues.length + " hit(s)" : "ok") +
        " · gap " +
        clearance +
        " · min_width " +
        minWidth +
        " · deck " +
        str(visual, walk, rec, "deck", "2L-FR4") +
        " · " +
        str(visual, walk, rec, "net", "n1")
    );
  }

  function chip(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const solvers = root.ZintriqSolvers;
    const die = str(visual, walk, rec, "die", "core");
    const bus = str(visual, walk, rec, "bus", "axi");
    const pins = Math.max(4, Math.min(32, parseInt(walkValue(visual, walk, rec.id, "pins"), 10) || 8));
    const mhz = num(visual, walk, rec, "mhz", 100);
    const traces = [];
    for (let i = 0; i < Math.min(pins, 8); i += 1) {
      const y = 48 + (i * 84) / Math.max(1, Math.min(pins, 8) - 1);
      traces.push(solvers ? solvers.manhattanRoute(64, y, 256, y + (i % 2) * 8) : [[64, y], [256, y]]);
    }
    const issues = solvers ? solvers.routeDrc(traces, 3) : [];
    const g = addCanvas(mount, 320, 180);
    g.fillStyle = "#1c1c1c";
    g.fillRect(0, 0, 320, 180);
    g.fillStyle = "#2f2f32";
    g.fillRect(70, 40, 180, 100);
    g.strokeStyle = "#6af";
    traces.forEach(function (path) {
      g.beginPath();
      path.forEach(function (pt, pi) {
        if (pi === 0) g.moveTo(pt[0], pt[1]);
        else g.lineTo(pt[0], pt[1]);
      });
      g.stroke();
    });
    g.fillStyle = "#666";
    for (let i = 0; i < pins; i += 1) {
      const y = 44 + (i * 92) / pins;
      g.fillRect(60, y, 10, 4);
      g.fillRect(250, y, 10, 4);
    }
    g.fillStyle = "#9cf";
    g.fillRect(100, 70, 50, 40);
    g.fillStyle = "#fc6";
    g.fillRect(168, 70, 50, 40);
    g.fillStyle = "#eee";
    g.font = "11px ui-monospace, monospace";
    g.fillText(die, 108, 94);
    addPre(
      mount,
      bus +
        " · " +
        pins +
        " pins · " +
        mhz +
        " MHz · route DRC " +
        (issues.length ? issues.length + " hit(s)" : "ok") +
        " · " +
        str(visual, walk, rec, "process", "28nm")
    );
  }

  function logic(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const state = str(visual, walk, rec, "state", "idle");
    const initial = str(visual, walk, rec, "initial", "idle");
    const count = arrayLength(visual, walk, rec.id, "transitions");
    const g = addCanvas(mount, 320, 120);
    g.fillStyle = "#111";
    g.fillRect(0, 0, 320, 120);
    const labels = [initial, state, "end"];
    labels.forEach(function (label, i) {
      const x = 40 + i * 90;
      g.strokeStyle = label === state ? "#6af" : "#555";
      g.strokeRect(x, 36, 70, 40);
      g.fillStyle = label === state ? "#6af" : "#aaa";
      g.font = "11px ui-monospace, monospace";
      g.fillText(label.slice(0, 8), x + 8, 60);
      if (i < 2) {
        g.beginPath();
        g.moveTo(x + 70, 56);
        g.lineTo(x + 90, 56);
        g.stroke();
      }
    });
    addPre(mount, "state " + state + " · " + count + " transitions");
  }

  function video(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const clip = str(visual, walk, rec, "clip", "intro.mp4");
    let frame = parseInt(walkValue(visual, walk, rec.id, "frame"), 10) || 0;
    const fps = num(visual, walk, rec, "fps", 24);
    const g = addCanvas(mount, 320, 180);
    function tick() {
      if (playing(mount)) frame += 1;
      g.fillStyle = "#000";
      g.fillRect(0, 0, 320, 180);
      g.fillStyle = "hsl(" + ((frame * 3) % 360) + ",40%,20%)";
      g.fillRect(0, 0, 320, 150);
      const bar = (frame % (fps * 4)) / (fps * 4);
      g.fillStyle = "#444";
      g.fillRect(0, 160, 320, 20);
      g.fillStyle = "#6af";
      g.fillRect(0, 160, 320 * bar, 20);
      g.fillStyle = "#fff";
      g.font = "12px ui-monospace, monospace";
      g.fillText(clip.slice(0, 28), 12, 24);
      g.fillText("f" + frame + " @ " + fps + "fps", 12, 44);
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
  }

  function font(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const typeface = str(visual, walk, rec, "typeface", "Inter");
    const glyph = str(visual, walk, rec, "glyph", "A");
    const size = num(visual, walk, rec, "size", 64);
    const tracking = num(visual, walk, rec, "tracking", 0);
    const g = addCanvas(mount, 320, 140);
    g.fillStyle = "#fafafa";
    g.fillRect(0, 0, 320, 140);
    g.fillStyle = str(visual, walk, rec, "color", "#111111");
    g.font = size + "px " + typeface + ", system-ui, sans-serif";
    g.textBaseline = "middle";
    const sample = glyph + " agH";
    let x = 24;
    for (let i = 0; i < sample.length; i += 1) {
      g.fillText(sample[i], x, 70);
      x += size * 0.6 + tracking;
    }
    addPre(mount, typeface + " " + size + "px · tracking " + tracking);
  }

  function documentView(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const heading = str(visual, walk, rec, "heading", "Title");
    const paragraph = str(visual, walk, rec, "paragraph", "");
    const cols = num(visual, walk, rec, "columns", 1);
    addPre(mount, "# " + heading + "\n\n" + paragraph + "\n\n[" + cols + " col]");
  }

  function cad(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const w = num(visual, walk, rec, "width", 2);
    const h = num(visual, walk, rec, "height", 2);
    const d = num(visual, walk, rec, "depth", 2);
    const mesh = str(visual, walk, rec, "mesh", "box");
    const g = addCanvas(mount, 320, 220);
    drawGrid(g, 320, 220, gridOn(mount));
    const p = project(0, 0, 0, { x: 0, y: 0, z: 8, fov: 50 });
    drawMesh(g, mesh === "box" ? "cube" : mesh, p, 10 * Math.max(w, h, d));
    if (gizmoOn(mount)) drawGizmo(g, p.x, p.y);
    addPre(mount, mesh + " " + w + "×" + h + "×" + d + " · " + str(visual, walk, rec, "boolean", "union"));
  }

  function physics(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const g = addCanvas(mount, 320, 200);
    let x = num(visual, walk, rec, "x", 0);
    let y = num(visual, walk, rec, "y", 10);
    let vx = num(visual, walk, rec, "vx", 0);
    let vy = num(visual, walk, rec, "vy", 0);
    const gravity = num(visual, walk, rec, "gravity", -9.8);
    const drag = num(visual, walk, rec, "drag", 0.01);
    const bounce = num(visual, walk, rec, "restitution", 0.3);
    const mass = num(visual, walk, rec, "mass", 1);
    const r = 6 + Math.min(14, mass * 2);
    function tick() {
      if (playing(mount)) {
        vy += gravity * 0.016;
        vx *= 1 - drag;
        vy *= 1 - drag;
        x += vx * 0.016;
        y += vy * 0.016;
        if (y < r / 8) {
          y = r / 8;
          vy = -vy * bounce;
        }
      }
      g.fillStyle = "#111";
      g.fillRect(0, 0, 320, 200);
      g.strokeStyle = "#555";
      g.beginPath();
      g.moveTo(0, 180);
      g.lineTo(320, 180);
      g.stroke();
      const px = 160 + x * 10;
      const py = 180 - y * 10;
      g.fillStyle = "#e85";
      g.beginPath();
      g.arc(px, py, r, 0, Math.PI * 2);
      g.fill();
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
  }

  function vector(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const path = str(visual, walk, rec, "path", "M0 0 L10 10");
    const stroke = str(visual, walk, rec, "stroke", "#111");
    const fill = str(visual, walk, rec, "fill", "none");
    const scale = num(visual, walk, rec, "scale", 1);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "me-runtime-svg");
    svg.setAttribute("viewBox", "0 0 120 120");
    svg.setAttribute("width", "240");
    svg.setAttribute("height", "240");
    const pathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pathEl.setAttribute("d", path);
    pathEl.setAttribute("fill", fill === "none" ? "none" : fill);
    pathEl.setAttribute("stroke", stroke);
    pathEl.setAttribute("stroke-width", String(2 / Math.max(0.2, scale)));
    pathEl.setAttribute("transform", "scale(" + scale + ")");
    svg.appendChild(pathEl);
    mount.appendChild(svg);
  }

  function text(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const bodyNode = walk(visual, rec.id, "body");
    if (bodyNode && bodyNode.kind === "literal") {
      addPre(mount, String(walkValue(visual, walk, rec.id, "body") || ""));
      return;
    }
    const len = arrayLength(visual, walk, rec.id, "body");
    const g = addCanvas(mount, 280, 16 + Math.max(1, len) * 16);
    g.fillStyle = "#111";
    g.fillRect(0, 0, 280, 16 + Math.max(1, len) * 16);
    g.fillStyle = "#ddd";
    g.font = "11px ui-monospace, monospace";
    for (let i = 0; i < Math.max(1, len); i += 1) {
      g.fillText(String(i + 1), 8, 16 + i * 16);
    }
    addPre(mount, (len ? len + " line(s)" : "Empty") + " · " + str(visual, walk, rec, "locale", "en"));
  }

  function ai(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const model = str(visual, walk, rec, "model", "local.json");
    const prompt = str(visual, walk, rec, "prompt", "");
    const maxTok = num(visual, walk, rec, "max_tokens", 256);
    const status = document.createElement("pre");
    status.className = "me-runtime-log";
    status.textContent =
      "local session · hosted: false\nmodel: " +
      model +
      "\ntokens: 0 / " +
      maxTok +
      "\n---\n" +
      prompt;
    mount.appendChild(status);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Complete";
    function paint(data) {
      const body = data && data.body ? data.body : data || {};
      status.textContent =
        "local session · hosted: " +
        String(body.hosted === true) +
        " · openai: false\nmodel: " +
        String(body.model || model) +
        "\ntokens: " +
        String(body.tokens || (body.vector && body.vector.length) || 0) +
        " / " +
        maxTok +
        "\n---\n" +
        String(body.output || body.error || JSON.stringify(body.vector || body.pack || body.code || "") || "");
    }
    function call(path, payload) {
      const http = root.zintriq && root.zintriq.http;
      if (!http || !http.post) {
        status.textContent = "local session · hosted: false\nmodel: " + model + "\nno desktop http";
        return;
      }
      http
        .post(path, payload)
        .then(function (res) {
          return res && res.json ? res.json() : res;
        })
        .then(paint)
        .catch(function (err) {
          status.textContent = "local session · hosted: false\nmodel: " + model + "\n" + String(err && err.message ? err.message : err);
        });
    }
    btn.addEventListener("click", function () {
      call("/api/builder-core/meta/ai/chat", {
        model: model,
        prompt: prompt,
        messages: [{ role: "user", content: prompt }],
        max_tokens: maxTok,
        stream: false,
      });
    });
    const embedBtn = document.createElement("button");
    embedBtn.type = "button";
    embedBtn.textContent = "Embed";
    embedBtn.addEventListener("click", function () {
      call("/api/builder-core/meta/ai/embed", { model: model, text: prompt });
    });
    const toolBtn = document.createElement("button");
    toolBtn.type = "button";
    toolBtn.textContent = "Tools";
    toolBtn.addEventListener("click", function () {
      call("/api/builder-core/meta/ai/tools", { tool: "explain", args: { prompt: prompt }, model: model });
    });
    mount.appendChild(btn);
    mount.appendChild(embedBtn);
    mount.appendChild(toolBtn);
  }

  function film(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const solvers = root.ZintriqSolvers;
    const title = str(visual, walk, rec, "title", "Cut");
    const fps = num(visual, walk, rec, "fps", 24);
    const duration = Math.max(0.1, num(visual, walk, rec, "duration", 3));
    const rows = childRecords(visual, walk, rec.id, "shots").map(function (row) {
      return {
        clip: walkValue(visual, walk, row.id, "clip") || "shot",
        duration: Number(walkValue(visual, walk, row.id, "duration")) || 1,
        in: Number(walkValue(visual, walk, row.id, "in")) || 0,
        out: Number(walkValue(visual, walk, row.id, "out")) || 0,
        track: Number(walkValue(visual, walk, row.id, "track")) || 1,
        edl: walkValue(visual, walk, row.id, "edl") || "",
        cut: childRecords(visual, walk, row.id, "cut").map(function (child) {
          return {
            clip: walkValue(visual, walk, child.id, "clip") || "shot",
            duration: Number(walkValue(visual, walk, child.id, "duration")) || 1,
            in: Number(walkValue(visual, walk, child.id, "in")) || 0,
            out: Number(walkValue(visual, walk, child.id, "out")) || 0,
            track: Number(walkValue(visual, walk, child.id, "track")) || 1,
            edl: walkValue(visual, walk, child.id, "edl") || walkValue(visual, walk, row.id, "edl") || "",
          };
        }),
      };
    });
    const engineState = root.ZintriqEngine && root.ZintriqEngine.store ? root.ZintriqEngine.store.get() : {};
    const currentSlug = String((engineState && engineState.slug) || (document.getElementById("me-slug") || {}).value || "");
    const nestedCache = mount._nestedCuts || {};
    rows.forEach(function (row) {
      const slug = String(row.edl || "").trim();
      if (!slug || slug === currentSlug) return;
      if (row.cut && row.cut.length) return;
      if (nestedCache[slug] && nestedCache[slug].length) {
        row.cut = nestedCache[slug].map(function (shot) {
          return {
            track: shot.track,
            in: shot.in,
            out: shot.out,
          };
        });
      }
    });
    const missing = [];
    rows.forEach(function (row) {
      const slug = String(row.edl || "").trim();
      if (!slug || slug === currentSlug) return;
      if (row.cut && row.cut.length) return;
      if (missing.indexOf(slug) < 0) missing.push(slug);
    });
    const http = root.zintriq && root.zintriq.http;
    if (missing.length && !mount._nestedLoading && http && http.get) {
      mount._nestedLoading = true;
      Promise.all(
        missing.map(function (slug) {
          return http
            .get("/api/builder-core/meta/drafts/" + encodeURIComponent(slug) + "/cut")
            .then(function (res) {
              return res.json();
            })
            .then(function (data) {
              nestedCache[slug] = ((data && data.shots) || []).map(function (shot) {
                if (!shot || typeof shot !== "object") return shot;
                return {
                  track: shot.track,
                  in: shot.in,
                  out: shot.out,
                };
              });
            })
            .catch(function () {
              nestedCache[slug] = [];
            });
        })
      ).then(function () {
        mount._nestedCuts = nestedCache;
        mount._nestedLoading = false;
        film(mount, visual, spec, ctx, walk, domainRoot);
      });
    }
    const cut = solvers
      ? solvers.assembleCut(rows, 0)
      : { duration: duration, shots: rows, active: "" };
    const tracks = Math.max(1, ...cut.shots.map(function (s) { return s.track; }).concat([1]));
    const razorAt = duration / 2;
    const razored = solvers ? solvers.razorShot(cut.shots, razorAt) : cut.shots;
    const audioRows = childRecords(visual, walk, rec.id, "audio").map(function (row) {
      return {
        bus: walkValue(visual, walk, row.id, "bus") || "master",
        clip: walkValue(visual, walk, row.id, "clip") || "a",
        track: Number(walkValue(visual, walk, row.id, "track")) || 1,
        duration: Number(walkValue(visual, walk, row.id, "duration")) || 2,
        gain: Number(walkValue(visual, walk, row.id, "gain")) || 1,
        in: Number(walkValue(visual, walk, row.id, "in")) || 0,
        pan: Number(walkValue(visual, walk, row.id, "pan")) || 0,
      };
    });
    const thisDescAudio = audioRows;
    const mix = solvers && solvers.mixAudio ? solvers.mixAudio(thisDescAudio, 0.5) : { level: 0 };
    const wave = (mix && mix.wave) || audioRows.map(function (row) {
      return { y: Math.min(1, Number(row.gain) || 0.4) };
    });
    const grade = solvers && solvers.gradeFrame
      ? solvers.gradeFrame([0.5, 0.45, 0.4], num(visual, walk, rec, "lift", 0), num(visual, walk, rec, "gamma", 1), num(visual, walk, rec, "gain", 1), num(visual, walk, rec, "sat", 1))
      : [0.5, 0.45, 0.4];
    const graded = solvers && solvers.gradeGraph
      ? solvers.gradeGraph(grade, [{ op: "gain", value: num(visual, walk, rec, "gain", 1) }, { op: "sat", value: num(visual, walk, rec, "sat", 1) }])
      : grade;
    const parade = solvers && solvers.rgbParade ? solvers.rgbParade([graded, [0.2, 0.25, 0.3], [0.7, 0.6, 0.5]]) : { r: [], g: [], b: [] };
    const hist = solvers && solvers.histogram ? solvers.histogram([graded, [0.2, 0.3, 0.4], [0.8, 0.5, 0.2]], 12) : [];
    const scope = solvers && solvers.vectorscope ? solvers.vectorscope(graded) : { u: 0, v: 0 };
    const g = addCanvas(mount, 360, 36 + tracks * 28);
    let t = 0;
    function tick() {
      if (playing(mount)) t += 1 / fps;
      if (t > cut.duration) t = 0;
      const now = solvers ? solvers.assembleCut(cut.shots, t) : cut;
      g.fillStyle = "#181818";
      g.fillRect(0, 0, 360, 36 + tracks * 28);
      cut.shots.forEach(function (shot) {
        const x = 8 + (shot.in / Math.max(0.01, cut.duration)) * 344;
        const w = Math.max(6, (shot.duration / Math.max(0.01, cut.duration)) * 344);
        const y = 8 + (shot.track - 1) * 28;
        g.fillStyle = shot.clip === now.active ? "#6af" : "#445";
        g.fillRect(x, y, w, 22);
        g.fillStyle = "#111";
        g.font = "10px ui-monospace, monospace";
        g.fillText(String(shot.clip).slice(0, 8), x + 4, y + 15);
      });
      const px = 8 + (t / Math.max(0.01, cut.duration)) * 344;
      g.strokeStyle = "#fc6";
      g.beginPath();
      g.moveTo(px, 4);
      g.lineTo(px, 32 + tracks * 28);
      g.stroke();
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    const canvas = mount.querySelector("canvas");
    function shotDesc(list) {
      return {
        form: "sequence",
        items: list.map(function (shot) {
          return {
            form: "struct",
            fields: {
              clip: { form: "atom", type: "string", value: String(shot.clip || "shot") },
              duration: { form: "atom", type: "float", value: Number(shot.duration) || 1 },
              in: { form: "atom", type: "float", value: Number(shot.in) || 0 },
              out: { form: "atom", type: "float", value: Number(shot.out) || 0 },
              track: { form: "atom", type: "int", value: Number(shot.track) || 1 },
              edl: { form: "atom", type: "string", value: String(shot.edl || "") },
            },
          };
        }),
      };
    }
    function edlText(list, audioList) {
      const video = (list || []).map(function (shot, i) {
        const n = String(i + 1).padStart(3, "0");
        return n + "  " + String(shot.clip || "AX") + "  V     C        " + Number(shot.in).toFixed(2) + " " + Number(shot.out).toFixed(2) + "  T" + (Number(shot.track) || 1) + (shot.edl ? "  " + String(shot.edl) : "");
      });
      const audioLines = (audioList || audioRows).map(function (clip, i) {
        const n = String(video.length + i + 1).padStart(3, "0");
        const inn = Number(clip.in) || 0;
        const out = Number(clip.out) || inn + (Number(clip.duration) || 0);
        return n + "  " + String(clip.clip || "AX") + "  A     C        " + inn.toFixed(2) + " " + Number(out).toFixed(2) + "  A" + (Number(clip.track) || 1);
      });
      return video.concat(audioLines).join("\n");
    }
    if (canvas) {
      canvas.addEventListener("pointerdown", function (ev) {
        const at = (ev.offsetX / 360) * Math.max(0.01, cut.duration);
        const tool = hostTool(mount);
        if (tool === "razor") {
          const pieces = solvers ? solvers.razorShot(cut.shots, at) : cut.shots;
          writeMerge(ctx, "shots", shotDesc(pieces));
          writeMerge(ctx, "edl", { form: "atom", type: "string", value: edlText(pieces, audioRows) });
        } else if (tool === "edl") {
          const text = str(visual, walk, rec, "edl", "");
          const parsed = solvers && solvers.parseEdl ? solvers.parseEdl(text) : [];
          if (parsed.length) writeMerge(ctx, "shots", shotDesc(parsed));
          const audioParsed = parsed.audio || [];
          if (audioParsed.length) {
            writeMerge(ctx, "audio", {
              form: "sequence",
              items: audioParsed.map(function (clip) {
                return {
                  form: "struct",
                  fields: {
                    clip: { form: "atom", type: "string", value: String(clip.clip || "a") },
                    track: { form: "atom", type: "int", value: Number(clip.track) || 1 },
                    in: { form: "atom", type: "float", value: Number(clip.in) || 0 },
                    out: { form: "atom", type: "float", value: Number(clip.out) || 0 },
                    duration: { form: "atom", type: "float", value: Number(clip.duration) || 1 },
                    gain: { form: "atom", type: "float", value: 1 },
                    pan: { form: "atom", type: "float", value: 0 },
                    mute: { form: "atom", type: "bool", value: false },
                  },
                };
              }),
            });
          }
        } else {
          writeMerge(ctx, "playhead", { form: "atom", type: "float", value: at });
        }
      });
    }
    addPre(
      mount,
      title +
        " · " +
        cut.shots.length +
        " clip(s) / " +
        tracks +
        " track(s) @ " +
        fps +
        "fps · razor @" +
        razorAt.toFixed(2) +
        "s → " +
        razored.length +
        " pieces · EDL · mix " +
        (mix.level || 0).toFixed(2) +
        " · grade " +
        graded.map(function (c) { return Number(c).toFixed(2); }).join(",") +
        " · waveform " +
        wave.length +
        " · vectorscope " +
        Number(scope.u || 0).toFixed(2) +
        " · parade " +
        (parade.r || []).length +
        " · hist " +
        hist.length
    );
    const scopes = addCanvas(mount, 180, 48);
    scopes.fillStyle = "#111";
    scopes.fillRect(0, 0, 180, 48);
    wave.forEach(function (row, i) {
      const x = 8 + i * 16;
      scopes.fillStyle = "#6af";
      scopes.fillRect(x, 44 - (row.y || 0) * 40, 10, (row.y || 0) * 40);
    });
    scopes.fillStyle = "#fc6";
    scopes.beginPath();
    scopes.arc(150 + (scope.u || 0) * 20, 24 + (scope.v || 0) * 20, 3, 0, Math.PI * 2);
    scopes.fill();
  }

  function animation(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const duration = Math.max(0.1, num(visual, walk, rec, "duration", 1));
    const fps = num(visual, walk, rec, "fps", 24);
    const keys = arrayLength(visual, walk, rec.id, "keyframes");
    const g = addCanvas(mount, 320, 80);
    let t = 0;
    function tick() {
      if (playing(mount)) t = (t + 1 / fps) % duration;
      g.fillStyle = "#111";
      g.fillRect(0, 0, 320, 80);
      g.fillStyle = "#333";
      g.fillRect(16, 36, 288, 8);
      g.fillStyle = "#6af";
      g.fillRect(16, 36, 288 * (t / duration), 8);
      g.fillStyle = "#fc6";
      for (let i = 0; i < keys; i += 1) {
        g.fillRect(16 + (i / Math.max(1, keys - 1)) * 288, 32, 3, 16);
      }
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    addPre(mount, duration.toFixed(2) + "s · " + keys + " keys · " + str(visual, walk, rec, "easing", "linear"));
  }

  function skeleton(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const solvers = root.ZintriqSolvers;
    const boneRows = childRecords(visual, walk, rec.id, "bones");
    const n = Math.max(1, boneRows.length || arrayLength(visual, walk, rec.id, "bones"));
    const reach = num(visual, walk, rec, "reach", 1.5);
    const g = addCanvas(mount, 280, 200);
    const rest = [[140, 180]];
    let hx = 140;
    let hy = 180;
    let heading = -Math.PI / 2;
    for (let i = 0; i < n; i += 1) {
      const len = 28 * reach * (boneRows[i] ? Math.max(0.2, Number(walkValue(visual, walk, boneRows[i].id, "length")) || 1) : 1);
      heading += ((boneRows[i] ? Number(walkValue(visual, walk, boneRows[i].id, "angle")) : 0) || 0) * Math.PI / 180;
      hx += Math.cos(heading) * len;
      hy += Math.sin(heading) * len;
      rest.push([hx, hy]);
    }
    const mesh = solvers && solvers.skinMesh3d
      ? solvers.skinMesh3d(rest.map(function (p) { return [p[0], p[1], 0]; }), 8, 6)
      : (solvers && solvers.skinMesh ? solvers.skinMesh(rest, 14) : { faces: [], vertices: rest, weights: [] });
    let weights = mesh.weights && mesh.weights.length ? mesh.weights : rest.map(function (_v, i) {
      return [[Math.max(0, i - 1), 0.35], [Math.min(i, rest.length - 1), 0.65]];
    });
    const brush = num(visual, walk, rec, "brush", 24);
    const strength = num(visual, walk, rec, "paint", 0.35);
    const view = g.canvas;
    let yaw = 0.35;
    let pitch = 0.25;
    if (view && !view.getAttribute("data-paint-bound")) {
      view.setAttribute("data-paint-bound", "1");
      view.addEventListener("pointerdown", function (ev) {
        const host = mount.closest("[data-tool]") || mount;
        const tool = host.getAttribute("data-tool") || "paint";
        const box = view.getBoundingClientRect();
        const x = ((ev.clientX - box.left) / box.width) * view.width;
        const y = ((ev.clientY - box.top) / box.height) * view.height;
        if (tool === "orbit") {
          yaw += (x - 140) * 0.004;
          pitch += (y - 100) * 0.004;
          view.setAttribute("data-yaw", String(yaw));
          view.setAttribute("data-pitch", String(pitch));
          return;
        }
        if (tool === "flood" && solvers && solvers.floodWeights) {
          weights = solvers.floodWeights(weights, 0);
          return;
        }
        if (tool === "smooth" && solvers && solvers.heatBind) {
          weights = solvers.heatBind(mesh.vertices || rest, rest, brush);
          if (solvers.pruneInfluences) weights = solvers.pruneInfluences(weights, 4);
          return;
        }
        if (solvers && solvers.paintWeights) {
          const projected = solvers.projectOrbit ? solvers.projectOrbit(mesh.vertices || rest, yaw, pitch, 1, 140, 100) : (mesh.vertices || rest);
          weights = solvers.paintWeights(weights, projected, [x, y], 0, brush, strength);
        }
        view.setAttribute("data-brush-x", String(x));
        view.setAttribute("data-brush-y", String(y));
      });
    }
    let t = 0;
    function tick() {
      t += playing(mount) ? 0.03 : 0;
      const target = [140 + Math.cos(t) * 70 * reach, 40 + Math.sin(t) * 18];
      const yawNow = Number(view.getAttribute("data-yaw")) || yaw;
      const pitchNow = Number(view.getAttribute("data-pitch")) || pitch;
      const posed = solvers ? solvers.ccdIk(rest, target, 10) : rest;
      const skin3 = solvers && solvers.skinDeformDq
        ? solvers.skinDeformDq(mesh.vertices || rest, rest, posed, weights, 0.4)
        : (solvers && solvers.skinDeform ? solvers.skinDeform(mesh.vertices || rest, rest, posed, weights) : (mesh.vertices || rest));
      const skin = solvers && solvers.projectOrbit
        ? solvers.projectOrbit(skin3, yawNow, pitchNow, 1, 140, 100)
        : skin3;
      const posedDraw = solvers && solvers.projectOrbit
        ? solvers.projectOrbit(posed.map(function (p) { return [p[0], p[1], 0]; }), yawNow, pitchNow, 1, 140, 100)
        : posed;
      const targetDraw = solvers && solvers.projectOrbit
        ? solvers.projectOrbit([[target[0], target[1], 0]], yawNow, pitchNow, 1, 140, 100)[0]
        : target;
      g.fillStyle = "#111";
      g.fillRect(0, 0, 280, 200);
      (mesh.faces || []).forEach(function (face) {
        const a = skin[face[0]];
        const b = skin[face[1]];
        const c = skin[face[2]];
        if (!a || !b || !c) return;
        const w = ((weights[face[0]] || [])[0] || [0, 0])[1];
        g.fillStyle = "rgba(80,140,255," + (0.15 + 0.7 * (w || 0)) + ")";
        g.beginPath();
        g.moveTo(a[0], a[1]);
        g.lineTo(b[0], b[1]);
        g.lineTo(c[0], c[1]);
        g.closePath();
        g.fill();
      });
      g.strokeStyle = "#ddd";
      g.lineWidth = 3;
      g.beginPath();
      posedDraw.forEach(function (p, i) {
        if (i === 0) g.moveTo(p[0], p[1]);
        else g.lineTo(p[0], p[1]);
      });
      g.stroke();
      g.fillStyle = "#6af";
      g.beginPath();
      g.arc(posedDraw[posedDraw.length - 1][0], posedDraw[posedDraw.length - 1][1], 5, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = "#e55";
      g.beginPath();
      g.arc(targetDraw[0], targetDraw[1], 4, 0, Math.PI * 2);
      g.fill();
      if (solvers && solvers.bindPose) {
        g.strokeStyle = "rgba(255,200,80,0.7)";
        solvers.bindPose(posedDraw).forEach(function (bone) {
          const o = bone.origin || [0, 0];
          g.beginPath();
          g.moveTo(o[0], o[1]);
          g.lineTo(o[0] + (bone.dx || 0) * 0.2, o[1] + (bone.dy || 0) * 0.2);
          g.stroke();
        });
      }
      const bx = Number(view && view.getAttribute("data-brush-x"));
      const by = Number(view && view.getAttribute("data-brush-y"));
      if (bx || by) {
        g.strokeStyle = "#fc6";
        g.beginPath();
        g.arc(bx, by, brush, 0, Math.PI * 2);
        g.stroke();
      }
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
    addPre(mount, "mesh brush · 3d weight paint · " + (mesh.faces || []).length + " faces");
  }

  function level(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const w = num(visual, walk, rec, "width", 64);
    const h = num(visual, walk, rec, "height", 64);
    const sx = num(visual, walk, rec, "spawn.x", 0);
    const sy = num(visual, walk, rec, "spawn.y", 0);
    const g = addCanvas(mount, 280, 180);
    g.fillStyle = "#1b1e18";
    g.fillRect(0, 0, 280, 180);
    g.strokeStyle = "#4a4";
    g.strokeRect(20, 20, 240, 140);
    const px = 20 + ((sx + w / 2) / w) * 240;
    const py = 160 - ((sy + h / 2) / h) * 140;
    g.fillStyle = "#fc6";
    g.beginPath();
    g.arc(px, py, 5, 0, Math.PI * 2);
    g.fill();
    addPre(mount, str(visual, walk, rec, "room", "start") + " · spawn " + sx + "," + sy);
  }

  function spreadsheet(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const rows = childRecords(visual, walk, rec.id, "rows");
    const cols = Math.max(2, num(visual, walk, rec, "cols", 2));
    const g = addCanvas(mount, 280, 24 + Math.max(1, rows.length) * 22);
    g.fillStyle = "#f7f7f4";
    g.fillRect(0, 0, 280, 24 + Math.max(1, rows.length) * 22);
    g.strokeStyle = "#ccc";
    rows.forEach(function (row, i) {
      const y = 22 + i * 22;
      g.strokeRect(8, y, 264, 22);
      g.fillStyle = "#222";
      g.font = "11px ui-monospace, monospace";
      g.fillText(String(walkValue(visual, walk, row.id, "a") || ""), 14, y + 15);
      g.fillText(String(walkValue(visual, walk, row.id, "b") || ""), 140, y + 15);
    });
    addPre(mount, rows.length + " rows · " + cols + " cols · " + str(visual, walk, rec, "title", "Sheet"));
  }

  function ui(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const w = num(visual, walk, rec, "width", 360);
    const theme = str(visual, walk, rec, "theme", "light");
    const g = addCanvas(mount, 280, 160);
    g.fillStyle = theme === "dark" ? "#1a1a1a" : "#f4f4f4";
    g.fillRect(0, 0, 280, 160);
    g.fillStyle = theme === "dark" ? "#333" : "#fff";
    g.fillRect(20, 16, 240, 28);
    g.fillStyle = theme === "dark" ? "#eee" : "#111";
    g.font = "12px system-ui, sans-serif";
    g.fillText(str(visual, walk, rec, "title", "Screen"), 32, 36);
    g.fillStyle = theme === "dark" ? "#2a2a2a" : "#e8e8e8";
    g.fillRect(20, 56, 240, 80);
    addPre(mount, w + "px · " + theme);
  }

  function nodeGraph(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const g = addCanvas(mount, 280, 120);
    g.fillStyle = "#111";
    g.fillRect(0, 0, 280, 120);
    g.strokeStyle = "#6af";
    g.strokeRect(24, 40, 80, 40);
    g.strokeRect(176, 40, 80, 40);
    g.beginPath();
    g.moveTo(104, 60);
    g.lineTo(176, 60);
    g.stroke();
    g.fillStyle = "#ddd";
    g.font = "11px ui-monospace, monospace";
    g.fillText(str(visual, walk, rec, "a.label", "A"), 40, 64);
    g.fillText(str(visual, walk, rec, "b.label", "B"), 196, 64);
    g.fillText(str(visual, walk, rec, "edge", "→"), 128, 36);
  }

  function vr(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const g = addCanvas(mount, 320, 160);
    drawGrid(g, 320, 160, true);
    g.strokeStyle = "#8af";
    g.strokeRect(40, 30, 100, 100);
    g.strokeRect(180, 30, 100, 100);
    addPre(mount, "IPD " + num(visual, walk, rec, "ipd", 63) + "mm · fov " + num(visual, walk, rec, "fov", 90) + " · " + str(visual, walk, rec, "rig", "room"));
  }

  function robotics(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const joints = Math.max(2, parseInt(walkValue(visual, walk, rec.id, "joints"), 10) || 4);
    const g = addCanvas(mount, 280, 180);
    let t = 0;
    function tick() {
      t += playing(mount) ? 0.04 : 0;
      g.fillStyle = "#111";
      g.fillRect(0, 0, 280, 180);
      g.strokeStyle = "#fc6";
      g.lineWidth = 4;
      g.beginPath();
      let x = 40;
      let y = 140;
      g.moveTo(x, y);
      for (let i = 0; i < joints; i += 1) {
        x += 36;
        y -= 18 + Math.sin(t + i) * 10;
        g.lineTo(x, y);
      }
      g.stroke();
      mount._raf = root.requestAnimationFrame(tick);
    }
    tick();
  }

  function print3d(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const layer = num(visual, walk, rec, "layer", 0.2);
    const infill = num(visual, walk, rec, "infill", 0.2);
    const g = addCanvas(mount, 240, 160);
    g.fillStyle = "#222";
    g.fillRect(0, 0, 240, 160);
    const n = Math.max(4, Math.min(40, Math.round(20 / layer)));
    g.strokeStyle = "#e85";
    for (let i = 0; i < n; i += 1) g.strokeRect(70, 130 - i * 3, 100, 3);
    g.strokeStyle = "rgba(232,136,80," + infill + ")";
    for (let x = 80; x < 160; x += 6) {
      g.beginPath();
      g.moveTo(x, 20);
      g.lineTo(x, 130);
      g.stroke();
    }
    addPre(mount, str(visual, walk, rec, "material", "PLA") + " · layer " + layer + "mm · infill " + infill);
  }

  function cnc(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const g = addCanvas(mount, 240, 160);
    g.fillStyle = "#1a1a18";
    g.fillRect(0, 0, 240, 160);
    g.strokeStyle = "#8c8";
    g.beginPath();
    g.moveTo(20, 80);
    g.lineTo(80, 40);
    g.lineTo(160, 100);
    g.lineTo(220, 50);
    g.stroke();
    addPre(mount, str(visual, walk, rec, "tool", "endmill") + " · feed " + num(visual, walk, rec, "feed", 200) + " · " + num(visual, walk, rec, "rpm", 8000) + " rpm");
  }

  function chain(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    const blocks = Math.max(1, parseInt(walkValue(visual, walk, rec.id, "blocks"), 10) || 3);
    const g = addCanvas(mount, 320, 80);
    g.fillStyle = "#111";
    g.fillRect(0, 0, 320, 80);
    for (let i = 0; i < blocks; i += 1) {
      g.strokeStyle = "#fc6";
      g.strokeRect(16 + i * 60, 20, 48, 40);
      if (i) {
        g.beginPath();
        g.moveTo(16 + i * 60, 40);
        g.lineTo(16 + i * 60 - 12, 40);
        g.stroke();
      }
      g.fillStyle = "#fc6";
      g.font = "9px ui-monospace, monospace";
      g.fillText("h" + i, 22 + i * 60, 44);
      if (i) g.fillText("p" + (i - 1), 22 + i * 60, 54);
    }
    addPre(mount, str(visual, walk, rec, "title", "Ledger") + " · local only");
  }

  function checkout(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    addPre(
      mount,
      str(visual, walk, rec, "currency", "usd") +
        " · " +
        arrayLength(visual, walk, rec.id, "items") +
        " items · tax " +
        num(visual, walk, rec, "tax", 0) +
        " · local ledger"
    );
  }

  function channel(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    addPre(mount, "#" + str(visual, walk, rec, "name", "general") + " · " + arrayLength(visual, walk, rec.id, "messages") + " messages · " + str(visual, walk, rec, "visibility", "public"));
  }

  function metaView(mount, visual, spec, ctx, walk, domainRoot) {
    clearMount(mount);
    const rec = domainRoot(visual, spec);
    if (!rec) return;
    addPre(mount, str(visual, walk, rec, "id", "") + " → " + str(visual, walk, rec, "target", "web_build") + " · v" + str(visual, walk, rec, "version", "1"));
  }

  root.ZintriqEditorRuntimes = {
    shader: shader,
    quantum: quantum,
    map: map,
    bitmap: bitmap,
    audio: audio,
    particle: particle,
    terrain: terrain,
    scene: scene,
    model3d: model3d,
    material: material,
    circuit: circuit,
    chip: chip,
    logic: logic,
    video: video,
    font: font,
    document: documentView,
    cad: cad,
    physics: physics,
    vector: vector,
    text: text,
    ai: ai,
    film: film,
    animation: animation,
    skeleton: skeleton,
    level: level,
    spreadsheet: spreadsheet,
    ui: ui,
    node: nodeGraph,
    vr: vr,
    robotics: robotics,
    print3d: print3d,
    cnc: cnc,
    chain: chain,
    checkout: checkout,
    channel: channel,
    broadcast: channel,
    settle: checkout,
    federate: channel,
    weights: ai,
    meta: metaView,
  };
})(window);
