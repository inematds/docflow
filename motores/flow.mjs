// Motor Flow — dirige o Google Flow (labs.google/flow) no navegador, como o vídeo fazia à mão.
//
// STATUS: NÃO VALIDADO. A tela do Flow nunca foi aberta por este robô (falta o login da
// conta inematds no perfil abaixo). Os seletores são por TEXTO visível, com alternativas
// PT/EN, e cada passo salva um print em <saida>/tmp/flow-*.png. O 1º uso real calibra.
//
//   node motores/flow.mjs login                 abre o Chromium; o Nei loga pelo VNC (:5900)
//   node motores/flow.mjs gerar <dir> <n> <fmt> roda as etapas e baixa a coleção (zip)
//
// Etapas (as mesmas do vídeo):
//   1 novo projeto  2 formato  3 liga o agente  4 cola o bloco de imagens  5 aprova sempre
//   6 espera N imagens  7 cola o bloco de vídeos  8 aprova  9 pede a coleção  10 baixa o zip
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// playwright global (npm i -g): import ESM ignora NODE_PATH, require não
const { chromium } = createRequire(import.meta.url)('playwright');

const PERFIL = process.env.DOCFLOW_PERFIL || path.join(os.homedir(), '.config/docflow/chrome-flow');
const DISPLAY = process.env.DOCFLOW_DISPLAY || ':99';
const URL_FLOW = 'https://labs.google/fx/tools/flow';
const MIN = 60_000;

async function abrir() {
  fs.mkdirSync(PERFIL, { recursive: true });
  return chromium.launchPersistentContext(PERFIL, {
    headless: false, acceptDownloads: true, viewport: { width: 1600, height: 900 },
    env: { ...process.env, DISPLAY }, args: ['--lang=pt-BR'],
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function print(page, dir, nome) {
  try { await page.screenshot({ path: path.join(dir, 'tmp', `flow-${nome}.png`) }); } catch {}
}

// Clica no primeiro elemento visível cujo texto/aria casa com algum dos rótulos.
async function clicar(page, rotulos, { obrigatorio = true, espera = 15000 } = {}) {
  const fim = Date.now() + espera;
  while (Date.now() < fim) {
    for (const r of rotulos) {
      const re = new RegExp(r, 'i');
      for (const loc of [page.getByRole('button', { name: re }), page.getByRole('menuitem', { name: re }),
                         page.getByRole('link', { name: re }), page.getByText(re)]) {
        const el = loc.first();
        if (await el.isVisible().catch(() => false)) { await el.click(); return r; }
      }
    }
    await sleep(700);
  }
  if (obrigatorio) throw new Error(`não achei botão: ${rotulos.join(' | ')} (calibrar seletor)`);
  return null;
}

// Cola um texto longo no campo de prompt do agente e envia.
async function enviarPrompt(page, texto) {
  const campo = page.locator('textarea, [contenteditable="true"]').last();
  await campo.waitFor({ state: 'visible', timeout: 30000 });
  await campo.click();
  await campo.fill(texto);
  await page.keyboard.press('Enter');
}

// Enquanto o agente trabalha: clica em "aprovar sempre"/"aprovar" sempre que aparecer.
async function aprovarAte(page, condicao, tetoMs) {
  const fim = Date.now() + tetoMs;
  while (Date.now() < fim) {
    await clicar(page, ['sempre aprovar', 'always approve', 'aprovar', 'approve'],
                 { obrigatorio: false, espera: 1500 });
    if (await condicao()) return true;
    await sleep(4000);
  }
  return false;
}

async function contarMidias(page, tipo) {
  return page.locator(tipo === 'video' ? 'video' : 'img[src*="googleusercontent"], img[src^="blob:"]').count();
}

async function login() {
  const ctx = await abrir();
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto(URL_FLOW);
  console.log(`Chromium aberto no display ${DISPLAY} (perfil ${PERFIL}).`);
  console.log('Abra o VNC em localhost:5900, entre com a conta inematds e aceite os termos do Flow.');
  console.log('Esperando até 20 min a tela do Flow aparecer logada...');
  const fim = Date.now() + 20 * MIN;
  while (Date.now() < fim) {
    const u = page.url();
    if (u.includes('labs.google') && !u.includes('accounts.google')
        && await page.getByText(/new project|novo projeto/i).first().isVisible().catch(() => false)) {
      console.log('Login ok — o perfil ficou salvo. Pode fechar.');
      await ctx.close();
      return 0;
    }
    await sleep(5000);
  }
  console.log('Tempo esgotado sem ver a tela logada.');
  await ctx.close();
  return 1;
}

async function gerar(dir, n, formato) {
  const blocoImg = fs.readFileSync(path.join(dir, 'bloco-imagens.txt'), 'utf8');
  const blocoVid = fs.readFileSync(path.join(dir, 'bloco-videos.txt'), 'utf8');
  const ctx = await abrir();
  const page = ctx.pages()[0] || (await ctx.newPage());
  try {
    await page.goto(URL_FLOW, { waitUntil: 'domcontentloaded' });
    if (page.url().includes('accounts.google')) throw new Error('perfil sem login — rode `docflow flow-login`');
    await print(page, dir, '01-inicio');

    await clicar(page, ['novo projeto', 'new project']);                       // 1
    await print(page, dir, '02-projeto');
    await clicar(page, [formato.replace(':', '\\s*[:x]\\s*')], { obrigatorio: false }); // 2
    await clicar(page, ['agente', 'agent'], { obrigatorio: false });           // 3
    await print(page, dir, '03-agente');

    await enviarPrompt(page, blocoImg);                                         // 4
    const okImg = await aprovarAte(page, async () => (await contarMidias(page, 'img')) >= n, 15 * MIN); // 5-6
    await print(page, dir, '04-imagens');
    if (!okImg) throw new Error(`não vi ${n} imagens em 15 min (ver tmp/flow-04-imagens.png)`);

    await enviarPrompt(page, blocoVid);                                         // 7
    const okVid = await aprovarAte(page, async () => (await contarMidias(page, 'video')) >= n, 40 * MIN); // 8
    await print(page, dir, '05-videos');
    if (!okVid) throw new Error(`não vi ${n} vídeos em 40 min (ver tmp/flow-05-videos.png)`);

    await enviarPrompt(page, `Create a collection named "${path.basename(dir)}" with all ${n} videos and all ${n} images, keeping their numbers.`); // 9
    await aprovarAte(page, async () => page.getByText(/download|baixar/i).first().isVisible().catch(() => false), 3 * MIN);
    const baixa = page.waitForEvent('download', { timeout: 10 * MIN });          // 10
    await clicar(page, ['baixar coleção', 'download collection', 'baixar', 'download']);
    const dl = await baixa;
    const zip = path.join(dir, 'tmp', 'flow-colecao.zip');
    await dl.saveAs(zip);
    await print(page, dir, '06-baixado');
    distribuir(zip, dir);
    return 0;
  } catch (e) {
    await print(page, dir, 'erro');
    console.error('flow:', e.message);
    return 2;
  } finally {
    await ctx.close();
  }
}

// Zip do Flow -> imagens/NNN.png e videos/NNN.mp4 pelo número no nome do arquivo.
function distribuir(zip, dir) {
  const tmp = path.join(dir, 'tmp', 'flow-zip');
  fs.rmSync(tmp, { recursive: true, force: true });
  execFileSync('unzip', ['-q', '-o', zip, '-d', tmp]);
  const todos = execFileSync('find', [tmp, '-type', 'f'], { encoding: 'utf8' }).trim().split('\n');
  for (const f of todos) {
    const m = path.basename(f).match(/(\d{1,3})/);
    if (!m) continue;
    const num = m[1].padStart(3, '0');
    if (/\.mp4$/i.test(f)) fs.copyFileSync(f, path.join(dir, 'videos', `${num}.mp4`));
    else if (/\.(png|jpe?g|webp)$/i.test(f)) fs.copyFileSync(f, path.join(dir, 'imagens', `${num}.png`));
  }
  console.log(`flow: ${todos.length} arquivos distribuídos`);
}

const [cmd, dir, n, formato] = process.argv.slice(2);
if (cmd === 'login') process.exit(await login());
if (cmd === 'gerar') process.exit(await gerar(dir, Number(n), formato || '16:9'));
console.log('uso: flow.mjs login | gerar <dir> <n> <formato>');
process.exit(1);
