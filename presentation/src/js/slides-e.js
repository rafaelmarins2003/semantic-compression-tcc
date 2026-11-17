/* slides-e.js — conclusão (slides 22 a 26). */
(function () {
  'use strict';
  const K = window.K, S = window.SLIDES;
  const show = (el, p, dy = 6) => {
    el.style.opacity = K.clamp(p);
    el.style.transform = `translateY(${(1 - K.ease.out(K.clamp(p))) * dy}px)`;
  };

  /* ── 22. A resposta é dividida ───────────────────────────────────────── */
  S.push({
    id: 'resposta', act: 'Conclusão', name: 'A resposta é dividida',
    title: 'Gerar a representação compacta é mais confiável e mais econômico que gerar o XML?',
    html: `<div class="body ans">
      <section class="an a1">
        <h2>Mais confiável?</h2>
        <div class="an-v">${K.icon('cross', 'ko')}<b>Não</b></div>
        <div class="an-m"><svg viewBox="0 0 1196 78" width="552" height="36" class="c-xml"></svg><p><b>97,8%</b> de validade com o XML direto</p></div>
        <div class="an-m"><svg viewBox="0 0 1196 78" width="552" height="36" class="c-slm"></svg><p><b>87,0%</b> no melhor resultado com a DSL</p></div>
      </section>
      <section class="an a2">
        <h2>Mais econômico?</h2>
        <div class="an-v">${K.icon('check', 'ok')}<b>Sim</b></div>
        <div class="an-s"><b>81%</b><p>menos tokens emitidos<br>que o XML equivalente</p></div>
        <div class="an-s"><b>9,4×</b><p>menor custo por saída válida,<br>com o modelo pequeno ajustado</p></div>
      </section>
      <p class="an-f">O modelo pequeno ajustado é uma troca, e não uma substituição: custa várias vezes menos, com validade e fidelidade abaixo das do XML direto.</p>
    </div>`,
    setup(c) {
      const sv = c.$$('.an-m svg'), s1 = K.strip(sv[0], 'A1'), s2 = K.strip(sv[1], 'A4');
      const a1 = c.$('.a1'), a2 = c.$('.a2'), fin = c.$('.an-f'), v = c.$$('.an-v'), st = c.$$('.an-s');
      const stamp = (el, p) => { el.style.opacity = K.clamp(p * 3); el.style.transform = `scale(${K.lerp(1.25, 1, K.ease.out(K.clamp(p)))})`; };
      return K.steps([3400, 2400, 800], ([a, b, d]) => {
        a1.style.opacity = K.seg(a, 0, 0.1);
        s1.fill(K.seg(a, 0.1, 0.5));
        s2.fill(K.seg(a, 0.3, 0.7));
        stamp(v[0], K.seg(a, 0.72, 0.9));
        a2.style.opacity = K.seg(b, 0, 0.12);
        st.forEach((el, i) => show(el, K.seg(b, 0.15 + i * 0.2, 0.4 + i * 0.2)));
        stamp(v[1], K.seg(b, 0.7, 0.9));
        fin.style.opacity = K.ease.out(d);
      });
    },
  });

  /* ── 23. A lição de projeto ──────────────────────────────────────────── */
  const TAPE = ['service', '"Fetch data"', '->', 'service', '"Validate"', '->', 'xor', '"Retry?"', '{', '[yes]', '->'];
  S.push({
    id: 'licao', act: 'Conclusão', name: 'Uma condição para notações',
    title: 'Uma notação escrita por um modelo de linguagem deve poder apontar para o que já foi escrito.',
    note: 'A condição vale para qualquer notação com referências cruzadas. Aqui, foi testada de forma exploratória e em um único modelo.',
    html: `<div class="body"><svg class="fig tape" viewBox="0 0 1700 714" width="1700" height="714"></svg>
      <div class="tp-l bad">${K.icon('cross', 'ko')}<span>Anunciar antes: ao escrever o elemento, é preciso prever que haverá uma volta.</span></div>
      <div class="tp-l good">${K.icon('check', 'ok')}<span>Apontar para trás: o destino já está no contexto.</span></div>
    </div>`,
    setup(c) {
      const svg = c.$('svg.fig'), Y = 250, H = 64, chips = [];
      let x = 0;
      TAPE.forEach((t) => {
        const w = t.length * 14.4 + 30, g = K.s('g', {}, svg);
        K.s('rect', { x, y: Y, width: w, height: H, rx: 10, class: 'chip' }, g);
        K.s('text', { x: x + w / 2, y: Y + H / 2, class: 'chip-t' + (t[0] === '"' ? ' s' : ''), text: t }, g);
        chips.push({ g, x, w });
        x += w + 9;
      });
      const cur = K.s('rect', { x, y: Y + 6, width: 20, height: H - 12, rx: 4, class: 'cursor' }, svg), xc = x + 10;
      const gf = K.s('g', {}, svg), fx = x + 50;
      for (let i = 0; i < 3; i++) K.s('rect', { x: fx + i * 96, y: Y, width: 86, height: H, rx: 10, class: 'slot' }, gf);
      const gl = K.s('g', {}, svg);
      K.s('path', { d: `M0,${Y + H + 20} H${x - 14}`, class: 'tp-b' }, gl);
      K.s('text', { x: 0, y: Y + H + 52, class: 'tick l', text: 'já escrito' }, gl);
      K.s('path', { d: `M${fx},${Y + H + 20} H${fx + 278}`, class: 'tp-b' }, gl);
      K.s('text', { x: fx, y: Y + H + 52, class: 'tick l', text: 'ainda não escrito' }, gl);
      const tgt = chips[1], tx = tgt.x + tgt.w / 2, ex = fx + 43 + 96;
      const fwd = K.stroke(K.s('path', { d: `M${tx},${Y + H + 4} C${tx + 60},${Y + 330} ${ex - 80},${Y + 330} ${ex},${Y + H + 6}`, class: 'refarc bad' }, svg));
      const fq = K.s('text', { x: ex, y: Y + H / 2, class: 'chip-t q', text: '?' }, svg);
      const back = K.stroke(K.s('path', { d: `M${xc},${Y - 6} C${xc - 80},${Y - 210} ${tx + 90},${Y - 210} ${tx},${Y - 8}`, class: 'refarc good' }, svg));
      const bh = K.s('path', { d: `M${tx + 14},${Y - 24} L${tx},${Y - 8} L${tx + 21},${Y - 9}`, class: 'refarc good' }, svg);
      const lb = c.$('.tp-l.bad'), lg = c.$('.tp-l.good');
      return K.steps([4600, 2400], ([a, b]) => {
        chips.forEach((ch, i) => (ch.g.style.opacity = K.seg(a, 0.04 + i * 0.04, 0.09 + i * 0.04)));
        cur.style.opacity = K.seg(a, 0.48, 0.52);
        gf.style.opacity = gl.style.opacity = K.seg(a, 0.5, 0.6);
        fwd.set(K.ease.io(K.seg(a, 0.62, 0.86)));
        fwd.path.style.opacity = a > 0.6 ? K.lerp(1, 0.4, b) : 0;
        fq.style.opacity = K.seg(a, 0.84, 0.92);
        lb.style.opacity = K.seg(a, 0.88, 1) * K.lerp(1, 0.5, b);
        back.set(K.ease.io(K.seg(b, 0.05, 0.6)));
        back.path.style.opacity = b > 0 ? 1 : 0;
        bh.style.opacity = K.seg(b, 0.55, 0.65);
        tgt.g.classList.toggle('hit', b > 0.6);
        lg.style.opacity = K.seg(b, 0.6, 0.85);
      });
    },
  });

  /* ── 24. Contribuições ───────────────────────────────────────────────── */
  const CONTRIB = [
    ['braces', 'BPMN-DSL e transpilador', '1.021 de 1.021 amostras do corpus aceitas pelo esquema oficial'],
    ['stack', 'Pares de texto e DSL', '768 pares e um modelo de 7 bilhões de parâmetros ajustado por US$ 0,47'],
    ['scale', 'Evidência sobre o formato de saída', 'a notação compacta reduz o custo, mas não aumenta a validade'],
    ['back', 'Condição para notações geradas por modelos', 'a referência deve poder apontar para o que já foi escrito'],
    ['ruler', 'Validação da medida de fidelidade', 'dois testes, com limiares fixados antes do uso'],
  ];
  S.push({
    id: 'contribuicoes', act: 'Conclusão', name: 'Contribuições',
    title: 'Contribuições',
    html: `<div class="body ctb">${CONTRIB.map(([ic, t, d]) => `<div class="ct-r">${K.icon(ic)}<b>${t}</b><span>${d}</span></div>`).join('')}</div>`,
    setup(c) {
      const rows = c.$$('.ct-r');
      return [{ dur: 2600, draw(p) { rows.forEach((r, i) => show(r, K.seg(p, 0.05 + i * 0.16, 0.25 + i * 0.16))); } }];
    },
  });

  /* ── 25. Limitações e próximos passos ────────────────────────────────── */
  const NEXT = [
    ['O treino só usa a referência por identificador', 'Reescrever o corpus com a referência por rótulo e retreinar'],
    ['A medida de fidelidade não atingiu todos os limiares', 'Avaliação humana cega, com mais de um avaliador'],
    ['46 itens de teste, com intervalos largos', 'Um conjunto de teste maior'],
    ['94,4% dos pares de treino vêm de uma única fonte', 'Dados de outras fontes e de outros domínios'],
    ['Uma linguagem de saída e um prompt por formato', 'Outras linguagens XML e novos braços, como o modelo pequeno em XML'],
    ['Só dois modelos de grande porte testados', 'Repetir os braços com modelos de grande porte mais recentes'],
  ];
  S.push({
    id: 'limites', act: 'Conclusão', name: 'Limitações e próximos passos',
    title: 'Cada limitação aponta um próximo passo.',
    html: `<div class="body nx"><div class="nx-h"><span>limitação</span><span></span><span>próximo passo</span></div>
      ${NEXT.map(([a, b]) => `<div class="nx-r"><span>${a}</span>${K.icon('arrow')}<b>${b}</b></div>`).join('')}</div>`,
    setup(c) {
      const rows = c.$$('.nx-r'), head = c.$('.nx-h');
      return [{
        dur: 3600,
        draw(p) {
          head.style.opacity = K.seg(p, 0, 0.08);
          rows.forEach((r, i) => {
            const a = 0.08 + i * 0.13;
            r.style.opacity = K.seg(p, a, a + 0.08);
            r.children[1].style.opacity = K.seg(p, a + 0.06, a + 0.12);
            show(r.children[2], K.seg(p, a + 0.1, a + 0.22));
          });
        },
      }];
    },
  });

  /* ── 26. Encerramento ────────────────────────────────────────────────── */
  S.push({
    id: 'fim', act: '', name: 'Obrigado', bare: true,
    html: `
    <div class="cover end">
      <h1 class="cover-title rv" data-at="0">Obrigado.</h1>
      <div class="end-s rv" data-at="0" style="--d:.3s">
        <div><b>81%</b><span>menos tokens que o XML equivalente</span></div>
        <div><b>87,0%</b><span>de saídas válidas com o modelo pequeno ajustado</span></div>
        <div><b>9,4×</b><span>menor custo por saída válida que o XML direto</span></div>
      </div>
    </div>
    <div class="morph"></div>
    <div class="cover-by rv" data-at="0" style="--d:.5s"><b>Rafael Marins Florenzano</b><span>Compressão Semântica na Geração de Modelos BPMN 2.0 por Modelos de Linguagem</span></div>`,
    setup: K.morphSetup,
    loop: (t, c, s) => K.morph(c, t, s.still),
  });
})();
