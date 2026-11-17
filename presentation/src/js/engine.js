/* engine.js — palco, navegação e passos.
   Cada slide tem passos; cada passo é { dur, draw(p, ctx) } com p ∈ [0, 1].
   O passo 0 toca ao entrar. Avançar conclui o passo atual e toca o seguinte;
   voltar desfaz. Elementos com data-at="k" recebem .on do passo k em diante. */
(function () {
  'use strict';
  const K = window.K, defs = window.SLIDES;
  const Q = new URLSearchParams(location.search);
  const PRINT = Q.has('print');
  const INSTANT = PRINT || Q.has('instant');
  // Depuração: ?instant&at=0.4 desenha o passo do hash em 40%; ?time=3 congela os laços.
  const AT = Q.has('at') ? +Q.get('at') : 1;
  const TIME = Q.has('time') ? +Q.get('time') : null;
  if (INSTANT) document.documentElement.classList.add('instant');
  const stage = document.getElementById('stage');
  const $ = (id) => document.getElementById(id);
  const st = { i: -1, k: 0, anim: null, typed: '' };
  const acts = [];

  /* tema */
  /* Cada arquivo abre no próprio tema (apresentacao-clara.html já vem com data-theme="light").
     ?theme= na URL sobrepõe. O tema não fica salvo no navegador: arquivos locais dividem o
     mesmo armazenamento, e testar T num arquivo faria o outro abrir no tema errado. */
  const theme = Q.get('theme');
  if (theme === 'light') document.documentElement.dataset.theme = 'light';
  if (theme === 'dark') delete document.documentElement.dataset.theme;

  function fit() {
    if (PRINT) { window.DECK_SCALE = 1; return; }
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    window.DECK_SCALE = s;
    stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px,${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  }

  function build() {
    const first = stage.firstChild;
    defs.forEach((d, i) => {
      const el = document.createElement('section');
      el.className = 'slide s-' + d.id;
      el.innerHTML =
        (d.bare ? '' : `<header class="hd"><h1 class="h1">${d.title}</h1></header>${d.badge ? `<div class="explo">${d.badge}</div>` : ''}`) +
        (d.html || '') + (d.note ? `<footer class="note">${d.note}</footer>` : '') +
        `<div class="pn">${String(i + 1).padStart(2, '0')} / ${defs.length}</div>`;
      stage.insertBefore(el, first);
      d.el = el;
      d.ctx = { el, $: (q) => el.querySelector(q), $$: (q) => [...el.querySelectorAll(q)] };
      d.steps = [];
    });
    defs.forEach((d) => {
      const r = d.setup ? d.setup(d.ctx) : null;
      if (Array.isArray(r)) d.steps = r;
      let n = d.steps.length;
      d.el.querySelectorAll('[data-at]').forEach((e) => { n = Math.max(n, +e.dataset.at + 1); });
      d.n = Math.max(1, n);
    });
  }

  const draw = (d, j, p) => { const s = d.steps[j]; if (s && s.draw) s.draw(p, d.ctx); };
  function reveal(d, k) {
    d.el.querySelectorAll('[data-at]').forEach((e) => e.classList.toggle('on', +e.dataset.at <= k));
    d.el.dataset.step = k;
  }
  function apply(d, k, p) {
    for (let j = d.n - 1; j > k; j--) draw(d, j, 0);
    for (let j = 0; j < k; j++) draw(d, j, 1);
    draw(d, k, p);
    reveal(d, k);
  }
  function quiet(d, fn) {
    d.el.classList.add('instant');
    fn();
    void d.el.offsetWidth;
    if (!PRINT) d.el.classList.remove('instant');
  }
  function stop() {
    if (st.anim) { draw(st.anim.d, st.anim.k, 1); st.anim = null; }
  }
  function play() {
    const d = defs[st.i], s = d.steps[st.k];
    if (!s || !s.draw) return;
    if (!s.dur || INSTANT) return void s.draw(1, d.ctx);
    st.anim = { d, k: st.k, t0: performance.now(), dur: s.dur };
  }
  // mode: 'fwd' entra animando do passo 0; 'back' entra no estado final; 'jump' vai a um passo.
  function enter(i, k, mode) {
    i = K.clamp(i, 0, defs.length - 1);
    stop();
    const d = defs[i], old = defs[st.i];
    if (old && old !== d) old.el.classList.remove('active');
    st.i = i;
    if (mode === 'fwd') {
      st.k = 0;
      quiet(d, () => { apply(d, 0, 0); d.el.querySelectorAll('[data-at]').forEach((e) => e.classList.remove('on')); });
      d.el.classList.add('active');
      reveal(d, 0);
      play();
    } else {
      st.k = mode === 'back' ? d.n - 1 : K.clamp(k || 0, 0, d.n - 1);
      quiet(d, () => apply(d, st.k, 1));
      d.el.classList.add('active');
    }
    sync();
  }
  function next() {
    const d = defs[st.i];
    stop();
    if (st.k < d.n - 1) { st.k++; reveal(d, st.k); play(); sync(); }
    else if (st.i < defs.length - 1) enter(st.i + 1, 0, 'fwd');
  }
  function prev() {
    const d = defs[st.i];
    stop();
    if (st.k > 0) { st.k--; apply(d, st.k, 1); sync(); }
    else if (st.i > 0) enter(st.i - 1, 0, 'back');
  }
  function sync() {
    const d = defs[st.i];
    acts.forEach((a) => {
      a.el.classList.toggle('cur', a.name === d.act);
      const done = st.i > a.to ? 1 : st.i < a.from ? 0 : (st.i - a.from + (st.k + 1) / d.n) / (a.to - a.from + 1);
      a.fill.style.width = done * 100 + '%';
    });
    $('rail').style.opacity = d.bare ? 0 : 1;
    $('pgn').textContent = String(st.i + 1).padStart(2, '0') + ' / ' + defs.length;
    $('pgd').innerHTML = d.n > 1 ? Array.from({ length: d.n }, (_, j) => `<i class="${j <= st.k ? 'done' : ''}"></i>`).join('') : '';
    $('pg').style.opacity = d.bare ? 0 : 1;
    if (!PRINT) history.replaceState(null, '', '#' + (st.i + 1) + (st.k ? '.' + st.k : ''));
    document.querySelectorAll('#idx button').forEach((b, j) => b.classList.toggle('cur', j === st.i));
  }
  function frame(now) {
    const d = defs[st.i];
    if (st.anim) {
      const a = st.anim, p = Math.min(1, (now - a.t0) / a.dur);
      draw(a.d, a.k, p);
      if (p >= 1) st.anim = null;
    }
    if (d && d.loop) d.loop(TIME == null ? now / 1000 : TIME, d.ctx, { k: st.k, busy: !!st.anim, last: st.k === d.n - 1 });
    requestAnimationFrame(frame);
  }

  /* moldura */
  function chrome() {
    stage.insertAdjacentHTML('beforeend', `
      <nav id="rail"></nav>
      <div id="pg"><span class="dots" id="pgd"></span><span id="pgn"></span></div>
      <div id="tip"></div><div id="toast"></div><div id="black"></div>
      <div class="over" id="idx"><h2>Índice · clique para ir · G fecha</h2><div class="grid"></div></div>
      <div class="over" id="help"><h2>Atalhos</h2><dl>
        <dt>→ espaço PageDown clique</dt><dd>avança um passo</dd>
        <dt>← PageUp</dt><dd>volta um passo</dd>
        <dt>↓ ↑</dt><dd>próximo slide, slide anterior</dd>
        <dt>número + Enter</dt><dd>vai para o slide</dd>
        <dt>G</dt><dd>índice dos slides</dd>
        <dt>R</dt><dd>repete a animação do slide</dd>
        <dt>F</dt><dd>tela cheia</dd>
        <dt>T</dt><dd>tema claro ou escuro</dd>
        <dt>B</dt><dd>tela preta</dd>
        <dt>?</dt><dd>esta ajuda</dd></dl></div>`);
    const rail = $('rail');
    defs.forEach((d, i) => {
      if (!d.act) return;
      let a = acts[acts.length - 1];
      if (!a || a.name !== d.act) {
        const el = K.h(`<span>${d.act}<i><b></b></i></span>`);
        rail.appendChild(el);
        acts.push((a = { name: d.act, from: i, to: i, el, fill: el.querySelector('b') }));
      }
      a.to = i;
    });
    const grid = stage.querySelector('#idx .grid');
    defs.forEach((d, i) => {
      const b = K.h(`<button><small>${String(i + 1).padStart(2, '0')}${d.act ? ' · ' + d.act : ''}</small><span>${d.name || d.title.replace(/<[^>]+>/g, '')}</span></button>`);
      b.addEventListener('click', (e) => { e.stopPropagation(); toggle('idx', false); enter(i, 0, 'fwd'); });
      grid.appendChild(b);
    });
  }
  const toggle = (id, on) => $(id).classList.toggle('open', on);
  const anyOpen = () => document.querySelector('.over.open');
  let toastT;
  function toast(s) {
    const t = $('toast');
    t.textContent = s;
    t.style.opacity = 1;
    clearTimeout(toastT);
    toastT = setTimeout(() => (t.style.opacity = 0), 1100);
  }

  function keys(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if ($('black').style.display === 'block' && k !== 'F5') { $('black').style.display = 'none'; return e.preventDefault(); }
    if (k === 'Escape') { document.querySelectorAll('.over.open').forEach((o) => o.classList.remove('open')); st.typed = ''; return; }
    if (/^\d$/.test(k)) { st.typed += k; return toast('ir para ' + st.typed + ' ⏎'); }
    if (k === 'Enter' && st.typed) { const n = +st.typed; st.typed = ''; toggle('idx', false); return enter(n - 1, 0, 'fwd'); }
    st.typed = '';
    const act = {
      ArrowRight: next, PageDown: next, ' ': next, Enter: next, n: next,
      ArrowLeft: prev, PageUp: prev, Backspace: prev, p: prev,
      ArrowDown: () => enter(st.i + 1, 0, 'fwd'), ArrowUp: () => enter(st.i - 1, 0, 'back'),
      Home: () => enter(0, 0, 'fwd'), End: () => enter(defs.length - 1, 0, 'fwd'),
      r: () => enter(st.i, 0, 'fwd'),
      g: () => { toggle('help', false); $('idx').classList.toggle('open'); },
      '?': () => { toggle('idx', false); $('help').classList.toggle('open'); },
      h: () => { toggle('idx', false); $('help').classList.toggle('open'); },
      f: () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {})),
      t: () => {
        const light = document.documentElement.dataset.theme !== 'light';
        light ? (document.documentElement.dataset.theme = 'light') : delete document.documentElement.dataset.theme;
      },
      b: () => ($('black').style.display = 'block'), '.': () => ($('black').style.display = 'block'),
    }[k.length === 1 ? k.toLowerCase() : k];
    if (act) { e.preventDefault(); act(); }
  }

  function pointer() {
    stage.addEventListener('click', (e) => {
      if (anyOpen()) return void (e.target.closest('.over') === e.target && e.target.classList.remove('open'));
      if ($('black').style.display === 'block') return void ($('black').style.display = 'none');
      e.shiftKey ? prev() : next();
    });
    stage.addEventListener('contextmenu', (e) => { e.preventDefault(); if (!anyOpen()) prev(); });
    let idle;
    addEventListener('mousemove', (e) => {
      document.body.classList.remove('nocursor');
      clearTimeout(idle);
      idle = setTimeout(() => document.body.classList.add('nocursor'), 2400);
      const tip = $('tip'), el = e.target.closest && e.target.closest('[data-tip]');
      if (!el) return void (tip.style.opacity = 0);
      const s = window.DECK_SCALE, b = stage.getBoundingClientRect();
      tip.textContent = el.getAttribute('data-tip');
      const x = (e.clientX - b.left) / s, y = (e.clientY - b.top) / s;
      tip.style.left = Math.min(x + 18, 1900 - tip.offsetWidth) + 'px';
      tip.style.top = Math.max(10, y - 52) + 'px';
      tip.style.opacity = 1;
    });
    let tx = null;
    addEventListener('touchstart', (e) => (tx = e.touches[0].clientX), { passive: true });
    addEventListener('touchend', (e) => {
      if (tx == null) return;
      const dx = e.changedTouches[0].clientX - tx;
      if (Math.abs(dx) > 50) dx < 0 ? next() : prev();
      tx = null;
    });
  }

  function start() {
    build();
    chrome();
    fit();
    if (PRINT) {
      document.body.classList.add('print');
      defs.forEach((d) => {
        d.el.classList.add('active', 'instant');
        apply(d, d.n - 1, 1);
        if (d.loop) d.loop(3.4, d.ctx, { k: d.n - 1, busy: false, last: true, still: true });
      });
      return;
    }
    addEventListener('resize', fit);
    addEventListener('keydown', keys);
    pointer();
    const m = /^#(\d+)(?:\.(\d+))?$/.exec(location.hash);
    m ? enter(+m[1] - 1, +(m[2] || 0), m[2] || INSTANT ? 'jump' : 'fwd') : enter(0, 0, 'fwd');
    if (INSTANT) { const d = defs[st.i]; apply(d, st.k, AT); }
    requestAnimationFrame(frame);
  }
  // As medidas de texto dependem das fontes embutidas: carrega antes de montar.
  const faces = ['500 60px Newsreader', 'italic 500 60px Newsreader', '500 20px "Libre Franklin"', '800 20px "Libre Franklin"', '500 20px "JetBrains Mono"', '700 20px "JetBrains Mono"'];
  const ready = document.fonts && document.fonts.load ? Promise.all(faces.map((f) => document.fonts.load(f))) : Promise.resolve();
  Promise.race([ready, new Promise((r) => setTimeout(r, 2500))]).then(start, start);
})();
