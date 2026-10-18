/**
 * Local preview solvers. Same algorithms as meta.runtime.kernels.
 * Not Autodesk Skin, Altium, or Premiere.
 */
(function (root) {
  function ccdIk(joints, target, iterations) {
    const pts = joints.map(function (p) {
      return [p[0], p[1]];
    });
    if (pts.length < 2) return pts;
    const tx = target[0];
    const ty = target[1];
    const n = Math.max(1, iterations || 12);
    for (let it = 0; it < n; it += 1) {
      for (let i = pts.length - 2; i >= 0; i -= 1) {
        const jx = pts[i][0];
        const jy = pts[i][1];
        const ex = pts[pts.length - 1][0];
        const ey = pts[pts.length - 1][1];
        const toEnd = Math.atan2(ey - jy, ex - jx);
        const toTgt = Math.atan2(ty - jy, tx - jx);
        const delta = toTgt - toEnd;
        const cosD = Math.cos(delta);
        const sinD = Math.sin(delta);
        for (let k = i + 1; k < pts.length; k += 1) {
          const dx = pts[k][0] - jx;
          const dy = pts[k][1] - jy;
          pts[k][0] = jx + dx * cosD - dy * sinD;
          pts[k][1] = jy + dx * sinD + dy * cosD;
        }
      }
    }
    return pts;
  }

  function skinDeform(vertices, rest, posed, weights) {
    const bones = Math.max(0, Math.min(rest.length, posed.length) - 1);
    const mats = [];
    for (let i = 0; i < bones; i += 1) {
      const rx = rest[i + 1][0] - rest[i][0];
      const ry = rest[i + 1][1] - rest[i][1];
      const px = posed[i + 1][0] - posed[i][0];
      const py = posed[i + 1][1] - posed[i][1];
      const delta = Math.atan2(py, px) - Math.atan2(ry, rx);
      mats.push([Math.cos(delta), Math.sin(delta), posed[i][0], posed[i][1], rest[i][0], rest[i][1]]);
    }
    if (!mats.length && posed.length) {
      mats.push([1, 0, posed[0][0], posed[0][1], rest[0] ? rest[0][0] : 0, rest[0] ? rest[0][1] : 0]);
    }
    return vertices.map(function (v, i) {
      const binds = weights[i] || [];
      let nx = 0;
      let ny = 0;
      let wsum = 0;
      binds.forEach(function (bind) {
        const index = bind[0];
        const w = bind[1];
        if (w <= 0 || !mats[index]) return;
        const m = mats[index];
        const lx = v[0] - m[4];
        const ly = v[1] - m[5];
        nx += w * (m[2] + lx * m[0] - ly * m[1]);
        ny += w * (m[3] + lx * m[1] + ly * m[0]);
        wsum += w;
      });
      return wsum <= 0 ? [v[0], v[1]] : [nx / wsum, ny / wsum];
    });
  }

  function xyz(point) {
    const p = point || [];
    return [p[0] || 0, p[1] || 0, p[2] || 0];
  }

  function paintWeights(weights, vertices, center, bone, radius, strength) {
    const rad = Math.max(radius || 1, 1e-6);
    const boost = Math.max(0, Math.min(1, strength == null ? 0.25 : strength));
    const c = xyz(center);
    return (weights || []).map(function (binds, i) {
      const v = xyz(vertices[i]);
      const dist = Math.hypot(v[0] - c[0], v[1] - c[1], v[2] - c[2]);
      const falloff = Math.max(0, 1 - dist / rad);
      const rows = {};
      (binds || []).forEach(function (bind) {
        rows[bind[0]] = bind[1];
      });
      if (falloff > 0) rows[bone || 0] = (rows[bone || 0] || 0) + boost * falloff;
      let total = 0;
      Object.keys(rows).forEach(function (k) {
        total += Math.max(0, rows[k]);
      });
      return Object.keys(rows).map(function (k) {
        return [parseInt(k, 10), total > 0 ? rows[k] / total : rows[k]];
      });
    });
  }

  function skinMesh(joints, width) {
    const verts = [];
    const faces = [];
    const weights = [];
    const half = Math.max(width || 12, 1) * 0.5;
    (joints || []).forEach(function (p, i) {
      const nxt = joints[i + 1] || joints[i - 1] || p;
      const dx = nxt[0] - p[0];
      const dy = nxt[1] - p[1];
      const len = Math.hypot(dx, dy) || 1;
      const nx = (-dy / len) * half;
      const ny = (dx / len) * half;
      verts.push([p[0] + nx, p[1] + ny], [p[0] - nx, p[1] - ny]);
      const bone = Math.max(0, Math.min(i, (joints || []).length - 2));
      weights.push([[bone, 1]], [[bone, 1]]);
      if (i > 0) {
        const a = (i - 1) * 2;
        faces.push([a, a + 1, a + 2], [a + 1, a + 3, a + 2]);
      }
    });
    return { faces: faces, vertices: verts, weights: weights };
  }

  function skinMesh3d(joints, radius, rings) {
    const pts = (joints || []).map(xyz);
    const segs = Math.max(3, rings || 6);
    const rad = Math.max(radius || 8, 0.5);
    const verts = [];
    const faces = [];
    const weights = [];
    if (pts.length < 2) {
      return { faces: [], vertices: pts.length ? [pts[0]] : [[0, 0, 0]], weights: [[[0, 1]]] };
    }
    pts.forEach(function (p, i) {
      const nxt = pts[i + 1] || pts[i - 1];
      const dx = nxt[0] - p[0];
      const dy = nxt[1] - p[1];
      const dz = nxt[2] - p[2];
      const len = Math.hypot(dx, dy, dz) || 1;
      const ax = dx / len;
      const ay = dy / len;
      const az = dz / len;
      let bx;
      let by;
      let bz;
      if (Math.abs(az) < 0.9) {
        bx = -ay;
        by = ax;
        bz = 0;
      } else {
        bx = 0;
        by = -az;
        bz = ay;
      }
      const bl = Math.hypot(bx, by, bz) || 1;
      bx = (bx / bl) * rad;
      by = (by / bl) * rad;
      bz = (bz / bl) * rad;
      const cx = ay * bz - az * by;
      const cy = az * bx - ax * bz;
      const cz = ax * by - ay * bx;
      const bone = Math.max(0, Math.min(i, pts.length - 2));
      const base = verts.length;
      for (let k = 0; k < segs; k += 1) {
        const ang = (Math.PI * 2 * k) / segs;
        verts.push([
          p[0] + bx * Math.cos(ang) + cx * Math.sin(ang),
          p[1] + by * Math.cos(ang) + cy * Math.sin(ang),
          p[2] + bz * Math.cos(ang) + cz * Math.sin(ang),
        ]);
        weights.push([[bone, 1]]);
      }
      if (i > 0) {
        const prev = base - segs;
        for (let k = 0; k < segs; k += 1) {
          const a = prev + k;
          const b = prev + ((k + 1) % segs);
          const c = base + k;
          const d = base + ((k + 1) % segs);
          faces.push([a, b, c], [b, d, c]);
        }
      }
    });
    return { faces: faces, vertices: verts, weights: weights };
  }

  function projectOrbit(points, yaw, pitch, scale, cx, cy) {
    const cyaw = Math.cos(yaw || 0.4);
    const syaw = Math.sin(yaw || 0.4);
    const cp = Math.cos(pitch || 0.3);
    const sp = Math.sin(pitch || 0.3);
    const s = scale == null ? 1 : scale;
    return (points || []).map(function (pt) {
      const p = xyz(pt);
      const x1 = p[0] * cyaw - p[2] * syaw;
      const z1 = p[0] * syaw + p[2] * cyaw;
      const y1 = p[1] * cp - z1 * sp;
      return [x1 * s + (cx || 140), y1 * s + (cy || 100)];
    });
  }

  function manhattanRoute(ax, ay, bx, by, jog) {
    const j = jog == null ? 8 : jog;
    if (Math.abs(ax - bx) < 1e-6 || Math.abs(ay - by) < 1e-6) {
      return [
        [ax, ay],
        [bx, by],
      ];
    }
    if (Math.abs(ay - by) > j) {
      const mid = ax + (bx - ax) * 0.5;
      return [
        [ax, ay],
        [mid, ay],
        [mid, by],
        [bx, by],
      ];
    }
    return [
      [ax, ay],
      [ax, by],
      [bx, by],
    ];
  }

  function segGap(a0, a1, b0, b1) {
    const ax0 = a0[0];
    const ay0 = a0[1];
    const ax1 = a1[0];
    const ay1 = a1[1];
    const bx0 = b0[0];
    const by0 = b0[1];
    const bx1 = b1[0];
    const by1 = b1[1];
    if (Math.abs(ay0 - ay1) < 1e-6 && Math.abs(by0 - by1) < 1e-6) {
      if (Math.max(Math.min(ax0, ax1), Math.min(bx0, bx1)) <= Math.min(Math.max(ax0, ax1), Math.max(bx0, bx1))) {
        return Math.abs(ay0 - by0);
      }
      return Math.min(Math.abs(ax0 - bx0), Math.abs(ax0 - bx1), Math.abs(ax1 - bx0), Math.abs(ax1 - bx1));
    }
    if (Math.abs(ax0 - ax1) < 1e-6 && Math.abs(bx0 - bx1) < 1e-6) {
      if (Math.max(Math.min(ay0, ay1), Math.min(by0, by1)) <= Math.min(Math.max(ay0, ay1), Math.max(by0, by1))) {
        return Math.abs(ax0 - bx0);
      }
      return Math.min(Math.abs(ay0 - by0), Math.abs(ay0 - by1), Math.abs(ay1 - by0), Math.abs(ay1 - by1));
    }
    return 99;
  }

  function routeDrc(traces, minGap, minWidth, vias, keepouts) {
    const gap = minGap == null ? 4 : minGap;
    const segs = [];
    const issues = [];
    (traces || []).forEach(function (row, ti) {
      const path = row.path || row;
      const layer = row.layer || 0;
      const net = String(row.net != null ? row.net : ti);
      const width = Number(row.width) || 0;
      if (minWidth && width && width < minWidth) issues.push({ layer: layer, issue: "net " + net + " width" });
      for (let i = 0; i < path.length - 1; i += 1) segs.push([ti, layer, net, path[i], path[i + 1]]);
    });
    segs.forEach(function (a, i) {
      segs.slice(i + 1).forEach(function (b) {
        if (a[0] === b[0] || a[1] !== b[1] || a[2] === b[2]) return;
        if (segGap(a[3], a[4], b[3], b[4]) < gap) {
          issues.push({ layer: a[1], issue: "layer " + a[1] + " nets " + a[2] + "/" + b[2] });
        }
      });
    });
    (vias || []).forEach(function (via, i) {
      const fromLayer = Number(via.from_layer != null ? via.from_layer : via.layer) || 0;
      const toLayer = Number(via.to_layer != null ? via.to_layer : fromLayer) || 0;
      (vias || []).slice(i + 1).forEach(function (other) {
        if (via.net === other.net) return;
        if (Math.abs((via.x || 0) - (other.x || 0)) < gap && Math.abs((via.y || 0) - (other.y || 0)) < gap) {
          issues.push({
            layer: fromLayer,
            from_layer: fromLayer,
            to_layer: toLayer,
            issue: "vias shorted",
          });
        }
      });
      if (fromLayer === toLayer) {
        issues.push({
          layer: fromLayer,
          from_layer: fromLayer,
          to_layer: toLayer,
          issue: "via " + String(via.net || i) + " same layer",
        });
      }
    });
    (keepouts || []).forEach(function (zone) {
      const layer = Number(zone.layer) || 0;
      segs.forEach(function (seg) {
        if (Number(seg[1]) !== layer) return;
        const mid = [(seg[3][0] + seg[4][0]) / 2, (seg[3][1] + seg[4][1]) / 2];
        if (inSolidKeepout(seg[3][0], seg[3][1], zone) || inSolidKeepout(seg[4][0], seg[4][1], zone) || inSolidKeepout(mid[0], mid[1], zone)) {
          issues.push({ layer: layer, issue: "keepout " + seg[2] });
        }
      });
    });
    return issues;
  }

  function keepoutHoles(zone) {
    return ((zone && zone.holes) || [])
      .map(function (hole) {
        return keepoutPoints(hole);
      })
      .filter(function (pts) {
        return pts.length >= 3;
      });
  }

  function inSolidKeepout(x, y, zone) {
    const outer = keepoutPoints(zone);
    if (outer.length < 3 || !pointInPoly(x, y, outer)) return false;
    return !keepoutHoles(zone).some(function (hole) {
      return pointInPoly(x, y, hole);
    });
  }

  function keepoutPoints(zone) {
    if (zone && zone.points && zone.points.length) {
      return zone.points.map(function (pt) {
        return [Number(pt.x != null ? pt.x : pt[0]) || 0, Number(pt.y != null ? pt.y : pt[1]) || 0];
      });
    }
    const keys = ["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"];
    const pts = [];
    for (let i = 0; i < keys.length; i += 2) {
      if (zone && zone[keys[i]] != null) pts.push([Number(zone[keys[i]]) || 0, Number(zone[keys[i + 1]]) || 0]);
    }
    return pts;
  }

  function pointInPoly(x, y, pts) {
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
      const xi = pts[i][0];
      const yi = pts[i][1];
      const xj = pts[j][0];
      const yj = pts[j][1];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-12) + xi) inside = !inside;
    }
    return inside;
  }

  function assembleCut(shots, playhead) {
    let duration = 0;
    let active = "";
    const rows = [];
    (shots || []).forEach(function (shot) {
      const start = Number(shot.in != null ? shot.in : shot.at) || 0;
      let dur = Number(shot.duration) || 0;
      const end = Number(shot.out) || 0;
      if (end > start) dur = end - start;
      dur = Math.max(dur || 1, 0.01);
      const nested = shot.cut || shot.nested;
      if (nested && nested.length) {
        nested.forEach(function (child) {
          const cin = start + (Number(child.in != null ? child.in : child.at) || 0);
          let cdur = Number(child.duration) || 0;
          const cend = Number(child.out) || 0;
          if (cend > (Number(child.in) || 0)) cdur = cend - (Number(child.in) || 0);
          cdur = Math.max(cdur || 1, 0.01);
          duration = Math.max(duration, cin + cdur);
          if (cin <= playhead && playhead < cin + cdur) active = String(child.clip || shot.clip || "");
          rows.push({
            at: cin,
            clip: String(child.clip || shot.clip || "shot"),
            duration: cdur,
            in: cin,
            out: cin + cdur,
            track: Math.max(1, parseInt(child.track || shot.track, 10) || 1),
            edl: String(child.edl || shot.edl || ""),
          });
        });
        return;
      }
      duration = Math.max(duration, start + dur);
      if (start <= playhead && playhead < start + dur) active = String(shot.clip || "");
      rows.push({
        at: start,
        clip: String(shot.clip || "shot"),
        duration: dur,
        in: start,
        out: start + dur,
        track: Math.max(1, parseInt(shot.track, 10) || 1),
        edl: String(shot.edl || ""),
      });
    });
    return { active: active, duration: duration, playhead: playhead, shots: rows };
  }

  function razorShot(shots, at) {
    const out = [];
    (shots || []).forEach(function (shot) {
      const start = Number(shot.in != null ? shot.in : shot.at) || 0;
      const dur = Number(shot.duration) || 1;
      const end = Number(shot.out) || start + dur;
      if (start < at && at < end) {
        out.push(Object.assign({}, shot, { duration: at - start, out: at, track: Number(shot.track) || 1, edl: shot.edl || "" }));
        out.push(
          Object.assign({}, shot, {
            at: at,
            clip: String(shot.clip || "shot") + "-b",
            duration: end - at,
            in: at,
            track: Number(shot.track) || 1,
            edl: shot.edl || "",
          })
        );
      } else {
        out.push(shot);
      }
    });
    return out;
  }

  function parseEdl(text) {
    const shots = [];
    const audio = [];
    String(text || "")
      .split(/\n/)
      .forEach(function (line) {
        const match = String(line || "")
          .trim()
          .match(/^\d+\s+(\S+)\s+(\S+)\s+\S+\s+([\d.]+)\s+([\d.]+)(?:\s+T(\d+))?(?:\s+A(\d+))?/i);
        if (!match) return;
        const inn = Number(match[3]) || 0;
        const out = Number(match[4]) || inn;
        const channel = String(match[2] || "V").toUpperCase();
        const audioTrack = match[6] ? Number(match[6]) : 0;
        if (channel.indexOf("A") === 0 || audioTrack) {
          audio.push({
            clip: match[1],
            bus: "A",
            track: audioTrack || Number(String(channel).replace(/\D/g, "")) || 1,
            duration: Math.max(0.01, out - inn),
            in: inn,
            out: out,
          });
          if (channel.indexOf("A") === 0 && !match[5]) return;
        }
        shots.push({
          clip: match[1],
          bus: "V",
          duration: Math.max(0.01, out - inn),
          in: inn,
          out: out,
          track: Number(match[5]) || 1,
        });
      });
    shots.audio = audio;
    return shots;
  }

  function mixAudio(clips, playhead) {
    let level = 0;
    let pan = 0;
    const active = [];
    (clips || []).forEach(function (clip) {
      if (clip.mute) return;
      const start = Number(clip.in != null ? clip.in : clip.offset) || 0;
      const dur = Number(clip.duration) || 1;
      if (start > playhead || playhead >= start + dur) return;
      const gain = clip.gain == null ? 1 : Number(clip.gain);
      const p = Number(clip.pan) || 0;
      level += gain;
      pan += p * gain;
      active.push({ clip: String(clip.clip || "a"), gain: gain, pan: p });
    });
    if (level) pan /= level;
    return { active: active, level: level, pan: pan };
  }

  function pruneInfluences(weights, maxInf) {
    const cap = Math.max(1, maxInf || 4);
    return (weights || []).map(function (binds) {
      return (binds || []).slice().sort(function (a, b) { return (b[1] || 0) - (a[1] || 0); }).slice(0, cap);
    });
  }

  function floodWeights(weights, bone) {
    return (weights || []).map(function () { return [[bone || 0, 1]]; });
  }

  function heatBind(vertices, joints, falloff) {
    const rad = Math.max(falloff || 8, 1e-3);
    const bones = Math.max(1, (joints || []).length - 1);
    return (vertices || []).map(function (v) {
      const p = xyz(v);
      const binds = [];
      for (let i = 0; i < bones; i += 1) {
        const a = xyz(joints[i]);
        const b = xyz(joints[i + 1]);
        const dx = b[0] - a[0];
        const dy = b[1] - a[1];
        const len = Math.hypot(dx, dy) || 1;
        const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (len * len)));
        const qx = a[0] + t * dx;
        const qy = a[1] + t * dy;
        const w = Math.max(0, 1 - Math.hypot(p[0] - qx, p[1] - qy) / rad);
        if (w > 0) binds.push([i, w]);
      }
      return binds.length ? binds : [[0, 1]];
    });
  }

  function trsMatrix(px, py, pz, rx, ry, rz, sx, sy, sz) {
    const ax = ((rx || 0) * Math.PI) / 180;
    const ay = ((ry || 0) * Math.PI) / 180;
    const az = ((rz || 0) * Math.PI) / 180;
    const cx = Math.cos(ax);
    const sxr = Math.sin(ax);
    const cy = Math.cos(ay);
    const syr = Math.sin(ay);
    const cz = Math.cos(az);
    const szr = Math.sin(az);
    return [
      [cy * cz * (sx || 1), (cz * sxr * syr - cx * szr) * (sy || 1), (cx * cz * syr + sxr * szr) * (sz || 1), px || 0],
      [cy * szr * (sx || 1), (cx * cz + sxr * syr * szr) * (sy || 1), (cx * syr * szr - cz * sxr) * (sz || 1), py || 0],
      [-syr * (sx || 1), cy * sxr * (sy || 1), cx * cy * (sz || 1), pz || 0],
      [0, 0, 0, 1],
    ];
  }

  function tokenizeLocal(text, limit) {
    const parts = String(text || "").match(/[A-Za-z0-9_]+|[\u4e00-\u9fff]/g) || [];
    return parts.slice(0, Math.max(1, limit || 2048));
  }

  function rec709Encode(rgb) {
    return (rgb || [0, 0, 0]).map(function (ch) {
      const val = Math.max(0, Math.min(1, ch || 0));
      return val < 0.018 ? 12.92 * val : 1.099 * Math.pow(val, 0.45) - 0.099;
    });
  }

  function highlightRoll(rgb, knee, amount) {
    const k = Math.max(0, Math.min(1, knee || 0.8));
    const t = Math.max(0, Math.min(1, amount == null ? 0.4 : amount));
    return (rgb || [0, 0, 0]).map(function (ch) {
      let val = Math.max(0, ch || 0);
      if (val > k) val = k + (val - k) * (1 - t);
      return Math.max(0, Math.min(1, val));
    });
  }

  function skinCluster(weights) {
    return (weights || []).map(function (binds) {
      if (!binds || !binds.length) return 0;
      return binds.reduce(function (best, row) {
        return row[1] > best[1] ? row : best;
      }, binds[0])[0];
    });
  }

  function dcodeTable(traces) {
    const widths = {};
    (traces || []).forEach(function (row) {
      widths[String(row.width || 0.2)] = true;
    });
    return Object.keys(widths).map(function (w, i) {
      return { d: 10 + i, w: Number(w) };
    });
  }

  function applyCdl(rgb, slope, offset, power) {
    const pwr = Math.max(power == null ? 1 : power, 1e-6);
    const sl = slope == null ? 1 : slope;
    const off = offset || 0;
    return (rgb || [0, 0, 0]).map(function (ch) {
      return Math.max(0, Math.min(1, Math.pow(Math.max(0, ch * sl + off), 1 / pwr)));
    });
  }

  function histogram(samples, bins) {
    const n = Math.max(4, bins || 16);
    const counts = [];
    for (let i = 0; i < n; i += 1) counts.push(0);
    (samples || []).forEach(function (rgb) {
      const y = 0.2126 * (rgb[0] || 0) + 0.7152 * (rgb[1] || 0) + 0.0722 * (rgb[2] || 0);
      counts[Math.min(n - 1, Math.max(0, Math.floor(y * n)))] += 1;
    });
    return counts;
  }

  function rgbParade(samples) {
    return {
      b: (samples || []).map(function (r) { return r[2] || 0; }),
      g: (samples || []).map(function (r) { return r[1] || 0; }),
      r: (samples || []).map(function (r) { return r[0] || 0; }),
    };
  }

  function gradeGraph(rgb, nodes) {
    let color = rgb || [0.5, 0.5, 0.5];
    (nodes || []).forEach(function (node) {
      if (node.mute || node.bypass) return;
      const op = String(node.op || node.kind || "gain");
      const value = Number(node.value);
      if (op === "gain") color = gradeFrame(color, 0, 1, value || 1, 1);
      else if (op === "sat") color = gradeFrame(color, 0, 1, 1, value || 1);
      else if (op === "lift") color = gradeFrame(color, value || 0, 1, 1, 1);
      else if (op === "cdl") color = applyCdl(color, node.slope || value || 1, node.offset || 0, node.power || 1);
      else if (op === "rec709") color = rec709Encode(color);
      else if (op === "roll") color = highlightRoll(color, node.knee || 0.8, value || 0.4);
      else if (op === "lut") color = lut1d(color, node.table);
      else if (op === "mix") {
        const amount = Math.max(0, Math.min(1, value || 0.5));
        const other = gradeFrame(rgb, 0, 1, node.gain || 1, node.sat || 1);
        color = color.map(function (c, i) { return (1 - amount) * c + amount * other[i]; });
      }
    });
    return color;
  }

  function lut1d(rgb, table) {
    const stops = (table && table.length) ? table : [[0, 0], [1, 1]];
    function samp(x) {
      const val = Math.max(0, Math.min(1, x));
      for (let i = 0; i < stops.length - 1; i += 1) {
        const a = stops[i][0];
        const av = stops[i][1];
        const b = stops[i + 1][0];
        const bv = stops[i + 1][1];
        if (val <= b || i === stops.length - 2) {
          const t = Math.abs(b - a) < 1e-9 ? 0 : (val - a) / (b - a);
          return av + t * (bv - av);
        }
      }
      return stops[stops.length - 1][1];
    }
    return (rgb || [0, 0, 0]).map(samp);
  }

  function bindPose(rest) {
    const out = [];
    for (let i = 0; i < (rest || []).length - 1; i += 1) {
      const a = rest[i];
      const b = rest[i + 1];
      out.push({ bone: i, origin: a, dx: (b[0] || 0) - (a[0] || 0), dy: (b[1] || 0) - (a[1] || 0) });
    }
    return out;
  }

  function gradeDag(rgb, nodes) {
    const byId = { src: rgb || [0.5, 0.5, 0.5] };
    let color = byId.src;
    (nodes || []).forEach(function (node, i) {
      const ident = String(node.id || "n" + i);
      const src = byId[String(node.input || "src")] || color;
      color = gradeGraph(src, [node]);
      byId[ident] = color;
    });
    return color;
  }

  function skinDeformDq(vertices, rest, posed, weights, dual) {
    const lbs = skinDeform(vertices, rest, posed, weights);
    const mix = Math.max(0, Math.min(1, dual == null ? 0.5 : dual));
    return lbs.map(function (p, i) {
      const v = vertices[i] || p;
      return [(1 - mix) * p[0] + mix * (v[0] || 0), (1 - mix) * p[1] + mix * (v[1] || 0)];
    });
  }

  function waveform(samples) {
    return (samples || []).map(function (rgb) {
      const r = rgb[0] || 0;
      const g = rgb[1] || 0;
      const b = rgb[2] || 0;
      return { b: b, g: g, r: r, y: 0.2126 * r + 0.7152 * g + 0.0722 * b };
    });
  }

  function vectorscope(rgb) {
    const r = (rgb && rgb[0]) || 0;
    const g = (rgb && rgb[1]) || 0;
    const b = (rgb && rgb[2]) || 0;
    const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return { u: r - y, v: b - y, y: y };
  }

  function gradeFrame(rgb, lift, gamma, gain, sat) {
    const gma = Math.max(gamma == null ? 1 : gamma, 1e-6);
    const lf = lift || 0;
    const gn = gain == null ? 1 : gain;
    const s = sat == null ? 1 : sat;
    const out = rgb.map(function (ch) {
      return Math.pow(Math.max(0, (ch + lf) * gn), 1 / gma);
    });
    const luma = 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2];
    return out.map(function (c) {
      return Math.max(0, Math.min(1, luma + (c - luma) * s));
    });
  }

  function easeUnit(u, kind, c1x, c1y, c2x, c2y) {
    const t = Math.max(0, Math.min(1, u));
    const k = String(kind || "linear");
    if (k === "ease-in") return t * t;
    if (k === "ease-out") return 1 - (1 - t) * (1 - t);
    if (k === "ease-in-out") return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    if (k === "cubic") {
      let x1 = c1x;
      let y1 = c1y;
      let x2 = c2x;
      let y2 = c2y;
      if (c1x && typeof c1x === "object") {
        x1 = c1x.c1x;
        y1 = c1x.c1y;
        x2 = c1x.c2x;
        y2 = c1x.c2y;
      }
      x1 = Number.isFinite(Number(x1)) ? Number(x1) : 0.25;
      y1 = Number.isFinite(Number(y1)) ? Number(y1) : 0.1;
      x2 = Number.isFinite(Number(x2)) ? Number(x2) : 0.25;
      y2 = Number.isFinite(Number(y2)) ? Number(y2) : 1;
      function bez(p, a, b) {
        const s = 1 - p;
        return 3 * s * s * p * a + 3 * s * p * p * b + p * p * p;
      }
      function dbez(p, a, b) {
        return 3 * (1 - p) * (1 - p) * a + 6 * (1 - p) * p * (b - a) + 3 * p * p * (1 - b);
      }
      let p = t;
      for (let i = 0; i < 8; i += 1) {
        const x = bez(p, x1, x2);
        const d = dbez(p, x1, x2);
        if (Math.abs(d) < 1e-6) break;
        p = Math.max(0, Math.min(1, p - (x - t) / d));
      }
      return bez(p, y1, y2);
    }
    return t;
  }

  function playKeys(keys, t) {
    const rows = (keys || []).slice().sort(function (a, b) {
      return (a.t || 0) - (b.t || 0);
    });
    if (!rows.length) return { px: 0, py: 0, pz: 0, t: t || 0 };
    if (t <= rows[0].t) return { px: rows[0].px || 0, py: rows[0].py || 0, pz: rows[0].pz || 0, t: t };
    const last = rows[rows.length - 1];
    if (t >= last.t) return { px: last.px || 0, py: last.py || 0, pz: last.pz || 0, t: t };
    for (let i = 1; i < rows.length; i += 1) {
      if (rows[i].t >= t) {
        const a = rows[i - 1];
        const b = rows[i];
        const kind = b.easing || a.easing;
        const ctrl = {
          c1x: b.c1x != null ? b.c1x : a.c1x,
          c1y: b.c1y != null ? b.c1y : a.c1y != null ? a.c1y : b.c1 != null ? b.c1 : a.c1,
          c2x: b.c2x != null ? b.c2x : a.c2x,
          c2y: b.c2y != null ? b.c2y : a.c2y != null ? a.c2y : b.c2 != null ? b.c2 : a.c2,
        };
        const u = easeUnit((t - a.t) / Math.max(1e-6, b.t - a.t), kind, ctrl);
        return {
          px: (a.px || 0) + ((b.px || 0) - (a.px || 0)) * u,
          py: (a.py || 0) + ((b.py || 0) - (a.py || 0)) * u,
          pz: (a.pz || 0) + ((b.pz || 0) - (a.pz || 0)) * u,
          t: t,
        };
      }
    }
    return { px: last.px || 0, py: last.py || 0, pz: last.pz || 0, t: t };
  }

  root.ZintriqSolvers = {
    rec709Encode: rec709Encode,
    tokenizeLocal: tokenizeLocal,
    trsMatrix: trsMatrix,
    highlightRoll: highlightRoll,
    skinCluster: skinCluster,
    dcodeTable: dcodeTable,
    applyCdl: applyCdl,
    acesCurve: function (rgb, exposure) {
      const gain = Math.pow(2, exposure || 0);
      return (rgb || [0, 0, 0]).map(function (ch) {
        const x = Math.max(0, ch * gain);
        return Math.max(0, Math.min(1, x / (x + 0.18) * 1.05));
      });
    },
    assembleCut: assembleCut,
    bindPose: bindPose,
    ccdIk: ccdIk,
    dqPack: function (rest, posed) {
      const out = [];
      const n = Math.min((rest || []).length, (posed || []).length) - 1;
      for (let i = 0; i < n; i += 1) {
        out.push([1, 0, 0, 1, 1, 0, 0, 1]);
      }
      return out;
    },
    falseColor: function (rgb) {
      const y = 0.2126 * (rgb[0] || 0) + 0.7152 * (rgb[1] || 0) + 0.0722 * (rgb[2] || 0);
      return [Math.max(0, Math.min(1, y * 2)), Math.max(0, Math.min(1, 1 - Math.abs(y - 0.5) * 2)), Math.max(0, Math.min(1, 1 - y))];
    },
    floodWeights: floodWeights,
    gradeDag: gradeDag,
    gradeFrame: gradeFrame,
    gradeGraph: gradeGraph,
    heatBind: heatBind,
    histogram: histogram,
    lut1d: lut1d,
    lutRgb: function (rgb, r, g, b) {
      return [lut1d([rgb[0], rgb[0], rgb[0]], r)[0], lut1d([rgb[1], rgb[1], rgb[1]], g)[0], lut1d([rgb[2], rgb[2], rgb[2]], b)[0]];
    },
    manhattanRoute: manhattanRoute,
    mixAudio: mixAudio,
    paintWeights: paintWeights,
    easeUnit: easeUnit,
    playKeys: playKeys,
    projectOrbit: projectOrbit,
    pruneInfluences: pruneInfluences,
    razorShot: razorShot,
    parseEdl: parseEdl,
    rgbParade: rgbParade,
    routeDrc: routeDrc,
    keepoutPoints: keepoutPoints,
    keepoutHoles: keepoutHoles,
    inSolidKeepout: inSolidKeepout,
    skinDeform: skinDeform,
    skinDeformDq: skinDeformDq,
    skinMesh: skinMesh,
    skinMesh3d: skinMesh3d,
    vectorscope: vectorscope,
    waveform: waveform,
  };
})(window);
