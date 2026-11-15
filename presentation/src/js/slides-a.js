/* slides-a.js — capa e problema (slides 1 a 5). */
(function () {
  'use strict';
  const K = window.K, S = window.SLIDES, D = window.DADOS;

  K.steps = (durs, render) => {
    const P = durs.map(() => 0);
    return durs.map((dur, j) => ({ dur, draw(p) { P[j] = p; render(P); } }));
  };

  /* ── 1. Capa ─────────────────────────────────────────────────────────── */
  const PAIRS = [
    { pre: '<serviceTask id="ServiceTask_2" name=', kw: 'service ', mid: '"Validate"', post: '/>' },
    { pre: '<sequenceFlow id="SequenceFlow_2" sourceRef="ServiceTask_1" targetRef="ServiceTask_2"/>', kw: '->', mid: '', post: '' },
    { pre: '<exclusiveGateway id="ExclusiveGateway_1" name=', kw: 'xor ', mid: '"Valid?"', post: '/>' },
    { pre: '<endEvent id="EndEvent_2" name=', kw: 'end:error ', mid: '"Invalid"', post: '><errorEventDefinition/></endEvent>' },
  ];
  K.morph = (c, t, still) => {
    const T = 6.8, i = Math.floor(t / T) % PAIRS.length, u = still ? 4.6 : t % T, P = PAIRS[i];
    if (c.cur !== i) {
      c.cur = i;
      ['pre', 'kw', 'mid', 'post'].forEach((k, j) => (c.segs[j].textContent = P[k]));
    }
    const e = K.ease.io(K.seg(u, 2.5, 3.5));
    const nx = P.pre.length + P.mid.length + P.post.length, nd = P.kw.length + P.mid.length;
    c.segs[0].style.width = P.pre.length * (1 - e) + 'ch';
    c.segs[3].style.width = P.post.length * (1 - e) + 'ch';
    c.segs[1].style.width = P.kw.length * e + 'ch';
    c.segs[0].style.opacity = c.segs[3].style.opacity = 1 - e;
    c.segs[1].style.opacity = e;
    c.box.style.opacity = Math.min(K.seg(u, 0, 0.5), 1 - K.seg(u, 6.2, 6.8));
    K.text(c.tag, e < 0.5 ? 'XML' : 'DSL');
    c.tagBox.classList.toggle('c-dsl', e >= 0.5);
    c.tagBox.classList.toggle('c-xml', e < 0.5);
    K.text(c.cnt, Math.round(K.lerp(nx, nd, e)) + ' caracteres');
    if (c.mini) c.mini.set(still ? 1 : K.seg(u, 2.5, 3.5) - K.seg(u, 6.0, 6.8));
  };
  K.morphSetup = (c) => {
    c.box = c.$('.morph');
    c.box.innerHTML = '<span class="tag c-xml"><span class="sw"></span><b></b></span><span class="morph-line"></span><span class="morph-n"></span>';
    c.tagBox = c.box.firstChild;
    c.tag = c.box.querySelector('b');
    c.cnt = c.box.querySelector('.morph-n');
    const line = c.box.querySelector('.morph-line');
    c.segs = ['pre', 'kw', 'mid', 'post'].map((n) => line.appendChild(K.h(`<span class="m-${n}"></span>`)));
    c.cur = -1;
    const mm = c.$('.mm');
    if (mm) c.mini = K.minimap(mm, { cw: 3.5, h: 6.5, pitch: 14 });
  };

  S.push({
    id: 'capa', act: '', name: 'Capa', bare: true,
    html: `
    <div class="cover">
      <p class="cover-k rv" data-at="0">Trabalho de Conclusão de Curso em Engenharia da Computação, Universidade de Fortaleza, 2026</p>
      <h1 class="cover-title rv" data-at="0" style="--d:.1s">Compressão Semântica na Geração de Modelos BPMN&nbsp;2.0 por Modelos de Linguagem</h1>
      <p class="cover-sub rv" data-at="0" style="--d:.22s">DSL e transpilação determinística</p>
    </div>
    <svg class="fig mm rv fade" data-at="0" style="--d:.7s" viewBox="0 0 360 420" width="360" height="420"></svg>
    <div class="morph"></div>
    <div class="cover-by rv" data-at="0" style="--d:.5s"><b>Rafael Marins Florenzano</b><span>Orientador: Prof. Caio Marques</span></div>`,
    setup: K.morphSetup,
    loop: (t, c, s) => K.morph(c, t, s.still),
  });

  /* ── 2. Do texto ao BPMN ─────────────────────────────────────────────── */
  S.push({
    id: 'texto', act: 'Problema', name: 'Do texto ao modelo BPMN',
    title: 'O processo está descrito em texto.<br>O modelo BPMN ainda é feito à mão.',
    html: `<div class="body">
      <div class="doc rv fade" data-at="0">
        <div class="doc-k">descrição em linguagem natural</div>
        <p>When <span class="ph">an order arrives</span>, the system <span class="ph">fetches its data</span> and <span class="ph">validates it</span>. <span class="ph">If the order is valid</span>, <span class="ph">it is processed</span>. Otherwise, the system may <span class="ph">retry</span>, <span class="ph">fetching the data again</span>, or <span class="ph">stop with an error</span>.</p>
      </div>
      <svg class="fig" viewBox="0 0 1700 714" width="1700" height="714"><g class="dia" transform="translate(724,96)"></g><g class="arcs"></g></svg>
      <div class="dia-k rv fade" data-at="0" style="--d:.4s">modelo BPMN 2.0</div>
    </div>`,
    setup(c) {
      const b = K.orderDiagram(c.$('.dia'));
      const ph = c.$$('.ph'), body = c.$('.body'), gA = c.$('.arcs');
      // cada frase faz aparecer estes elementos; o primeiro nó é o alvo do arco
      const map = [['start'], ['f1', 'fetch'], ['f2', 'validate'], ['f3', 'valid'], ['yes', 'process', 'f5', 'end'], ['no', 'retry'], ['loop'], ['err', 'invalid']];
      const aim = ['start', 'fetch', 'validate', 'valid', 'process', 'retry', null, 'invalid'];
      let arcs = null;
      const measure = () => {
        if (arcs) return;
        arcs = ph.map((el, i) => {
          const r = K.rectIn(el, body), n = aim[i] && b.n[aim[i]];
          const t = n ? { x: n.cx, y: n.cy } : b.f.loop.at(0.45);
          const sx = r.x + r.w / 2, sy = r.y + r.h * 0.92, tx = t.x + 724, ty = t.y + 96;
          const path = K.s('path', { d: `M${sx},${sy} C${sx + 60},${sy + 150} ${tx - 220},${ty + 110} ${tx},${ty}`, class: 'arc' }, gA);
          return K.stroke(path);
        });
      };
      return [{
        dur: 7800,
        draw(p) {
          measure();
          map.forEach((ids, i) => {
            const a = 0.05 + i * 0.1;
            ph[i].classList.toggle('lit', p > a);
            arcs[i].set(K.ease.out(K.seg(p, a + 0.012, a + 0.08)));
            arcs[i].path.style.opacity = p > a ? 0.95 * (1 - K.seg(p, a + 0.1, a + 0.19)) : 0;
            ids.forEach((id, j) => (b.n[id] || b.f[id]).show(K.seg(p, a + 0.055 + j * 0.02, a + 0.12 + j * 0.02)));
          });
        },
      }];
    },
  });

  /* ── 3. XML verboso ──────────────────────────────────────────────────── */
  S.push({
    id: 'xml', act: 'Problema', name: 'O XML é extenso',
    title: 'Para 8 elementos e 8 fluxos, o modelo precisa escrever 1.833 caracteres de XML.',
    html: `<div class="body">
      <svg class="fig" viewBox="0 0 700 420" width="700" height="420" style="top:64px"><g class="dia" transform="scale(.71)"></g></svg>
      <p class="x-cap rv" data-at="1">Em destaque, o que descreve o processo: <b>tipos, rótulos e condições</b>. O resto é marcação que um programa consegue derivar.</p>
      <div class="panel xmlp" style="left:752px;top:-16px;width:948px;height:728px">
        <div class="panel-hd"><span>saída em BPMN 2.0 XML</span><span><b class="cnt">0</b> caracteres</span></div>
        <div class="xml"></div>
      </div>
    </div>`,
    setup(c) {
      K.orderDiagram(c.$('.dia'));
      const src = D.exemplo.xml.split('\n'), len = src.map((l) => l.length + 1);
      src[0] = '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" …>';
      const code = K.code(c.$('.xml'), src.join('\n'), 'xml'), cnt = c.$('.cnt'), panel = c.$('.xmlp');
      return [
        {
          dur: 3800,
          draw(p) {
            const n = Math.round(K.ease.io(K.seg(p, 0.05, 0.97)) * src.length);
            code.showLines(n);
            K.text(cnt, K.int(len.slice(0, n).reduce((a, x) => a + x, 0)));
          },
        },
        { dur: 500, draw(p) { panel.classList.toggle('focus', p > 0); } },
      ];
    },
  });

  /* ── 4. Tokens e orçamento ───────────────────────────────────────────── */
  S.push({
    id: 'orcamento', act: 'Problema', name: 'Tokens pesam no orçamento',
    title: 'O gasto com tokens já pesa nas decisões das empresas.',
    note: 'Fontes: Ropek (TechCrunch, 2026) e Cooter (CIO, 2026), citados na Introdução.',
    html: `<div class="body bud">
      <article class="bcard rv" data-at="0">
        <div class="bk">Uber<span>2026</span></div>
        <div class="months"></div>
        <div class="mo-cap"><span>orçamento de 12 meses, gasto em 4</span><span class="gone-l">8 meses sem orçamento</span></div>
        <p class="bt">Orçamento anual de ferramentas de IA para programação: <b>esgotado em 4 meses</b>.</p>
        <p class="bs">Depois disso, teto de US$&nbsp;1.500 por mês, por funcionário e por ferramenta.</p>
      </article>
      <article class="bcard rv" data-at="0" style="--d:.12s">
        <div class="bk">Microsoft<span>2026</span></div>
        <div class="swap">
          <div class="sbox out"><span>assistentes de terceiros</span></div>
          <svg viewBox="0 0 120 40" width="120" height="40"><path class="sarrow" d="M6 20h104M96 8l14 12-14 12"/></svg>
          <div class="sbox in"><span>modelos próprios</span></div>
        </div>
        <p class="bt">Cancelou a maior parte das licenças de assistentes externos da engenharia. <b>Motivo declarado: custo</b>.</p>
        <p class="bs">Parte das requisições dos produtos passou para modelos da própria empresa.</p>
      </article>
    </div>`,
    setup(c) {
      const m = c.$('.months');
      const mo = Array.from({ length: 12 }, (_, i) => m.appendChild(K.h(`<div class="mo"><b></b><span>${i + 1}</span></div>`)));
      const out = c.$('.out'), inn = c.$('.in'), arrow = K.stroke(c.$('.sarrow')), gl = c.$('.gone-l');
      return [{
        dur: 4400,
        draw(p) {
          mo.forEach((e, i) => {
            if (i < 4) e.firstChild.style.transform = `scaleY(${K.ease.out(K.seg(p, 0.14 + i * 0.12, 0.3 + i * 0.12))})`;
            else e.classList.toggle('gone', p > 0.7 + (i - 4) * 0.018);
          });
          gl.style.opacity = K.seg(p, 0.78, 0.9);
          out.classList.toggle('cut', p > 0.42);
          arrow.set(K.ease.io(K.seg(p, 0.5, 0.72)));
          inn.classList.toggle('lit', p > 0.72);
        },
      }];
    },
  });

  /* ── 5. Duas alavancas ───────────────────────────────────────────────── */
  S.push({
    id: 'alavancas', act: 'Problema', name: 'Duas alavancas de custo',
    title: 'O custo é o produto de dois fatores. Dá para agir nos dois.',
    note: 'Esquema conceitual. Os valores medidos aparecem nos resultados.',
    html: `<div class="body lev">
      <div class="formula rv" data-at="0">custo <i>=</i> <span class="f1">tokens</span> <i>×</i> <span class="f2">preço</span></div>
      <div class="lrow l1"><span class="sw c-dsl"></span><div><b>Menos tokens</b><span>uma representação mais curta que o XML</span></div></div>
      <div class="lrow l2"><span class="sw c-slm"></span><div><b>Token mais barato</b><span>um modelo pequeno no lugar de um de grande porte</span></div></div>
      <p class="lfact rv fade" data-at="0" style="--d:.9s">Nos provedores, o token gerado custa cerca de 3× o token lido.</p>
      <svg class="fig" viewBox="0 0 1700 714" width="1700" height="714"></svg>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), X = 800, Y = 610, W = 800, H = 440, kx = 0.3, ky = 0.3;
      const axis = K.s('path', { d: `M${X},${Y - H - 40} L${X},${Y} L${X + W + 50},${Y}`, class: 'ax' }, svg);
      const ghost = K.s('rect', { x: X, y: Y - H, width: W, height: H, class: 'ghost' }, svg);
      const rs = ['xml', 'dsl', 'slm'].map((n) => K.s('rect', { x: X, class: 'area a-' + n, rx: 4 }, svg));
      const lab = K.s('text', { class: 'area-l', text: 'custo' }, svg);
      const gl = K.s('text', { x: X + W - 18, y: Y - H + 36, class: 'ghost-l', 'text-anchor': 'end', text: 'XML, modelo de grande porte' }, svg);
      const sl = K.s('text', { x: X + W * kx + 58, y: Y - (H * ky) / 2, class: 'ghost-l', 'dominant-baseline': 'central', text: 'DSL, modelo pequeno' }, svg);
      K.s('text', { x: X + W / 2, y: Y + 44, class: 'ax-l', text: 'tokens gerados' }, svg);
      K.s('text', { x: X - 26, y: Y - H / 2, class: 'ax-l', transform: `rotate(-90 ${X - 26} ${Y - H / 2})`, text: 'preço por token' }, svg);
      const a1 = K.s('path', { d: `M${X + W - 8},${Y - H - 22} L${X + W * kx + 8},${Y - H - 22} m14,-10 l-14,10 l14,10`, class: 'lev-a c-dsl' }, svg);
      const a2 = K.s('path', { d: `M${X + W * kx + 26},${Y - H + 8} L${X + W * kx + 26},${Y - H * ky - 8} m-10,-14 l10,14 l10,-14`, class: 'lev-a c-slm' }, svg);
      const s1 = K.stroke(a1), s2 = K.stroke(a2), l1 = c.$('.l1'), l2 = c.$('.l2'), f1 = c.$('.f1'), f2 = c.$('.f2');
      return K.steps([1700, 1500, 1500], ([a, b, d]) => {
        const g = K.ease.out(K.seg(a, 0.25, 1)), e1 = K.ease.io(b), e2 = K.ease.io(d);
        const w = W * g * K.lerp(1, kx, e1), h = H * g * K.lerp(1, ky, e2);
        axis.style.opacity = K.seg(a, 0.1, 0.4);
        rs.forEach((r) => { r.setAttribute('y', Y - h); r.setAttribute('width', Math.max(0, w)); r.setAttribute('height', Math.max(0, h)); });
        rs[0].style.opacity = g * (1 - e1);
        rs[1].style.opacity = e1 * (1 - e2);
        rs[2].style.opacity = e2;
        ghost.style.opacity = gl.style.opacity = Math.max(K.seg(b, 0, 0.2), d > 0 ? 1 : 0);
        sl.style.opacity = K.seg(d, 0.7, 1);
        lab.setAttribute('x', X + w / 2);
        lab.setAttribute('y', Y - h / 2);
        lab.style.opacity = K.seg(a, 0.6, 1);
        lab.style.fontSize = K.lerp(44, 26, Math.max(e1, e2)) + 'px';
        s1.set(K.seg(b, 0.1, 0.8));
        s2.set(K.seg(d, 0.1, 0.8));
        l1.classList.toggle('on', b > 0); f1.classList.toggle('on', b > 0);
        l2.classList.toggle('on', d > 0); f2.classList.toggle('on', d > 0);
      });
    },
  });
})();
