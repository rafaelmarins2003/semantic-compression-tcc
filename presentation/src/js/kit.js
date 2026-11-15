/* kit.js — utilidades de desenho e animação. Sem dependências.
   Toda animação é uma função pura do progresso p ∈ [0, 1]: o motor pode tocar,
   concluir ou desfazer qualquer passo sem estado escondido. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const K = (window.K = {});
  window.SLIDES = [];

  K.clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
  K.lerp = (a, b, t) => a + (b - a) * t;
  K.seg = (p, a, b) => K.clamp((p - a) / (b - a));
  K.ease = {
    out: (t) => 1 - Math.pow(1 - t, 3),
    in: (t) => t * t * t,
    io: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    back: (t) => 1 + 2.70158 * Math.pow(t - 1, 3) + 1.70158 * Math.pow(t - 1, 2),
  };
  K.fmt = (n, d = 1) => n.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  K.int = (n) => Math.round(n).toLocaleString('pt-BR');

  K.h = (html) => {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  };
  K.s = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) k === 'text' ? (e.textContent = attrs[k]) : e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  K.text = (el, s) => { if (el.textContent !== s) el.textContent = s; };
  K.op = (el, v) => { el.style.opacity = v; };
  // Retângulo de `el` em coordenadas do palco, relativo a `box`.
  K.rectIn = (el, box) => {
    const s = window.DECK_SCALE || 1, a = el.getBoundingClientRect(), b = box.getBoundingClientRect();
    return { x: (a.left - b.left) / s, y: (a.top - b.top) / s, w: a.width / s, h: a.height / s };
  };

  const ICONS = {
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    cross: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    arrow: '<path d="M4 12h15M13 6l6 6-6 6"/>',
    back: '<path d="M20 12H5M11 6l-6 6 6 6"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
    doc: '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/>',
    scale: '<path d="M12 4v16M6 20h12M5 8h14M5 8l-2.5 6a3 3 0 005 0zM19 8l-2.5 6a3 3 0 005 0z"/>',
    ruler: '<path d="M3 16L16 3l5 5L8 21zM7 12l2 2M10 9l2 2M13 6l2 2"/>',
    stack: '<path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5"/>',
    braces: '<path d="M9 4c-2 0-3 1-3 3v2c0 1.5-1 3-2.5 3C5 12 6 13.500 6 15v2c0 2 1 3 3 3M15 4c2 0 3 1 3 3v2c0 1.500 1 3 2.500 3-1.500 0-2.500 1.500-2.500 3v2c0 2-1 3-3 3"/>',
  };
  K.icon = (name, cls = '') => `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

  // Contorno de engrenagem centrado em (0, 0).
  K.gear = (R, r, n) => {
    const step = (Math.PI * 2) / n;
    let d = '';
    for (let i = 0; i < n; i++) {
      const a = i * step;
      [[r, a - step * 0.27], [R, a - step * 0.13], [R, a + step * 0.13], [r, a + step * 0.27]].forEach(([rad, ang], j) => {
        d += (i + j === 0 ? 'M' : 'L') + (Math.cos(ang) * rad).toFixed(2) + ',' + (Math.sin(ang) * rad).toFixed(2);
      });
    }
    return d + 'Z';
  };

  // Rota ortogonal com cantos arredondados.
  K.route = (pts, r = 14) => {
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const d1 = Math.hypot(x1 - x0, y1 - y0), d2 = Math.hypot(x2 - x1, y2 - y1);
      const rr = Math.min(r, d1 / 2, d2 / 2);
      d += ` L${x1 - ((x1 - x0) / d1) * rr},${y1 - ((y1 - y0) / d1) * rr} Q${x1},${y1} ${x1 + ((x2 - x1) / d2) * rr},${y1 + ((y2 - y1) / d2) * rr}`;
    }
    const z = pts[pts.length - 1];
    return d + ` L${z[0]},${z[1]}`;
  };

  // Traço que se desenha com o progresso.
  K.stroke = (path) => {
    const len = path.getTotalLength();
    path.style.strokeDasharray = len;
    const o = { path, len, set(p) { path.style.strokeDashoffset = len * (1 - K.clamp(p)); }, at: (t) => path.getPointAtLength(len * K.clamp(t)) };
    o.set(0);
    return o;
  };

  /* ── BPMN ────────────────────────────────────────────────────────────── */
  K.bpmn = (root, opt = {}) => {
    const fs = opt.fs || 22;
    const gF = K.s('g', {}, root), gN = K.s('g', {}, root), gT = K.s('g', {}, root);
    const api = { n: {}, f: {} };
    const node = (id, cx, cy, build) => {
      const g = K.s('g', { class: 'bp-node' }, gN);
      build(g);
      const o = {
        g, cx, cy,
        show(p) {
          p = K.clamp(p);
          g.setAttribute('transform', `translate(${cx},${cy}) scale(${0.55 + 0.45 * K.ease.back(p)})`);
          g.style.opacity = K.clamp(p * 2.4);
        },
        hit(on) { g.classList.toggle('hit', !!on); },
      };
      o.show(1);
      return (api.n[id] = o);
    };
    api.task = (id, cx, cy, label, o = {}) => node(id, cx, cy, (g) => {
      const w = o.w || 170, h = o.h || 80, f = o.fs || fs, lines = String(label).split('\n');
      K.s('rect', { x: -w / 2, y: -h / 2, width: w, height: h, rx: 13, class: 'bp-shape' }, g);
      lines.forEach((ln, i) => K.s('text', { x: 0, y: (i - (lines.length - 1) / 2) * f * 1.2, class: 'bp-label', 'font-size': f, text: ln }, g));
    });
    api.event = (id, cx, cy, kind, label, o = {}) => node(id, cx, cy, (g) => {
      const r = o.r || 21;
      K.s('circle', { r, class: 'bp-shape' + (kind === 'start' ? '' : ' bp-end') }, g);
      if (kind === 'error') K.s('path', { d: 'M-8,7 L-3,-8 L2,2 L8,-7 L3,8 L-2,-2 Z', class: 'bp-glyph' }, g);
      if (label) K.s('text', { x: 0, y: r + 28, class: 'bp-cap', text: label }, g);
    });
    api.gateway = (id, cx, cy, label, o = {}) => node(id, cx, cy, (g) => {
      const r = o.r || 38, k = r * 0.3;
      K.s('path', { d: `M0,${-r} L${r},0 L0,${r} L${-r},0 Z`, class: 'bp-shape' }, g);
      K.s('path', { d: `M${-k},${-k} L${k},${k} M${k},${-k} L${-k},${k}`, class: 'bp-x' }, g);
      if (label) K.s('text', { x: o.lx || 0, y: o.ly != null ? o.ly : -r - 14, class: 'bp-cap', 'text-anchor': o.anchor || 'middle', text: label }, g);
    });
    api.flow = (id, pts, o = {}) => {
      const g = K.s('g', { class: 'bp-flow' }, gF);
      const path = K.s('path', { d: typeof pts === 'string' ? pts : K.route(pts, o.r || 14), class: 'bp-edge' }, g);
      const head = K.s('path', { d: 'M1,0 L-13,-6.500 L-13,6.500 Z', class: 'bp-head' }, g);
      const lab = o.label ? K.s('text', { x: o.lx, y: o.ly, class: 'bp-cond', text: o.label }, g) : null;
      const len = path.getTotalLength();
      const a = path.getPointAtLength(len), b = path.getPointAtLength(Math.max(0, len - 3));
      head.setAttribute('transform', `translate(${a.x},${a.y}) rotate(${(Math.atan2(a.y - b.y, a.x - b.x) * 180) / Math.PI})`);
      path.style.strokeDasharray = `${len} ${len}`;
      const f = {
        g, path, len, lab,
        show(p) {
          p = K.clamp(p);
          path.style.strokeDashoffset = len * (1 - K.ease.io(p));
          head.style.opacity = K.seg(p, 0.82, 1);
          g.style.opacity = p > 0 ? 1 : 0;
          if (lab) lab.style.opacity = K.seg(p, 0.3, 0.75);
        },
        at: (t) => path.getPointAtLength(len * K.clamp(t)),
      };
      f.show(1);
      return (api.f[id] = f);
    };
    api.token = (cls = '') => {
      const c = K.s('circle', { r: 11, class: 'bp-token ' + cls }, gT);
      c.style.opacity = 0;
      return { el: c, to(pt, op = 1) { c.setAttribute('cx', pt.x); c.setAttribute('cy', pt.y); c.style.opacity = op; }, hide() { c.style.opacity = 0; } };
    };
    return api;
  };

  // Processo do Código 1 da monografia ("Order Processing with Retry"), em 980 × 560.
  K.orderDiagram = (g) => {
    const b = K.bpmn(g);
    b.flow('f1', [[70, 170], [113, 170]]);
    b.flow('f2', [[285, 170], [323, 170]]);
    b.flow('f3', [[495, 170], [549, 170]]);
    b.flow('yes', [[630, 170], [683, 170]], { label: 'yes', lx: 654, ly: 152 });
    b.flow('f5', [[835, 170], [879, 170]]);
    b.flow('no', [[590, 210], [590, 389]], { label: 'no', lx: 612, ly: 300 });
    b.flow('loop', [[550, 430], [200, 430], [200, 212]], { label: 'yes', lx: 516, ly: 412, r: 22 });
    b.flow('err', [[630, 430], [734, 430]], { label: 'no', lx: 672, ly: 412 });
    b.event('start', 50, 170, 'start');
    b.task('fetch', 200, 170, 'Fetch data');
    b.task('validate', 410, 170, 'Validate');
    b.gateway('valid', 590, 170, 'Valid?');
    b.task('process', 760, 170, 'Process', { w: 150 });
    b.event('end', 905, 170, 'end');
    b.gateway('retry', 590, 430, 'Retry?', { ly: 70 });
    b.event('invalid', 760, 430, 'error', 'Invalid');
    return b;
  };

  /* ── código com realce ───────────────────────────────────────────────── */
  const DSL_KW = /^(@lane|process|pool|collaboration|start|end|catch|throw|task|user|service|manual|script|send|receive|rule|xor|and|or|event|subprocess|call|note|message|from|to)\b(:[a-z]+)?/;
  K.lexDSL = (line) => {
    const out = [];
    let i = 0, m;
    while (i < line.length) {
      const r = line.slice(i);
      if ((m = /^\s+/.exec(r))) out.push(['ws', m[0]]);
      else if ((m = /^#"[^"]*"/.exec(r)) || (m = /^#[A-Za-z_]\w*/.exec(r))) out.push(['ref', m[0]]);
      else if ((m = /^"[^"]*"/.exec(r))) out.push(['str', m[0]]);
      else if ((m = /^->/.exec(r))) out.push(['op', m[0]]);
      else if ((m = /^\[[^\]]*\]/.exec(r))) out.push(['cond', m[0]]);
      else if ((m = DSL_KW.exec(r))) out.push(['kw', m[0]]);
      else if ((m = /^[{}();,]/.exec(r))) out.push(['pun', m[0]]);
      else { m = /^\S+/.exec(r); out.push(['id', m[0]]); }
      i += m[0].length;
    }
    return out;
  };
  // "info": o que descreve o processo (tipos de nó, rótulos, condições).
  const NODE_TAG = /^(startEvent|endEvent|serviceTask|userTask|task|exclusiveGateway|parallelGateway|errorEventDefinition)$/;
  K.lexXML = (line) => {
    const out = [];
    let i = 0, m, attr = '';
    while (i < line.length) {
      const r = line.slice(i);
      if ((m = /^\s+/.exec(r))) out.push(['ws', m[0]]);
      else if ((m = /^<(\/?)([\w:]+)/.exec(r))) {
        out.push(['pun', '<' + m[1]]);
        out.push([!m[1] && NODE_TAG.test(m[2]) ? 'tag info' : 'tag', m[2]]);
      } else if ((m = /^\/?>/.exec(r))) out.push(['pun', m[0]]);
      else if ((m = /^([\w:]+)=/.exec(r))) { attr = m[1]; out.push(['attr', m[0]]); }
      else if ((m = /^"[^"]*"/.exec(r))) out.push([attr === 'name' ? 'val info' : 'val', m[0]]);
      else { m = /^[^<\s]+/.exec(r); out.push([m[0] === '…' ? 'pun' : 'txt info', m[0]]); }
      i += m[0].length;
    }
    return out;
  };
  K.code = (host, text, lang) => {
    host.classList.add('code');
    const lex = lang === 'xml' ? K.lexXML : K.lexDSL, lines = [], toks = [];
    text.split('\n').forEach((ln, li) => {
      const row = K.h('<div class="ln"></div>');
      lex(ln).forEach(([cls, s]) => {
        if (cls === 'ws') return void row.appendChild(document.createTextNode(s));
        const sp = document.createElement('span');
        sp.className = 'tk ' + cls.replace(/^(\w+)/, 'k-$1');
        sp.textContent = s;
        sp._line = li;
        row.appendChild(sp);
        toks.push(sp);
      });
      if (!row.childNodes.length) row.textContent = ' ';
      host.appendChild(row);
      lines.push(row);
    });
    return {
      host, lines, toks,
      show(n) {
        const k = Math.floor(n + 1e-6);
        for (let i = 0; i < toks.length; i++) {
          toks[i].classList.toggle('hid', i >= k);
          toks[i].classList.toggle('cur', i === k - 1 && k < toks.length && k > 0);
        }
      },
      showLines(n) { lines.forEach((l, i) => l.classList.toggle('hid', i >= n)); },
      mark(li) { lines.forEach((l, i) => l.classList.toggle('hot', i === li)); },
      find(str, nth = 0) { return toks.filter((t) => t.textContent === str)[nth]; },
    };
  };

  /* ── minimapa do exemplo: 30 linhas de XML que se fundem nas 12 da DSL ── */
  K.XML2DSL = [0, 0, 1, 2, 2, 3, 3, 4, 5, 5, 5, 5, 5, 5, 6, 7, 7, 7, 8, 8, 8, 8, 8, 8, 6, 6, 6, 4, 11, 11];
  K.minimap = (svg, o = {}) => {
    const E = window.DADOS.exemplo, cw = o.cw || 3.4, bh = o.h || 6, lp = o.pitch || 13, cap = o.cap || 100;
    const info = (l) => { const ind = l.length - l.trimStart().length; return { ind, len: Math.min(l.length, cap) - ind }; };
    const X = E.xml.split('\n').map(info), L = E.dsl.split('\n').map(info);
    const g = K.s('g', { class: 'mini' }, svg), yD = (j) => ((X.length - L.length) / 2 + j) * lp;
    const bars = X.map((a, i) => ({ el: K.s('rect', { height: bh, rx: bh / 2 }, g), a, d: L[K.XML2DSL[i]], yx: i * lp, yd: yD(K.XML2DSL[i]), i }));
    const lone = L.map((d, j) => (K.XML2DSL.includes(j) ? null : { el: K.s('rect', { height: bh, rx: bh / 2, x: d.ind * cw, y: yD(j), width: d.len * cw }, g) })).filter(Boolean);
    return {
      g, height: X.length * lp,
      // e: 0 = XML, 1 = DSL
      set(e) {
        g.style.setProperty('--mix', (1 - K.clamp(e)) * 100 + '%');
        for (const b of bars) {
          const t = K.ease.io(K.seg(e, (b.i / X.length) * 0.35, (b.i / X.length) * 0.35 + 0.65));
          b.el.setAttribute('x', K.lerp(b.a.ind, b.d.ind, t) * cw);
          b.el.setAttribute('y', K.lerp(b.yx, b.yd, t));
          b.el.setAttribute('width', K.lerp(b.a.len, b.d.len, t) * cw);
        }
        for (const b of lone) b.el.style.opacity = K.seg(e, 0.7, 1);
      },
    };
  };

  /* ── tira de 138 gerações: 46 itens (colunas) × 3 repetições (linhas) ── */
  const WHY = { v: 'válida no XSD', u: 'referência não declarada', m: 'referência fora de posição', s: 'outra falha de sintaxe', o: 'bloco não fechado', t: 'truncada no limite de tokens', x: 'XML recusado pelo XSD' };
  K.strip = (svg, arm, o = {}) => {
    const D = window.DADOS, codes = o.codes || D.bracos[arm];
    const R = o.r || 9, pitch = o.pitch || 26, x0 = (o.x || 0) + pitch / 2, y0 = (o.y || 0) + pitch / 2;
    const g = K.s('g', { class: 'strip ' + (o.cls || '') }, svg), dots = [];
    for (let i = 0; i < codes.length; i++) {
      const col = Math.floor(i / 3), row = i % 3;
      const el = K.s('circle', { cx: x0 + col * pitch, cy: y0 + row * pitch, r: 2.4, class: 'sd' }, g);
      dots.push({ el, col, row, i, x: x0 + col * pitch, y: y0 + row * pitch });
    }
    const tip = (d, cs, name) => {
      const note = D.notas[name] && D.notas[name][d.i] ? ' ' + D.notas[name][d.i] : '';
      d.el.setAttribute('data-tip', `${D.itens[d.col]}, repetição ${d.row + 1}: ${WHY[cs[d.i]]}${note}`);
    };
    const paint = (d, code, t) => {
      const el = d.el;
      if (t <= 0) { el.setAttribute('r', 2.4); el.setAttribute('class', 'sd'); return; }
      if (code === 'v') { el.setAttribute('class', 'sd v'); el.setAttribute('r', K.lerp(2.4, R, K.ease.back(t))); }
      else { el.setAttribute('class', 'sd x'); el.setAttribute('r', K.lerp(2.4, R * 0.74, K.ease.out(t))); }
    };
    const delay = (d) => ((d.col + d.row * 0.4) / 47) * 0.8;
    if (!o.plain) dots.forEach((d) => tip(d, codes, arm));
    return {
      g, dots, codes, R, pitch,
      fill(p) { for (const d of dots) paint(d, codes[d.i], K.seg(p, delay(d), delay(d) + 0.16)); },
      // Passa do desfecho de `from` para o de `codes`, ponto a ponto.
      morph(p, from) {
        for (const d of dots) {
          const a = from[d.i] === 'v', b = codes[d.i] === 'v', t = K.seg(p, delay(d), delay(d) + 0.18);
          if (a === b) paint(d, codes[d.i], 1);
          else if (t < 0.5) paint(d, from[d.i], 1 - t * 2 + 0.001);
          else paint(d, codes[d.i], (t - 0.5) * 2);
        }
      },
      count(cs = codes) { return [...cs].filter((c) => c === 'v').length; },
    };
  };
})();
