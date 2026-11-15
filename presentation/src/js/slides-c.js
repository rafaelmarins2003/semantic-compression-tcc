/* slides-c.js — experimento e validade (slides 11 a 16). */
(function () {
  'use strict';
  const K = window.K, S = window.SLIDES, D = window.DADOS;
  const pct = (codes) => ([...codes].filter((x) => x === 'v').length / codes.length) * 100;
  const show = (el, p, dy = 6) => {
    el.style.opacity = K.clamp(p);
    el.style.transform = `translateY(${(1 - K.ease.out(K.clamp(p))) * dy}px)`;
  };

  // Linha de resultado: rótulo, tira das 138 gerações e validade.
  K.row = (host, o) => {
    const el = K.h(`<div class="srow" style="top:${o.y}px">
      <div class="srow-l"><b>${o.title}</b><span class="tag">${o.tag}</span></div>
      <svg viewBox="0 0 1196 78" width="1196" height="78" class="c-${o.c}"></svg>
      <div class="srow-v"><b>0,0</b><i>%</i></div>
      ${o.under ? `<div class="srow-u">${o.under}</div>` : ''}</div>`);
    host.appendChild(el);
    const strip = K.strip(el.querySelector('svg'), o.arm), val = el.querySelector('.srow-v b'), to = pct(strip.codes);
    return {
      el, strip, to,
      // p: 0 → 1. Com `from` (desfechos de outro braço), a tira muda ponto a ponto.
      set(p, from) {
        el.style.opacity = K.seg(p, 0, 0.08);
        if (from) {
          strip.morph(K.seg(p, 0.12, 1), from);
          K.text(val, K.fmt(K.lerp(pct(from), to, K.ease.io(K.seg(p, 0.12, 0.96)))));
        } else {
          strip.fill(K.seg(p, 0.05, 1));
          K.text(val, K.fmt(to * K.ease.out(K.seg(p, 0.05, 0.96))));
        }
      },
    };
  };

  /* ── 11. Desenho do experimento ──────────────────────────────────────── */
  const arm = (a, txt, cls = '') => `<div class="arm ${cls}" data-a="${a}"><b>${a}</b><span>${txt}</span></div>`;
  S.push({
    id: 'experimento', act: 'Experimento', name: 'Desenho do experimento',
    title: 'Mesmos textos, mesma medida. Muda uma coisa de cada vez.',
    note: 'Validade: proporção das gerações que produzem XML aceito pelo esquema XSD oficial do BPMN 2.0, verificada por programa.',
    html: `<div class="body xp">
      <div class="xp-top">
        <svg viewBox="0 0 1196 78" width="598" height="39" class="c-ink"></svg>
        <p><b>46</b> processos do conjunto de teste <i>×</i> <b>3</b> repetições <i>=</i> <b>138</b> gerações por braço</p>
      </div>
      <div class="xp-grid">
        <div></div>
        <div class="xh c-xml"><span class="sw"></span>escreve XML</div>
        <div class="xh c-dsl"><span class="sw"></span>escreve DSL, que o transpilador expande</div>
        <div class="xm"><b>DeepSeek V4 Pro</b><span>modelo de grande porte</span></div>
        <div class="xc">${arm('A1', 'geração direta, a prática corrente')}</div>
        <div class="xc">${arm('A2', 'gramática da DSL no prompt')}</div>
        <div class="xm"><b>GLM 5.2</b><span>grande porte, gerou o corpus</span></div>
        <div class="xc">${arm('A1g', 'geração direta')}</div>
        <div class="xc">${arm('A2g', 'gramática da DSL no prompt')}</div>
        <div class="xm"><b>Qwen2.5-Coder 7B</b><span>modelo pequeno</span></div>
        <div class="xc"></div>
        <div class="xc">${arm('A3', 'gramática no prompt, sem ajuste')}${arm('A3m', 'prompt mínimo, sem ajuste')}${arm('A4', 'prompt mínimo, com ajuste fino', 'slm')}</div>
      </div>
      <div class="enc e1"><span>mesmo modelo:<br>muda só o formato</span></div>
      <div class="enc e2"><span>mesmo modelo e mesmo prompt: muda só o adaptador</span></div>
    </div>`,
    setup(c) {
      const strip = K.strip(c.$('.xp-top svg'), 'A1', { codes: 'v'.repeat(138), plain: true });
      const cells = c.$$('.xp-grid > *'), body = c.$('.body'), e1 = c.$('.e1'), e2 = c.$('.e2'), top = c.$('.xp-top p');
      const T = (a) => c.$(`.arm[data-a="${a}"]`);
      let done = false;
      const place = (enc, a, b) => {
        const r1 = K.rectIn(T(a), body), r2 = K.rectIn(T(b), body), pad = 10;
        enc.style.left = r1.x - pad + 'px';
        enc.style.top = r1.y - pad + 'px';
        enc.style.width = r2.x + r2.w - r1.x + 2 * pad + 'px';
        enc.style.height = r1.h + 2 * pad + 'px';
      };
      return K.steps([3200, 700, 700], ([a, b, d]) => {
        if (!done) { place(e1, 'A1', 'A2'); place(e2, 'A3m', 'A4'); done = true; }
        strip.fill(K.seg(a, 0, 0.5));
        top.style.opacity = K.seg(a, 0.1, 0.3);
        cells.forEach((el, i) => show(el, K.seg(a, 0.34 + Math.floor(i / 3) * 0.12, 0.52 + Math.floor(i / 3) * 0.12)));
        e1.style.opacity = K.ease.out(b);
        e2.style.opacity = K.ease.out(d);
      });
    },
  });

  /* ── 12. A DSL reduziu a validade ────────────────────────────────────── */
  S.push({
    id: 'validade', act: 'Resultados', name: 'A DSL reduziu a validade',
    title: 'Com o mesmo modelo, pedir DSL no lugar de XML reduziu a validade.',
    note: 'Cada ponto é uma geração: coluna = processo, linha = repetição. Cheio = XML aceito pelo XSD oficial. Vazado = saída inválida.',
    html: `<div class="body rows">
      <div class="gh" style="top:6px">DeepSeek V4 Pro</div>
      <div class="gh g2" style="top:336px">GLM 5.2 <span>o modelo que gerou o corpus</span></div>
    </div>`,
    setup(c) {
      const host = c.$('.rows'), g2 = c.$('.g2');
      const r = [
        K.row(host, { y: 48, arm: 'A1', c: 'xml', title: 'escreve XML', tag: 'A1' }),
        K.row(host, { y: 166, arm: 'A2', c: 'dsl', title: 'escreve DSL', tag: 'A2' }),
        K.row(host, { y: 378, arm: 'A1g', c: 'xml', title: 'escreve XML', tag: 'A1g' }),
        K.row(host, { y: 496, arm: 'A2g', c: 'dsl', title: 'escreve DSL', tag: 'A2g' }),
      ];
      return K.steps([4800, 4800], ([a, b]) => {
        r[0].set(K.seg(a, 0.02, 0.5));
        r[1].set(K.seg(a, 0.46, 1));
        g2.style.opacity = K.seg(b, 0, 0.08);
        r[2].set(K.seg(b, 0.02, 0.5));
        r[3].set(K.seg(b, 0.46, 1));
      });
    },
  });

  /* ── 13. Onde a DSL falha ────────────────────────────────────────────── */
  S.push({
    id: 'causa', act: 'Resultados', name: 'Onde a DSL falha',
    title: 'A maior parte das falhas está nas referências a elementos já escritos.',
    note: 'Classificação pela mensagem do analisador. No GLM 5.2 (A2g), as referências respondem por 41 das 65 saídas inválidas.',
    html: `<div class="body cz">
      <div class="srow-l cz-l"><b>escreve DSL</b><span class="tag">A2</span></div>
      <svg class="fig c-dsl" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="cz-r"><b>52</b><span>inválidas<br>de 138</span></div>
      <div class="cz-g g1"><b class="n1">0</b><span>falhas de referência</span></div>
      <div class="cz-g g2"><b class="n2">0</b><span>outras falhas de sintaxe</span></div>
      <div class="cz-s s1"><code>-&gt; #detailedReview</code><span><b>26</b> apontam para um identificador que nenhum elemento recebeu</span></div>
      <div class="cz-s s2"><code>#appoint: task "…"</code><span><b>12</b> tentam declarar o destino depois de usá-lo</span></div>
    </div>`,
    setup(c) {
      const svg = c.$('svg'), strip = K.strip(svg, 'A2', { x: 318, y: 14 });
      strip.fill(1);
      const slot = (x0, k) => ({ x: x0 + Math.floor(k / 3) * 42 + 21, y: 306 + (k % 3) * 42 + 21 });
      const X = { u: 318, m: 318 + 9 * 42 + 76, s: 1264 }, n = { u: 0, m: 0, s: 0 };
      const fl = strip.dots.filter((d) => strip.codes[d.i] !== 'v').map((d, j) => {
        const code = strip.codes[d.i];
        const el = K.s('circle', { class: 'fly ' + (code === 's' ? 'oth' : 'ref'), 'data-tip': d.el.getAttribute('data-tip') }, svg);
        return { el, d, code, j, to: slot(X[code], n[code]++) };
      });
      const n1 = c.$('.n1'), n2 = c.$('.n2'), late = c.$$('.cz-g span, .cz-s'), heads = c.$$('.cz-g b');
      return [{
        dur: 5600,
        draw(p) {
          let nr = 0, no = 0;
          fl.forEach((f) => {
            const a = 0.14 + (f.j / fl.length) * 0.48, t = K.ease.io(K.seg(p, a, a + 0.3));
            f.el.setAttribute('cx', K.lerp(f.d.x, f.to.x, t));
            f.el.setAttribute('cy', K.lerp(f.d.y, f.to.y, t));
            f.el.setAttribute('r', K.lerp(6.7, 15, t));
            f.el.style.fillOpacity = t;
            f.el.style.opacity = p > 0.08 ? 1 : 0;
            if (t > 0.97) f.code === 's' ? no++ : nr++;
          });
          K.text(n1, String(nr));
          K.text(n2, String(no));
          heads.forEach((h) => (h.style.opacity = K.seg(p, 0.14, 0.24)));
          late.forEach((el, i) => show(el, K.seg(p, 0.8 + i * 0.03, 0.9 + i * 0.03)));
        },
      }];
    },
  });

  /* ── 14. Por que a referência falha ──────────────────────────────────── */
  const REF_ID = `process "Order Processing with Retry" {
  start
  -> service "Fetch data"
  -> service "Validate"
  -> xor "Valid?" {
    [yes] -> service "Process" -> end
    [no]  -> xor "Retry?" {
               [yes] -> #fetch`;
  S.push({
    id: 'mecanismo', act: 'Resultados', name: 'Por que a referência falha',
    title: 'Quem escreve da esquerda para a direita ainda não sabe que vai precisar voltar.',
    html: `<div class="body mec">
      <div class="panel mL" style="left:0;top:0;width:820px;height:404px">
        <div class="panel-hd"><span>referência por identificador</span><span>o que a notação pedia</span></div><div class="dsl"></div></div>
      <div class="panel mR" style="left:880px;top:0;width:820px;height:404px">
        <div class="panel-hd"><span>referência por rótulo</span><span>forma alternativa</span></div><div class="dsl"></div></div>
      <svg class="fig" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="think">vou precisar voltar aqui?</div>
      <div class="vd vL">${K.icon('cross', 'ko')}<div><code>Unresolved DSL ref #fetch</code><span>Para apontar, era preciso ter marcado o elemento quando ele foi escrito.</span></div></div>
      <div class="vd vR">${K.icon('check', 'ok')}<div><code>#"Fetch data"</code><span>O rótulo já está escrito. Basta apontar para trás.</span></div></div>
    </div>`,
    setup(c) {
      const L = K.code(c.$('.mL .dsl'), REF_ID, 'dsl'), R = K.code(c.$('.mR .dsl'), REF_ID.replace('#fetch', '#"Fetch data"'), 'dsl');
      const N = L.toks.length, body = c.$('.body'), svg = c.$('svg'), think = c.$('.think');
      const ghost = K.h('<span class="ghostref">#fetch</span>');
      L.toks[6].after(document.createTextNode(' '), ghost);
      const pR = c.$('.mR'), vL = c.$('.vL'), vR = c.$('.vR');
      let arcL = null, arcR = null;
      const arc = (from, to, cls) => {
        const a = K.rectIn(from, body), b = K.rectIn(to, body);
        const sx = a.x + a.w + 8, sy = a.y + a.h / 2, tx = b.x + b.w + 10, ty = b.y + b.h / 2;
        const path = K.s('path', { d: `M${sx},${sy} C${sx + 170},${sy} ${tx + 250},${ty} ${tx},${ty}`, class: 'refarc ' + cls }, svg);
        const head = K.s('path', { d: `M${tx + 16},${ty - 9} L${tx},${ty} L${tx + 16},${ty + 9}`, class: 'refarc ' + cls }, svg);
        const s = K.stroke(path);
        return { set(p) { s.set(p); path.style.opacity = p > 0 ? 1 : 0; head.style.opacity = K.seg(p, 0.9, 1); } };
      };
      const measure = () => {
        if (arcL) return;
        arcL = arc(L.toks[N - 1], ghost, 'bad');
        arcR = arc(R.toks[N - 1], R.toks[6], 'good');
        const g = K.rectIn(L.toks[6], body);
        think.style.left = g.x + g.w + 26 + 'px';
        think.style.top = g.y - 6 + 'px';
      };
      return K.steps([6200, 4600], ([a, b]) => {
        measure();
        const n = a >= 1 ? N : K.seg(a, 0.02, 0.6) * N;
        L.show(n);
        think.style.opacity = K.seg(n, 6.8, 7.6) * (1 - K.seg(n, 13, 16));
        arcL.set(K.ease.io(K.seg(a, 0.64, 0.82)));
        ghost.style.opacity = K.seg(a, 0.8, 0.87);
        show(vL, K.seg(a, 0.88, 1));
        pR.style.opacity = K.seg(b, 0, 0.06);
        R.show(b >= 1 ? N : K.seg(b, 0.04, 0.5) * N);
        arcR.set(K.ease.io(K.seg(b, 0.56, 0.76)));
        R.toks[6].classList.toggle('tgt', b > 0.74);
        show(vR, K.seg(b, 0.8, 1));
      });
    },
  });

  /* ── 15. Referência por rótulo ───────────────────────────────────────── */
  S.push({
    id: 'rotulo', act: 'Resultados', badge: 'exploratório', name: 'Referência por rótulo',
    title: 'Com a referência pelo rótulo, a validade do mesmo modelo subiu para 87,0%.',
    note: 'Braço A2r: definido depois de vistos os resultados do A2 e, por isso, exploratório. Mesmo modelo e mesmo prompt, exceto o trecho sobre referências.',
    html: `<div class="body rows">
      <div class="gh" style="top:6px">DeepSeek V4 Pro <span>escreve DSL</span></div>
      <div class="rfx"><span>falhas de referência</span><b>38</b>${K.icon('arrow')}<b>8</b></div>
      <div class="gh g2" style="top:424px">Referência <span>o mesmo modelo escrevendo XML direto</span></div>
    </div>`,
    setup(c) {
      const host = c.$('.rows'), rfx = c.$('.rfx'), g2 = c.$('.g2');
      const a2 = K.row(host, { y: 48, arm: 'A2', c: 'dsl', title: 'referência por identificador', tag: 'A2' });
      const a2r = K.row(host, { y: 174, arm: 'A2r', c: 'dsl', title: 'referência por rótulo', tag: 'A2r' });
      const a1 = K.row(host, { y: 466, arm: 'A1', c: 'xml', title: 'XML direto', tag: 'A1' });
      return K.steps([5200, 2600], ([a, b]) => {
        a2.set(K.seg(a, 0, 0.02) > 0 ? 1 : 0);
        a2r.set(K.seg(a, 0.12, 0.9), D.bracos.A2);
        show(rfx, K.seg(a, 0.86, 1));
        g2.style.opacity = K.seg(b, 0, 0.1);
        a1.set(K.seg(b, 0.05, 1));
      });
    },
  });

  /* ── 16. O modelo pequeno ────────────────────────────────────────────── */
  S.push({
    id: 'pequeno', act: 'Resultados', name: 'O modelo pequeno',
    title: 'O modelo pequeno aprende a notação no ajuste, sem a gramática no prompt.',
    note: 'Qwen2.5-Coder-7B-Instruct com decodificação gulosa. Prompt mínimo: 753 tokens. Prompt com a gramática: 1.351 tokens.',
    html: `<div class="body rows">
      <div class="gh" style="top:6px">Qwen2.5-Coder 7B <span>escreve DSL</span></div>
      <div class="callout"><span class="sw c-slm"></span><span>A3m e A4 usam o mesmo modelo e o mesmo prompt. A diferença é só o adaptador.</span></div>
    </div>`,
    setup(c) {
      const host = c.$('.rows'), e3 = c.$('.callout');
      const r = [
        K.row(host, { y: 48, arm: 'A3m', c: 'dsl', title: 'prompt mínimo, sem ajuste', tag: 'A3m', under: 'Sem a gramática e sem o ajuste, o modelo escreveu XML nas 138 gerações.' }),
        K.row(host, { y: 224, arm: 'A3', c: 'dsl', title: 'gramática no prompt, sem ajuste', tag: 'A3' }),
        K.row(host, { y: 366, arm: 'A4', c: 'slm', title: 'prompt mínimo, com ajuste fino', tag: 'A4' }),
      ];
      return K.steps([6400, 800], ([a, b]) => {
        r[0].set(K.seg(a, 0.02, 0.3));
        r[1].set(K.seg(a, 0.3, 0.64));
        r[2].set(K.seg(a, 0.62, 1));
        e3.style.opacity = K.ease.out(b);
      });
    },
  });
})();
