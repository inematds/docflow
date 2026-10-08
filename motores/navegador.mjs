// Navegador do estilo "historia": grava mapa ao vivo (earth.nullschool) ou tira o print de uma
// página com um trecho grifado.
//   node navegador.mjs mapa  <url> <saida.webm> <segundos> <W> <H>
//   node navegador.mjs prova <url> <saida-base> "<trecho>" <W> <H>
//     -> <saida-base>-limpo.png, <saida-base>-grifo.png, <saida-base>.json ({x,y,w,h} do trecho)
import fs from 'fs';
import path from 'path';
import { chromium } from '/home/nmaldaner/.npm-global/lib/node_modules/playwright/index.mjs';

const [, , modo, url, saida, a4, a5, a6] = process.argv;
const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl'] });

if (modo === 'mapa') {
  const [seg, W, H] = [+a4, +a5, +a6];
  const dir = saida + '.dir';
  const ctx = await b.newContext({ viewport: { width: W, height: H + 100 }, recordVideo: { dir, size: { width: W, height: H + 100 } } });
  const pg = await ctx.newPage();
  await pg.goto(url, { timeout: 60000 });
  await pg.waitForTimeout(seg * 1000);
  await ctx.close();
  const f = fs.readdirSync(dir).find((x) => x.endsWith('.webm'));
  fs.renameSync(path.join(dir, f), saida);
  fs.rmdirSync(dir);
} else if (modo === 'prova') {
  const [trecho, W, H] = [a4, +a5, +a6];
  const pg = await b.newPage({ viewport: { width: W, height: H }, locale: 'pt-BR', deviceScaleFactor: 2 });
  await pg.goto(url, { timeout: 90000, waitUntil: 'domcontentloaded' });
  await pg.waitForTimeout(5000);
  // some com banners de cookie comuns, sem clicar em nada
  await pg.addStyleTag({ content: '[id*=cookie],[class*=cookie],[id*=consent],[class*=consent],[class*=lgpd],[id*=lgpd]{display:none!important}' });
  // esconde camadas fixas grandes (cookies, avisos, paywall) e destrava a rolagem
  await pg.evaluate(() => {
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if ((cs.position === 'fixed' || cs.position === 'sticky') && el.getBoundingClientRect().width > innerWidth * 0.25) el.style.display = 'none';
    }
    document.documentElement.style.overflow = 'auto'; document.body.style.overflow = 'auto';
  });
  const box = await pg.evaluate((alvo) => {
    const norm = (s) => s.replace(/\s+/g, ' ').toLowerCase();
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const i = norm(n.textContent).indexOf(norm(alvo));
      if (i < 0) continue;
      // casa o trecho dentro do nó (sem normalizar espaços do original: busca aproximada)
      const raw = n.textContent;
      let ini = raw.toLowerCase().indexOf(alvo.toLowerCase());
      if (ini < 0) ini = 0;
      const r = document.createRange();
      r.setStart(n, ini);
      r.setEnd(n, Math.min(raw.length, ini + alvo.length));
      const mark = document.createElement('mark');
      mark.id = '__grifo';
      mark.style.cssText = 'background:transparent;color:inherit;padding:0 2px';
      r.surroundContents(mark);
      mark.scrollIntoView({ block: 'center' });
      return true;
    }
    return false;
  }, trecho);
  if (!box) { console.error('trecho não achado'); process.exit(2); }
  await pg.waitForTimeout(800);
  await pg.screenshot({ path: saida + '-limpo.png' });
  const r = await pg.evaluate(() => {
    const m = document.getElementById('__grifo');
    m.style.background = '#ffd23f';
    m.style.color = '#111';
    const rects = [...m.getClientRects()].map((q) => ({ x: q.x, y: q.y, w: q.width, h: q.height }));
    return rects;
  });
  await pg.screenshot({ path: saida + '-grifo.png' });
  fs.writeFileSync(saida + '.json', JSON.stringify(r));
}
await b.close();
