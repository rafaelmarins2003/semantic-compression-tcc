/* slides-d.js — custo e fidelidade (slides 17 a 21). */
(function () {
  'use strict';
  const K = window.K, S = window.SLIDES;
  const show = (el, p, dy = 6) => {
    el.style.opacity = K.clamp(p);
    el.style.transform = `translateY(${(1 - K.ease.out(K.clamp(p))) * dy}px)`;
  };

  /* ── 17. Anatomia do custo ───────────────────────────────────────────── */
  // Tokens médios, preços e validade das Tabelas 4.3, 5.1 e 5.4 da monografia.
  const COST = [
    { id: 'A1', cls: 'xml', x: 0, tin: 1316, tout: 935, pin: 1.32, pout: 3.96, v: 135 / 138, cost: 5561, name: 'XML direto, modelo grande' },
    { id: 'A2r', cls: 'dsl', x: 709, tin: 1621, tout: 171, pin: 1.32, pout: 3.96, v: 120 / 138, cost: 3241, name: 'DSL, modelo grande' },
    { id: 'A4', cls: 'slm', x: 1356, tin: 922, tout: 220, pin: 0.45, pout: 0.45, v: 120 / 138, cost: 591, name: 'DSL, modelo pequeno ajustado' },
  ];
  S.push({
    id: 'custo', act: 'Resultados', name: 'Custo por saída válida',
    title: 'O menor custo por saída válida é o do modelo pequeno ajustado.',
    note: 'Preços públicos de um mesmo provedor, sem cache. No modelo pequeno, o acréscimo de 50% pelo adaptador é uma estimativa. Com cache: 7,1× e 2,1×.',
    html: `<div class="body cst">
      <svg class="fig" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <p class="cst-key">largura: tokens por saída válida<br>altura: preço por token<br>área: custo</p>
      ${COST.map((a, i) => `<div class="cst-b b${i}" style="${i < 2 ? `left:${a.x}px` : 'right:0;text-align:right'}"><p><span class="tag">${a.id}</span>${a.name}</p><b>US$ <span>0</span></b><em>por milhão de saídas válidas</em></div>`).join('')}
      <div class="cst-x"><b>9,4×</b> menos que o XML direto<br><b>5,5×</b> menos que a DSL no modelo grande</div>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), B = 440, kx = 0.262, ky = 92;
      const hair = [[3.96, 'US$ 3,96 por milhão de tokens de saída'], [1.32, 'US$ 1,32 por milhão de tokens de entrada']].map(([p, t]) => {
        const g = K.s('g', {}, svg), y = B - p * ky;
        K.s('path', { d: `M0,${y} H1700`, class: 'hair' }, g);
        K.s('text', { x: 1700, y: y - 12, class: 'hair-t', text: t }, g);
        return g;
      });
      K.s('path', { d: `M0,${B} H1700`, class: 'base' }, svg);
      const ann = ['a saída responde por 68% do custo', 'a saída encolhe; a gramática aumenta a entrada', 'token a US$ 0,45, prompt sem a gramática'];
      const arms = COST.map((a, i) => {
        const g = K.s('g', { class: 'c-' + a.cls }, svg);
        const wi = (a.tin / a.v) * kx, wo = (a.tout / a.v) * kx, hi = a.pin * ky, ho = a.pout * ky;
        const rin = K.s('rect', { x: a.x, y: B - hi, height: hi, class: 'fp fp-in' }, g);
        const rout = K.s('rect', { x: a.x + wi + 2, width: wo, class: 'fp fp-out' }, g);
        const lin = K.s('text', { x: a.x + 12, y: B - hi + 27, class: 'fp-t', text: 'entrada' }, g);
        const lout = wo > 60 ? K.s('text', { x: a.x + wi + 14, y: B - ho + 27, class: 'fp-t', text: 'saída' }, g) : K.s('text', { x: a.x + wi + 2 + wo / 2, y: B - ho - 12, class: 'fp-o', text: 'saída' }, g);
        const note = K.s('text', { x: i < 2 ? a.x : 1700, y: B - hi - 16, class: 'fp-a', 'text-anchor': i < 2 ? 'start' : 'end', text: ann[i] }, svg);
        const blk = c.$('.b' + i), num = blk.querySelector('b span');
        return {
          draw(p) {
            const e1 = K.ease.out(K.seg(p, 0.08, 0.45)), e2 = K.ease.out(K.seg(p, 0.4, 0.8));
            rin.setAttribute('width', wi * e1);
            rout.setAttribute('y', B - ho * e2);
            rout.setAttribute('height', ho * e2);
            lin.style.opacity = K.seg(p, 0.4, 0.5);
            lout.style.opacity = K.seg(p, 0.78, 0.86);
            note.style.opacity = K.seg(p, 0.82, 0.96);
            show(blk, K.seg(p, 0.05, 0.2));
            K.text(num, K.int(a.cost * K.ease.out(K.seg(p, 0.25, 0.9))));
          },
        };
      });
      const key = c.$('.cst-key'), mult = c.$('.cst-x');
      return K.steps([3000, 2600, 2800], ([a, b, d]) => {
        hair.forEach((g) => (g.style.opacity = K.seg(a, 0, 0.15)));
        key.style.opacity = K.seg(a, 0.84, 1);
        arms[0].draw(a);
        arms[1].draw(b);
        arms[2].draw(d);
        show(mult, K.seg(d, 0.86, 1));
      });
    },
  });

  /* ── 18. Custo × validade ────────────────────────────────────────────── */
  // [braço, custo por requisição (US$ por milhão), validade %, grupo, rótulo, lado do rótulo]
  const MAP = [
    ['A1', 5441, 97.8, 'xml', 'A1  XML direto', -1],
    ['A1g', 5969, 93.5, 'xml', 'A1g', 1],
    ['A2', 2686, 62.3, 'dsl', 'A2', -1],
    ['A2g', 2912, 52.9, 'dsl', 'A2g', 1],
    ['A2r', 2818, 87.0, 'dsl', 'A2r  DSL com referência por rótulo', 1],
    ['A3', 513, 58.7, 'slm open', 'A3  sem ajuste, com a gramática', 1],
    ['A3m', 802, 0, 'slm open', 'A3m  sem ajuste, prompt mínimo', 1],
    ['A4', 514, 87.0, 'slm', 'A4  modelo pequeno ajustado', -1],
  ];
  S.push({
    id: 'mapa', act: 'Resultados', name: 'Custo e validade de cada braço',
    title: 'O modelo pequeno ajustado alia validade alta e custo baixo.',
    note: 'Custo por requisição sem cache, com os tokens médios de cada braço. O braço A2r é exploratório.',
    html: `<div class="body"><svg class="fig sct" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="lgd"><span class="c-xml"><i class="sw"></i>escreve XML</span><span class="c-dsl"><i class="sw"></i>escreve DSL, modelo grande</span><span class="c-slm"><i class="sw"></i>escreve DSL, modelo pequeno</span><span class="c-slm"><i class="sw open"></i>sem ajuste</span></div>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), X0 = 150, X1 = 1620, Y0 = 560, Y1 = 60;
      const x = (v) => X0 + (v / 6500) * (X1 - X0), y = (v) => Y0 - (v / 100) * (Y0 - Y1);
      const gA = K.s('g', {}, svg);
      [0, 25, 50, 75, 100].forEach((v) => {
        K.s('path', { d: `M${X0},${y(v)} H${X1}`, class: v ? 'hair' : 'base' }, gA);
        K.s('text', { x: X0 - 16, y: y(v) + 7, class: 'tick r', text: v + '%' }, gA);
      });
      [0, 2000, 4000, 6000].forEach((v) => K.s('text', { x: x(v), y: Y0 + 36, class: 'tick', text: K.int(v) }, gA));
      K.s('text', { x: (X0 + X1) / 2, y: Y0 + 78, class: 'ax-l', text: 'custo por requisição, em US$ por milhão de requisições' }, gA);
      K.s('text', { x: X0 - 16, y: Y1 - 26, class: 'tick r', text: 'validade' }, gA);
      const link = K.s('path', { d: `M${x(514) + 20},${y(87)} H${x(2818) - 20}`, class: 'sct-link' }, svg);
      const linkT = K.s('text', { x: (x(514) + x(2818)) / 2, y: y(87) - 16, class: 'sct-lt', text: 'mesma validade, custo 5,5× menor' }, svg);
      const pts = MAP.map(([id, cost, val, grp, label, side]) => {
        const g = K.s('g', { class: 'pt c-' + grp, 'data-tip': `${id}: validade ${K.fmt(val)}%, US$ ${K.int(cost)} por milhão de requisições` }, svg);
        K.s('circle', { cx: x(cost), cy: y(val), r: 24, class: 'pt-hit' }, g);
        const dot = K.s('circle', { cx: x(cost), cy: y(val), r: 12, class: 'pt-dot' }, g);
        const t = K.s('text', { x: x(cost) + side * 24, y: y(val) + (id === 'A3m' ? -22 : 7), class: 'pt-l', 'text-anchor': id === 'A3m' ? 'start' : side < 0 ? 'end' : 'start', text: label }, g);
        return { id, g, dot, t, grp };
      });
      // A4 e A3 ficam quase na mesma abscissa: rótulos à direita dos dois
      const by = Object.fromEntries(pts.map((p) => [p.id, p]));
      by.A4.t.setAttribute('x', x(514) + 24); by.A4.t.setAttribute('text-anchor', 'start'); by.A4.t.setAttribute('y', y(87) + 44);
      by.A2.t.setAttribute('x', x(2686) - 24);
      const order = { A1: 0.14, A1g: 0.2, A2: 0.36, A2g: 0.42, A2r: 0.48, A3: 0.6, A3m: 0.66, A4: 0.8 };
      const lgd = c.$('.lgd');
      return K.steps([4200, 1200], ([a, b]) => {
        gA.style.opacity = K.seg(a, 0, 0.12);
        lgd.style.opacity = K.seg(a, 0.05, 0.2);
        pts.forEach((p) => {
          const t = K.seg(a, order[p.id], order[p.id] + 0.1);
          p.dot.setAttribute('r', 12 * K.ease.back(t));
          p.g.style.opacity = K.clamp(t * 3) * (b > 0 && !['A4', 'A2r'].includes(p.id) ? K.lerp(1, 0.35, b) : 1);
        });
        link.style.opacity = linkT.style.opacity = K.ease.out(b);
      });
    },
  });

  /* ── 19. Válido não quer dizer fiel ──────────────────────────────────── */
  S.push({
    id: 'fiel', act: 'Resultados', name: 'Válido não quer dizer fiel',
    title: 'Um XML aceito pelo esquema pode descrever o processo errado.',
    note: 'Saída do braço A1 (XML direto) para o item pmo_13 do conjunto de teste. Por isso a fidelidade ao texto é medida à parte.',
    html: `<div class="body fl">
      <blockquote>“If a refund is approved, the financial team processes the reimbursement.”<cite>trecho da descrição do processo</cite></blockquote>
      <div class="fl-b"><span>${K.icon('check', 'ok')} aceito pelo XSD</span><span>nota do juiz: 2 de 5</span></div>
      <svg class="fig" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="fl-w">${K.icon('cross', 'ko')}<span>O reembolso é processado mesmo quando a resposta é “no”.</span></div>
    </div>`,
    setup(c) {
      const svg = c.$('svg.fig'), Y = 420, b = K.bpmn(svg, { fs: 20 });
      const f = {
        a: b.flow('a', [[61, Y], [113, Y]]), b: b.flow('b', [[267, Y], [293, Y]]), c: b.flow('c', [[487, Y], [513, Y]]), d: b.flow('d', [[667, Y], [705, Y]]),
        yes: b.flow('yes', [[785, Y], [843, Y]], { label: 'yes', lx: 813, ly: Y - 16 }),
        no: b.flow('no', [[745, Y + 40], [745, Y + 92], [935, Y + 92], [935, Y + 44]], { label: 'no', lx: 842, ly: Y + 118 }),
        up: b.flow('up', [[1025, Y], [1062, Y], [1062, Y - 120], [1088, Y - 120]]),
        dn: b.flow('dn', [[1025, Y], [1062, Y], [1062, Y + 120], [1150, Y + 120]]),
        g: b.flow('g', [[1262, Y - 120], [1311, Y - 120]]),
        h: b.flow('h', [[1358, Y - 120], [1500, Y - 120], [1500, Y - 44]]),
        i: b.flow('i', [[1198, Y + 120], [1500, Y + 120], [1500, Y + 44]]),
        j: b.flow('j', [[1582, Y], [1635, Y]]),
      };
      b.event('s', 40, Y, 'start');
      b.task('t1', 190, Y, 'File\ncomplaint', { w: 150, h: 84 });
      b.task('t2', 390, Y, 'Log complaint\nand assign to\ndepartment', { w: 190, h: 96, fs: 19 });
      b.task('t3', 590, Y, 'Review\ndetails', { w: 150, h: 84 });
      b.gateway('gw', 745, Y, 'Refund justified?', { ly: -56 });
      b.task('t4', 935, Y, 'Notify customer\nof decision', { w: 180, h: 84 });
      b.task('t5', 1175, Y - 120, 'Process\nreimbursement', { w: 170, h: 84 });
      b.event('e1', 1335, Y - 120, 'end');
      b.event('e2', 1175, Y + 120, 'end');
      b.task('t6', 1500, Y, 'Provide\nfeedback', { w: 160, h: 84 });
      b.event('e3', 1660, Y, 'end');
      const build = ['s', 'a', 't1', 'b', 't2', 'c', 't3', 'd', 'gw', 'yes', 'no', 't4', 'up', 'dn', 't5', 'e2', 'g', 'e1', 'h', 'i', 't6', 'j', 'e3'];
      const t1 = b.token(), t2 = b.token(), warn = c.$('.fl-w'), quote = c.$('blockquote'), badges = c.$('.fl-b');
      // trecho comum, depois os dois caminhos que saem juntos de "Notify customer"
      const seq = (ids) => {
        const segs = ids.map((id) => (f[id] ? { f: f[id], len: f[id].len } : { n: b.n[id], len: 80 }));
        return { segs, total: segs.reduce((a, s) => a + s.len, 0) };
      };
      const A = seq(['s', 'a', 't1', 'b', 't2', 'c', 't3', 'd', 'gw', 'no', 't4']);
      const U = seq(['up', 't5', 'g', 'e1', 'h', 't6', 'j', 'e3']), Dn = seq(['dn', 'e2', 'i', 't6']);
      const walk = (q, tok, p) => {
        let L = K.clamp(p) * q.total;
        for (const s of q.segs) {
          if (L <= s.len) return s.f ? tok.to(s.f.at(L / s.len)) : (tok.hide(), s.n.hit(true));
          L -= s.len;
        }
      };
      return K.steps([3600, 7800], ([a, d]) => {
        build.forEach((id, i) => (b.n[id] || f[id]).show(K.seg(a, 0.06 + i * 0.034, 0.16 + i * 0.034)));
        quote.style.opacity = K.seg(a, 0, 0.1);
        badges.style.opacity = K.seg(a, 0.9, 1);
        t1.hide(); t2.hide();
        Object.values(b.n).forEach((n) => n.hit(false));
        f.no.g.classList.toggle('hot', d > 0.34);
        b.n.t5.g.classList.toggle('bad', d > 0.72);
        show(warn, K.seg(d, 0.72, 0.82));
        if (d <= 0 || d >= 1) return;
        if (d < 0.56) return walk(A, t1, d / 0.56);
        walk(U, t1, (d - 0.56) / 0.44);
        walk(Dn, t2, (d - 0.56) / 0.3);
      });
    },
  });

  /* ── 20. A medida de fidelidade foi testada ──────────────────────────── */
  const yes = K.icon('check', 'ok'), no = K.icon('cross', 'ko');
  const CRIT = [
    ['Concorda com as notas de um especialista?', 'correlação em 222 modelos avaliados', '≥ 0,50', '0,108', no, '0,04', no],
    ['Percebe um defeito inserido de propósito?', 'sensibilidade, em 343 casos construídos', '≥ 0,80', '0,702', no, '0,837', yes],
    ['Dá nota menor quando há mais defeitos?', 'gradação', '≤ −0,50', '−0,385', no, '−0,588', yes],
    ['Mantém a nota quando só as palavras mudam?', 'invariância à paráfrase dos rótulos', '≥ 0,80', '1,000', yes, '0,000', no],
  ];
  S.push({
    id: 'regua', act: 'Resultados', name: 'Validação da medida de fidelidade',
    title: 'Antes de ser usada, a medida de fidelidade passou por dois testes.',
    note: 'Limiares fixados antes dos testes. Juiz: modelo de linguagem de outra família, que lê o texto e o modelo gerado. DF-F1: comparação com o modelo de referência.',
    html: `<div class="body rg">
      <div class="rg-h"><span></span><span>limiar</span><span>juiz</span><span>DF-F1</span></div>
      ${CRIT.map((r) => `<div class="rg-r"><div><b>${r[0]}</b><span>${r[1]}</span></div><div class="rg-t">${r[2]}</div><div class="rg-v">${r[3]}${r[4]}</div><div class="rg-v">${r[5]}${r[6]}</div></div>`).join('')}
      <p class="rg-c rv" data-at="1">Nenhuma das duas medidas atingiu todos os limiares. Por isso a fidelidade é reportada como exploratória, e as conclusões principais se apoiam na validade e no custo.</p>
    </div>`,
    setup(c) {
      const rows = c.$$('.rg-r'), head = c.$('.rg-h');
      return [{
        dur: 4200,
        draw(p) {
          head.style.opacity = K.seg(p, 0, 0.1);
          rows.forEach((r, i) => {
            const a = 0.1 + i * 0.2;
            show(r, K.seg(p, a, a + 0.1));
            r.querySelectorAll('.ic').forEach((ic, j) => {
              const t = K.seg(p, a + 0.1 + j * 0.04, a + 0.17 + j * 0.04);
              ic.style.opacity = t;
              ic.style.transform = `scale(${K.lerp(1.8, 1, K.ease.out(t))})`;
            });
          });
        },
      }];
    },
  });

  /* ── 21. Fidelidade (exploratória) ───────────────────────────────────── */
  const FID = [
    ['A1', 'xml', 'XML direto', 3.77, 3.47, 4.06],
    ['A2r', 'dsl', 'DSL com referência por rótulo', 3.85, 3.54, 4.15],
    ['A4', 'slm', 'DSL, modelo pequeno ajustado', 2.78, 2.5, 3.09],
  ];
  const PROB = [['tarefas', 0.26, 0.99], ['decisões', 0.4, 1.14], ['ordem e fluxo', 0.81, 1.95], ['boa formação', 0.14, 0.03]];
  S.push({
    id: 'fidelidade', act: 'Resultados', badge: 'exploratório', name: 'Fidelidade ao texto',
    title: 'Na fidelidade, o modelo pequeno fica cerca de um ponto abaixo.',
    note: 'Nota de 0 a 5 dada pelo juiz às saídas válidas, com intervalo de confiança de 95%. Medida exploratória: o juiz não atingiu todos os limiares de validação.',
    html: `<div class="body"><svg class="fig fd" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="fd-p"><p>Problemas apontados pelo juiz por avaliação</p><div class="fd-g"></div>
      <div class="lgd in"><span class="c-dsl"><i class="sw"></i>A2r</span><span class="c-slm"><i class="sw"></i>A4</span></div></div>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), X0 = 520, W = 1040, x = (v) => X0 + (v / 5) * W, gA = K.s('g', {}, svg);
      for (let v = 0; v <= 5; v++) {
        K.s('path', { d: `M${x(v)},20 V318`, class: v ? 'hair' : 'base' }, gA);
        K.s('text', { x: x(v), y: 352, class: 'tick', text: String(v) }, gA);
      }
      K.s('text', { x: x(5) + 24, y: 352, class: 'tick l', text: 'nota do juiz' }, gA);
      const rows = FID.map(([id, cls, name, m, lo, hi], i) => {
        const y = 70 + i * 100, g = K.s('g', { class: 'c-' + cls, 'data-tip': `${id}: ${K.fmt(m, 2)}, IC 95% [${K.fmt(lo, 2)}; ${K.fmt(hi, 2)}]` }, svg);
        K.s('text', { x: 0, y: y + 8, class: 'fd-n', text: name }, g);
        K.s('text', { x: X0 - 34, y: y + 7, class: 'fd-id', text: id }, g);
        const ci = K.s('path', { d: `M${x(lo)},${y} H${x(hi)}`, class: 'fd-ci' }, g);
        const dot = K.s('circle', { cx: x(m), cy: y, r: 13, class: 'fd-dot' }, g);
        const val = K.s('text', { x: x(hi) + 22, y: y + 11, class: 'fd-v', text: K.fmt(m, 2) }, g);
        return { g, ci: K.stroke(ci), dot, val, m, y };
      });
      const eq = K.s('g', {}, svg);
      K.s('path', { d: `M${x(4.15) + 120},${rows[0].y} h18 V${rows[1].y} h-18`, class: 'fd-br' }, eq);
      K.s('text', { x: x(4.15) + 152, y: (rows[0].y + rows[1].y) / 2 + 7, class: 'fd-a', text: 'equivalentes' }, eq);
      const gap = K.s('g', {}, svg);
      K.s('path', { d: `M${x(2.78) + 22},${rows[2].y - 34} H${x(3.85) - 6} m-14,-9 l14,9 l-14,9 M${x(2.78) + 22},${rows[2].y - 34} m14,-9 l-14,9 l14,9`, class: 'fd-br' }, gap);
      K.s('text', { x: (x(2.78) + x(3.85)) / 2 + 8, y: rows[2].y - 46, class: 'fd-a mid', text: 'cerca de 1 ponto' }, gap);
      // problemas por critério: barras pareadas A2r e A4
      const host = c.$('.fd-g'), pb = PROB.map(([name, a, b4]) => {
        const el = K.h(`<div class="pb"><span>${name}</span><div><i class="c-dsl"></i><b>${K.fmt(a, 2)}</b></div><div><i class="c-slm"></i><b>${K.fmt(b4, 2)}</b></div></div>`);
        host.appendChild(el);
        return { bars: el.querySelectorAll('i'), w: [a * 150, b4 * 150] };
      });
      const panel = c.$('.fd-p');
      return K.steps([3800, 2400], ([a, b]) => {
        gA.style.opacity = K.seg(a, 0, 0.12);
        rows.forEach((r, i) => {
          const s = 0.14 + i * 0.2;
          r.g.style.opacity = K.seg(a, s, s + 0.06);
          r.ci.set(K.seg(a, s + 0.04, s + 0.16));
          r.dot.setAttribute('r', 13 * K.ease.back(K.seg(a, s + 0.04, s + 0.14)));
          r.val.style.opacity = K.seg(a, s + 0.12, s + 0.2);
        });
        eq.style.opacity = K.seg(a, 0.56, 0.66);
        gap.style.opacity = K.seg(a, 0.84, 0.96);
        panel.style.opacity = K.seg(b, 0, 0.15);
        pb.forEach((r, i) => r.bars.forEach((el, j) => (el.style.width = r.w[j] * K.ease.out(K.seg(b, 0.15 + i * 0.1, 0.6 + i * 0.1)) + 'px')));
      });
    },
  });
})();
