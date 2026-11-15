/* slides-b.js — proposta (slides 6 a 10). */
(function () {
  'use strict';
  const K = window.K, S = window.SLIDES, D = window.DADOS;
  const show = (el, p, dy = 6) => {
    el.style.opacity = K.clamp(p);
    el.style.transform = `translateY(${(1 - K.ease.out(K.clamp(p))) * dy}px)`;
  };
  const cap = (g, x, y, name, sub) => {
    const o = K.s('g', {}, g);
    K.s('text', { x, y, class: 'cap-n', text: name }, o);
    if (sub) K.s('text', { x, y: y + 29, class: 'cap-s', text: sub }, o);
    return o;
  };
  const bars = (g, text, x, y, cw, pitch, cls) =>
    text.split('\n').map((l, i) => {
      const ind = l.length - l.trimStart().length;
      return K.s('rect', { x: x + ind * cw, y: y + i * pitch, width: Math.max(3, (Math.min(l.length, 100) - ind) * cw), height: 5.5, rx: 2.75, class: cls }, g);
    });

  /* ── 6. A ideia ──────────────────────────────────────────────────────── */
  S.push({
    id: 'ideia', act: 'Proposta', name: 'A ideia',
    title: 'O modelo escreve pouco. O código escreve o resto.',
    html: `<div class="body"><svg class="fig pipe" viewBox="0 0 1700 714" width="1700" height="714"></svg></div>`,
    setup(c) {
      const svg = c.$('svg'), Y = 280, root = K.s('g', { transform: 'translate(62,0)' }, svg), b = K.bpmn(root);
      const F = [[214, 304], [496, 578], [720, 804], [1036, 1124], [1376, 1458]].map(([x1, x2], i) => b.flow('f' + i, [[x1, Y], [x2, Y]]));
      const G = () => K.s('g', { class: 'pg' }, root);
      // texto
      const gT = G();
      K.s('rect', { x: 20, y: Y - 120, width: 190, height: 240, rx: 5, class: 'card' }, gT);
      [150, 138, 146, 118, 150, 130, 142, 96].forEach((w, i) => K.s('rect', { x: 40, y: Y - 92 + i * 25, width: w, height: 5, rx: 2.5, class: 'tline' }, gT));
      cap(gT, 115, Y + 250, 'texto', 'descrição do processo');
      // LLM
      const gL = G();
      K.s('circle', { cx: 400, cy: Y, r: 90, class: 'prob' }, gL);
      K.s('text', { x: 400, y: Y, class: 'big-l', text: 'LLM' }, gL);
      cap(gL, 400, Y + 250, 'modelo de linguagem');
      // DSL
      const gD = G();
      K.s('rect', { x: 584, y: Y - 89, width: 130, height: 178, rx: 10, class: 'card k-dsl' }, gD);
      const bD = bars(gD, D.exemplo.dsl, 604, Y - 69, 2, 11.5, 'b-dsl');
      cap(gD, 649, Y + 250, 'DSL', '12 linhas');
      // transpilador
      const gP = G();
      K.s('rect', { x: 810, y: Y - 75, width: 220, height: 150, rx: 14, class: 'card solid' }, gP);
      const gear = K.s('path', { d: K.gear(46, 34, 10), class: 'gear', transform: `translate(920,${Y})` }, gP);
      K.s('circle', { cx: 920, cy: Y, r: 13, class: 'gear-h' }, gP);
      cap(gP, 920, Y + 250, 'transpilador');
      // XML
      const gX = G();
      K.s('rect', { x: 1130, y: Y - 192, width: 240, height: 385, rx: 10, class: 'card k-xml' }, gX);
      const bX = bars(gX, D.exemplo.xml, 1150, Y - 172, 2, 11.5, 'b-xml');
      cap(gX, 1250, Y + 250, 'BPMN 2.0 XML', '30 linhas');
      // XSD
      const gV = G();
      K.s('circle', { cx: 1510, cy: Y, r: 46, class: 'xsd' }, gV);
      K.s('path', { d: `M1490,${Y + 2} l14,14 l27,-30`, class: 'xsd-c' }, gV);
      cap(gV, 1510, Y + 250, 'XSD', 'esquema oficial');
      // chaves: quem escreve o quê
      const br = (x1, x2, txt, cls) => {
        const g = G();
        K.s('path', { d: `M${x1},${Y + 322} v12 H${x2} v-12`, class: 'brace ' + cls }, g);
        K.s('text', { x: (x1 + x2) / 2, y: Y + 372, class: 'brace-t', text: txt }, g);
        return g;
      };
      const b1 = br(310, 714, 'gerado pelo modelo: probabilístico', 'c-dsl'), b2 = br(810, 1556, 'gerado por código: determinístico', 'c-xml');
      const dots = F.map((_, i) => K.s('circle', { r: 4.5, class: 'pdot ' + (i < 1 ? '' : i < 3 ? 'c-dsl' : 'c-xml') }, root));
      c.loopFn = (t, on) => {
        gear.setAttribute('transform', `translate(920,${Y}) rotate(${(t * 36) % 360})`);
        dots.forEach((d, i) => {
          const u = (t * 0.55 + i * 0.37) % 1.6, pt = F[i].at(u);
          d.setAttribute('cx', pt.x);
          d.setAttribute('cy', pt.y);
          d.style.opacity = on && u < 1 ? Math.sin(u * Math.PI) : 0;
        });
      };
      return [{
        dur: 6200,
        draw(p) {
          show(gT, K.seg(p, 0.0, 0.1));
          F[0].show(K.seg(p, 0.08, 0.16));
          show(gL, K.seg(p, 0.12, 0.24));
          F[1].show(K.seg(p, 0.24, 0.31));
          show(gD, K.seg(p, 0.27, 0.35));
          bD.forEach((r, i) => (r.style.opacity = K.seg(p, 0.3 + i * 0.016, 0.33 + i * 0.016)));
          F[2].show(K.seg(p, 0.5, 0.57));
          show(gP, K.seg(p, 0.53, 0.63));
          F[3].show(K.seg(p, 0.62, 0.68));
          show(gX, K.seg(p, 0.64, 0.72));
          bX.forEach((r, i) => (r.style.opacity = K.seg(p, 0.66 + i * 0.006, 0.69 + i * 0.006)));
          F[4].show(K.seg(p, 0.85, 0.9));
          show(gV, K.seg(p, 0.88, 0.95));
          show(b1, K.seg(p, 0.9, 0.97), 8);
          show(b2, K.seg(p, 0.93, 1), 8);
        },
      }];
    },
    loop: (t, c, s) => c.loopFn(t, !s.busy && !s.still),
  });

  /* ── 7. BPMN-DSL ao vivo ─────────────────────────────────────────────── */
  S.push({
    id: 'dsl', act: 'Proposta', name: 'A BPMN-DSL',
    title: 'BPMN-DSL: o mesmo processo em 12 linhas.',
    html: `<div class="body">
      <div class="panel dslp" style="left:0;top:0;width:690px;height:600px">
        <div class="panel-hd"><span>saída do modelo em BPMN-DSL</span><span><b>286</b> caracteres</span></div>
        <div class="dsl"></div>
      </div>
      <div class="chips">
        <span><code>-&gt;</code>sequência</span><span><code>xor { }</code>decisão</span><span><code>#fetch</code>volta a um elemento já escrito</span>
      </div>
      <svg class="fig" viewBox="0 0 980 600" width="980" height="600" style="left:722px;top:30px"><g class="dia"></g></svg>
    </div>`,
    setup(c) {
      const code = K.code(c.$('.dsl'), D.exemplo.dsl, 'dsl'), b = K.orderDiagram(c.$('.dia')), tok = b.token(), chips = c.$('.chips');
      // token da DSL que faz cada elemento aparecer
      const when = { start: 3, f1: 4, fetch: 6, f2: 8, validate: 10, f3: 11, valid: 13, yes: 16, process: 18, f5: 19, end: 20, no: 22, retry: 24, loop: 28, err: 30, invalid: 32 };
      // percurso do token do processo: [elemento, linha da DSL]
      const run = [['start', 1], ['f1', 2], ['fetch', 2], ['f2', 3], ['validate', 3], ['f3', 4], ['valid', 4], ['no', 6], ['retry', 6], ['loop', 7], ['fetch', 2], ['f2', 3], ['validate', 3], ['f3', 4], ['valid', 4], ['yes', 5], ['process', 5], ['f5', 5], ['end', 5]];
      const segs = run.map(([id, ln]) => (b.f[id] ? { f: b.f[id], ln, len: b.f[id].len } : { n: b.n[id], ln, len: 95 }));
      const total = segs.reduce((a, s) => a + s.len, 0);
      const clear = () => { tok.hide(); code.mark(-1); Object.values(b.n).forEach((n) => n.hit(false)); };
      return [
        {
          dur: 7600,
          draw(p) {
            const n = K.seg(p, 0.03, 0.9) * code.toks.length;
            code.show(p >= 1 ? code.toks.length : n);
            for (const id in when) (b.n[id] || b.f[id]).show(K.seg(n, when[id] + 0.3, when[id] + 1.8));
            chips.style.opacity = K.seg(p, 0.92, 1);
          },
        },
        {
          dur: 8200,
          draw(p) {
            clear();
            if (p <= 0 || p >= 1) return;
            let L = p * total;
            for (const s of segs) {
              if (L <= s.len) {
                code.mark(s.ln);
                if (s.f) tok.to(s.f.at(L / s.len));
                else s.n.hit(true);
                return;
              }
              L -= s.len;
            }
          },
        },
      ];
    },
  });

  /* ── 8. O transpilador ───────────────────────────────────────────────── */
  const MAP = [[0, 1], [2], [3, 4], [5, 6], [7, 27], [8, 9, 10, 11, 12, 13], [14, 24, 25, 26], [15, 16, 17], [18, 19, 20, 21, 22, 23], [], [], [28, 29]];
  S.push({
    id: 'transpilador', act: 'Proposta', name: 'O transpilador',
    title: 'Um programa determinístico expande a DSL em XML e confere no esquema oficial.',
    html: `<div class="body tp">
      <div class="panel tp-dsl" style="left:0;top:0;width:556px;height:470px">
        <div class="panel-hd"><span>BPMN-DSL</span><span><b>286</b> caracteres</span></div>
        <div class="dsl"></div>
      </div>
      <svg class="fig tp-mid" viewBox="-70 -60 140 120" width="140" height="120" style="left:558px;top:170px">
        <path class="tp-ar" d="M-64,0 H-46 M46,0 H62 m-10,-8 l10,8 l-10,8"/><path class="gear" d="${K.gear(34, 25, 9)}"/><circle r="9" class="gear-h"/>
      </svg>
      <div class="panel tp-xml" style="left:700px;top:-16px;width:1000px;height:724px">
        <div class="panel-hd"><span>BPMN 2.0 XML</span><span class="stamp">${K.icon('check')} válido no XSD</span><span><b class="cnt">0</b> caracteres</span></div>
        <div class="xml"></div><div class="scan"></div>
      </div>
      <div class="corpus">
        <svg viewBox="0 0 560 142" width="560" height="142">
          <defs>
            <pattern id="pd0" width="8.75" height="8.75" patternUnits="userSpaceOnUse"><circle cx="4.375" cy="4.375" r="2.6" class="cd0"/></pattern>
            <pattern id="pd1" width="8.75" height="8.75" patternUnits="userSpaceOnUse"><circle cx="4.375" cy="4.375" r="3" class="cd1"/></pattern>
            <clipPath id="pc"><rect class="sweep" x="0" y="0" width="0" height="142"/></clipPath>
          </defs>
          <rect width="560" height="131.250" fill="url(#pd0)"/><rect y="131.250" width="533.750" height="8.750" fill="url(#pd0)"/>
          <g clip-path="url(#pc)"><rect width="560" height="131.250" fill="url(#pd1)"/><rect y="131.250" width="533.750" height="8.750" fill="url(#pd1)"/></g>
        </svg>
        <p><b class="cn">0</b> de 1.021 amostras do corpus viram XML válido.</p>
      </div>
    </div>`,
    setup(c) {
      const dsl = K.code(c.$('.dsl'), D.exemplo.dsl, 'dsl');
      const src = D.exemplo.xml.split('\n'), len = src.map((l) => l.length + 1);
      src[0] = '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" …>';
      const xml = K.code(c.$('.xml'), src.join('\n'), 'xml');
      const cnt = c.$('.cnt'), gear = c.$('.tp-mid .gear'), scan = c.$('.scan'), stamp = c.$('.stamp');
      const corpus = c.$('.corpus'), sweep = c.$('.sweep'), cn = c.$('.cn');
      return [
        {
          dur: 8400,
          draw(p) {
            const u = K.seg(p, 0.03, 0.96) * MAP.length, i = p >= 1 ? MAP.length : Math.floor(u);
            dsl.mark(p > 0 && p < 1 ? Math.min(i, MAP.length - 1) : -1);
            let chars = 0;
            MAP.forEach((ls, j) => ls.forEach((x) => {
              const on = p > 0 && j <= i;
              xml.lines[x].classList.toggle('hid', !on);
              xml.lines[x].classList.toggle('hot', on && j === i && p < 1);
              if (on) chars += len[x];
            }));
            K.text(cnt, K.int(chars));
            gear.style.transform = `rotate(${p * 540}deg)`;
          },
        },
        {
          dur: 1900,
          draw(p) {
            scan.style.opacity = p > 0 && p < 0.8 ? 1 : 0;
            scan.style.top = K.lerp(44, 722, K.ease.io(K.seg(p, 0, 0.78))) + 'px';
            stamp.style.opacity = K.seg(p, 0.78, 0.9);
            stamp.style.transform = `scale(${K.lerp(1.5, 1, K.ease.out(K.seg(p, 0.78, 1)))})`;
          },
        },
        {
          dur: 2600,
          draw(p) {
            const e = K.ease.io(K.seg(p, 0.15, 0.95));
            show(corpus, K.seg(p, 0, 0.15));
            sweep.setAttribute('width', 560 * e);
            K.text(cn, K.int(1021 * e));
          },
        },
      ];
    },
  });

  /* ── 9. Compressão ───────────────────────────────────────────────────── */
  S.push({
    id: 'compressao', act: 'Proposta', name: 'Compressão medida',
    title: 'A DSL deixa de emitir 81% dos tokens do XML equivalente.',
    note: 'Razão de compressão (TCR) = tokens do XML / tokens da DSL, com o tokenizador do Qwen2.5-Coder. Corpus: IC 95% [5,33; 5,41].',
    html: `<div class="body cmp">
      <svg class="fig" viewBox="0 0 540 540" width="540" height="540" style="top:14px"></svg>
      <p class="waf-cap">de cada 100 tokens de XML, a DSL emite cerca de 19</p>
      <div class="hero"><div class="num"><span class="tcr">5,37</span><i>×</i></div>
        <p>menos tokens que o XML, em média, nas 1.021 amostras do corpus</p></div>
      <div class="cbars">
        <p>Mesmo modelo, mesmos 46 processos: tokens de saída por geração</p>
        <div class="cb"><span>XML</span><i class="c-xml"></i><b>935</b></div>
        <div class="cb"><span>DSL</span><i class="c-dsl"></i><b>171</b></div>
      </div>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), N = 19, sq = [];
      for (let i = 0; i < 100; i++) {
        const x = (i % 10) * 54, y = Math.floor(i / 10) * 54;
        K.s('rect', { x: x + 1, y: y + 1, width: 44, height: 44, rx: 6, class: 'w0' }, svg);
        sq.push([K.s('rect', { x, y, width: 46, height: 46, rx: 7, class: 'w1' }, svg), K.s('rect', { x, y, width: 46, height: 46, rx: 7, class: 'w2' }, svg)]);
      }
      const tcr = c.$('.tcr'), cap2 = c.$('.waf-cap'), hero = c.$('.hero'), cb = c.$('.cbars'), fills = c.$$('.cb i'), vals = c.$$('.cb b');
      return [
        {
          dur: 4200,
          draw(p) {
            sq.forEach(([a, d], i) => {
              const inn = K.seg(p, 0.02 + i * 0.002, 0.1 + i * 0.002);
              // os 81 que somem saem do fim para o começo
              const out = i >= N ? K.seg(p, 0.3 + (99 - i) * 0.0052, 0.36 + (99 - i) * 0.0052) : 0;
              const blue = i < N ? K.seg(p, 0.8, 0.92) : 0;
              a.style.opacity = inn * (1 - out) * (1 - blue);
              d.style.opacity = blue;
              const s = 1 - 0.5 * out;
              a.style.transform = `scale(${s})`;
            });
            show(hero, K.seg(p, 0.2, 0.34));
            K.text(tcr, K.fmt(K.lerp(1, 5.37, K.ease.io(K.seg(p, 0.3, 0.8))), 2));
            cap2.style.opacity = K.seg(p, 0.86, 1);
          },
        },
        {
          dur: 1900,
          draw(p) {
            show(cb, K.seg(p, 0, 0.25));
            const e = K.ease.out(K.seg(p, 0.2, 1));
            fills[0].style.width = 860 * e + 'px';
            fills[1].style.width = (860 * 171 / 935) * e + 'px';
            K.text(vals[0], K.int(935 * e));
            K.text(vals[1], K.int(171 * e));
          },
        },
      ];
    },
  });

  /* ── 10. Corpus e destilação ─────────────────────────────────────────── */
  const LOSS = [1.1498, 0.7415, 0.5599, 0.5188, 0.5187, 0.5057, 0.4673, 0.473, 0.4392, 0.4005, 0.4, 0.3898, 0.4105, 0.3922, 0.3903, 0.4021, 0.3783, 0.3539, 0.3261, 0.3034, 0.335, 0.328, 0.3162, 0.3128, 0.3347];
  S.push({
    id: 'destilacao', act: 'Proposta', name: 'Corpus e ajuste do modelo pequeno',
    title: 'Um modelo grande gera os pares.<br>O modelo pequeno aprende com eles.',
    note: 'Pares mantidos só quando o XML reconstrói o processo extraído. Divisão por documento de origem: 690 de treino, 78 de validação.',
    html: `<div class="body dst">
      <svg class="fig" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="stats">
        <div><b><span class="n-pairs">768</span></b><span>pares de texto e DSL</span></div>
        <div><b>61 min</b><span>de treino, em uma GPU A40 alugada</span></div>
        <div><b>US$ 0,47</b><span>custo total do ajuste</span></div>
      </div>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), Y = 190, b = K.bpmn(svg), G = () => K.s('g', { class: 'pg' }, svg);
      const F = [[214, 330], [574, 716], [812, 928], [1150, 1292]].map(([x1, x2], i) => b.flow('f' + i, [[x1, Y], [x2, Y]]));
      // textos
      const gT = G();
      [[36, -8], [18, 4], [0, 16]].forEach(([dx, dy]) => K.s('rect', { x: 30 + dx, y: Y - 108 + dy, width: 150, height: 196, rx: 5, class: 'card' }, gT));
      [112, 100, 108, 86, 112, 96, 70].forEach((w, i) => K.s('rect', { x: 48, y: Y - 64 + i * 22, width: w, height: 5, rx: 2.5, class: 'tline' }, gT));
      cap(gT, 115, Y + 158, '772 descrições', '728 da GitLab, 44 do PET');
      // professor
      const gA = G();
      K.s('circle', { cx: 452, cy: Y, r: 118, class: 'prob' }, gA);
      K.s('text', { x: 452, y: Y, class: 'big-l', text: 'GLM 5.2' }, gA);
      cap(gA, 452, Y + 158, 'modelo de grande porte', 'extrai o processo em JSON');
      // conversão determinística
      const gC = G();
      K.s('rect', { x: 720, y: Y - 44, width: 88, height: 88, rx: 14, class: 'card solid' }, gC);
      const gear = K.s('path', { d: K.gear(30, 22, 9), class: 'gear', transform: `translate(764,${Y})` }, gC);
      K.s('circle', { cx: 764, cy: Y, r: 8, class: 'gear-h' }, gC);
      cap(gC, 764, Y + 158, 'código confere', 'JSON → DSL → XML');
      // pares
      const gP = G();
      [[16, -12], [8, -6], [0, 0]].forEach(([dx, dy]) => {
        K.s('rect', { x: 934 + dx, y: Y - 58 + dy, width: 196, height: 116, rx: 8, class: 'card' }, gP);
      });
      [70, 62, 68, 50, 66].forEach((w, i) => K.s('rect', { x: 950, y: Y - 36 + i * 18, width: w, height: 5, rx: 2.5, class: 'tline' }, gP));
      K.s('path', { d: `M1032,${Y - 44} V${Y + 44}`, class: 'split' }, gP);
      bars(gP, D.exemplo.dsl.split('\n').slice(1, 9).join('\n'), 1040, Y - 38, 1.9, 10.5, 'b-dsl');
      cap(gP, 1032, Y + 158, 'pares de treino', 'texto original e DSL');
      // aluno
      const gS = G();
      K.s('circle', { cx: 1366, cy: Y, r: 72, class: 'stu-bg' }, gS);
      const ring = K.s('circle', { cx: 1366, cy: Y, r: 72, class: 'stu-ring', transform: `rotate(-90 1366 ${Y})` }, gS);
      K.s('text', { x: 1366, y: Y, class: 'big-l', text: '7B' }, gS);
      cap(gS, 1366, Y + 158, 'Qwen2.5-Coder 7B', 'ajuste com QLoRA, 4 bits');
      const circ = 2 * Math.PI * 72;
      ring.style.strokeDasharray = circ;
      // perda de treino (dados reais do ajuste)
      const gLo = G(), lx = (i) => 1478 + (i / (LOSS.length - 1)) * 190, ly = (v) => Y + 44 - ((v - 0.3) / 0.85) * 96;
      const loss = K.stroke(K.s('path', { d: LOSS.map((v, i) => (i ? 'L' : 'M') + lx(i).toFixed(1) + ',' + ly(v).toFixed(1)).join(' '), class: 'loss' }, gLo));
      K.s('path', { d: `M1478,${Y + 50} H1668`, class: 'ax' }, gLo);
      K.s('text', { x: 1573, y: Y + 80, class: 'cap-s', text: 'perda de treino, 3 épocas' }, gLo);
      // partículas
      const mk = (cls, n) => Array.from({ length: n }, () => K.s('rect', { width: 16, height: 11, rx: 2.5, class: 'part ' + cls }, svg));
      const P0 = mk('p-doc', 7), P1 = mk('p-doc', 7), P2 = mk('p-pair', 7), P3 = mk('p-pair', 7);
      const fly = (ps, f, p, a, z) => ps.forEach((el, i) => {
        const u = K.seg(p, a + (i / ps.length) * (z - a) * 0.7, a + (i / ps.length) * (z - a) * 0.7 + (z - a) * 0.3), pt = f.at(u);
        el.setAttribute('x', pt.x - 8);
        el.setAttribute('y', pt.y - 5.5);
        el.style.opacity = u > 0 && u < 1 ? 1 : 0;
      });
      const stats = c.$$('.stats > div'), nPairs = c.$('.n-pairs');
      c.gear = gear; c.Y = Y;
      return [{
        dur: 7800,
        draw(p) {
          show(gT, K.seg(p, 0, 0.08));
          F[0].show(K.seg(p, 0.06, 0.12));
          show(gA, K.seg(p, 0.08, 0.17));
          fly(P0, F[0], p, 0.12, 0.34);
          F[1].show(K.seg(p, 0.26, 0.32));
          show(gC, K.seg(p, 0.28, 0.36));
          fly(P1, F[1], p, 0.3, 0.52);
          F[2].show(K.seg(p, 0.36, 0.42));
          show(gP, K.seg(p, 0.4, 0.48));
          fly(P2, F[2], p, 0.38, 0.6);
          K.text(nPairs, K.int(768 * K.ease.out(K.seg(p, 0.42, 0.64))));
          show(stats[0], K.seg(p, 0.42, 0.5));
          F[3].show(K.seg(p, 0.58, 0.64));
          show(gS, K.seg(p, 0.6, 0.68));
          fly(P3, F[3], p, 0.62, 0.86);
          const tr = K.seg(p, 0.66, 0.9);
          ring.style.strokeDashoffset = circ * (1 - tr);
          show(gLo, K.seg(p, 0.64, 0.7), 0);
          loss.set(tr);
          show(stats[1], K.seg(p, 0.86, 0.93));
          show(stats[2], K.seg(p, 0.91, 0.98));
        },
      }];
    },
    loop: (t, c) => c.gear.setAttribute('transform', `translate(764,${c.Y}) rotate(${(t * 36) % 360})`),
  });
})();
