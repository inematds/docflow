#!/usr/bin/env python3
"""docflow — tema -> documentário curto narrado -> YouTube.

Recria o processo do vídeo de referência (flow no GPT -> Google Flow -> TTS -> música ->
CapCut -> YouTube) sem passos manuais:

  roteiro   as 6 respostas do tema.yaml viram roteiro + prompts (Codex, pela assinatura)
  gerar     imagens 001..N e clipes 001..N pelo motor escolhido (flow | agnes)
  narrar    uma fala por cena (inemavox, local) -> encaixa no tempo de cada cena
  montar    ffmpeg faz o papel do CapCut: tempo, transição, fades, ambiente, música
  estatica  troca o clipe de IA de uma cena pela imagem com zoom lento (--cenas 6)
  descricao gera a descrição com o rodapé (projeto, APIs, INEMA.CLUB); --video URL aplica
  publicar  yt-pubx (dry-run por padrão; --enviar sobe de verdade)
  tudo      roteiro -> gerar -> narrar -> montar (para antes de publicar)

Saída: ~/projetos/output/docflow/<slug>/
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent
SAIDA = Path.home() / 'projetos/output/docflow'
VERSAO = '0.2.0'
os.environ.setdefault('NODE_PATH', str(Path.home() / '.npm-global/lib/node_modules'))


# ---------------------------------------------------------------- tema / plano
def carregar_tema(caminho):
    t = yaml.safe_load(open(caminho))
    t['n_cenas'] = max(1, round(t['duracao_total'] / t['duracao_cena']))
    t['palavras_cena'] = int(t['duracao_cena'] * 2.2)   # ~2,2 palavras/s em narração calma
    t.setdefault('fatos', 'nenhum fato fornecido: use só conhecimento consolidado')
    t.setdefault('estrutura', 'livre, em ordem cronológica')
    d = SAIDA / t['slug']
    for sub in ('imagens', 'videos', 'narracao', 'tmp'):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return t, d


def plano(d):
    p = d / 'plano.json'
    if not p.exists():
        sys.exit(f'falta {p} — rode `docflow roteiro` antes')
    return json.load(open(p))


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- 1. roteiro
def cmd_roteiro(t, d, refazer=False):
    alvo = d / 'plano.json'
    if alvo.exists() and not refazer:
        log(f'roteiro: já existe {alvo} (use --refazer)')
        return json.load(open(alvo))
    pedido = (RAIZ / 'roteiro/flow-gpt.md').read_text().format(**t)
    modelo = os.environ.get('DOCFLOW_CODEX_MODELO', 'gpt-6-astra')
    log(f'roteiro: Codex ({modelo}) escrevendo {t["n_cenas"]} cenas...')
    r = subprocess.run(['codex', 'exec', '-m', modelo, '-s', 'read-only',
                        '--skip-git-repo-check', '-'],
                       input=pedido, capture_output=True, text=True, timeout=900)
    bruto = r.stdout
    m = re.search(r'\{.*\}', bruto, re.S)
    if not m:
        (d / 'tmp/codex-saida.txt').write_text(bruto + '\n---\n' + r.stderr)
        sys.exit('roteiro: o Codex não devolveu JSON (ver tmp/codex-saida.txt)')
    p = json.loads(m.group(0))
    if len(p['cenas']) != t['n_cenas']:
        sys.exit(f'roteiro: vieram {len(p["cenas"])} cenas, esperava {t["n_cenas"]}')
    json.dump(p, open(alvo, 'w'), ensure_ascii=False, indent=2)
    escrever_blocos(p, t, d)
    log(f'roteiro: "{p["titulo"]}" -> {alvo}')
    return p


def escrever_blocos(p, t, d):
    """Os mesmos blocos que o flow do vídeo entregava para colar no agente do Flow."""
    n = len(p['cenas'])
    img = [f'Generate {n} separate images, {t["formato"]}, one per prompt. '
           f'Name each file with its number (001, 002, ...). Do not merge prompts.\n']
    vid = [f'Animate each image into a {t["duracao_cena"]}-second video, {t["formato"]}, '
           f'keeping the same number as the image (image 001 -> video 001).\n']
    for c in p['cenas']:
        img.append(f'{c["n"]:03d}: {c["prompt_imagem"]}')
        vid.append(f'{c["n"]:03d}: {c["prompt_video"]}')
    (d / 'bloco-imagens.txt').write_text('\n'.join(img) + '\n')
    (d / 'bloco-videos.txt').write_text('\n'.join(vid) + '\n')
    (d / 'narracao.txt').write_text('\n'.join(c['narracao'] for c in p['cenas']) + '\n')
    (d / 'musica.txt').write_text(p['prompt_musica'] + '\n')


# ---------------------------------------------------------------- 2. gerar
def cmd_gerar(t, d, motor):
    p = plano(d)
    if motor == 'agnes':
        from motores import agnes
        agnes.gerar(p, t, d, log)
    elif motor == 'flow':
        r = subprocess.run(['node', str(RAIZ / 'motores/flow.mjs'), 'gerar', str(d),
                            str(len(p['cenas'])), t['formato']])
        if r.returncode:
            sys.exit('flow: falhou (ver acima). Reserva: --motor agnes')
    else:
        sys.exit(f'motor "{motor}" ainda não implementado (ver README)')
    faltam = [c['n'] for c in p['cenas'] if not (d / f'videos/{c["n"]:03d}.mp4').exists()]
    if faltam:
        sys.exit(f'gerar: faltam clipes {faltam} — rode de novo (só refaz o que falta)')
    log(f'gerar: {len(p["cenas"])} clipes prontos')


def cmd_estatica(t, d, cenas):
    """Troca o clipe de IA da cena pela própria imagem com zoom lento (sem IA de vídeo).
    Para cena em que o gerador "deriva" (muda época, arquitetura, rosto)."""
    from montagem import RES
    W, H = RES.get(t['formato'], RES['16:9'])
    fps, seg = 30, t['duracao_cena']
    for n in cenas:
        png, dest = d / f'imagens/{n:03d}.png', d / f'videos/{n:03d}.mp4'
        if dest.exists():
            (d / 'tmp/descartes').mkdir(parents=True, exist_ok=True)
            dest.rename(d / f'tmp/descartes/{n:03d}-ia-{int(time.time())}.mp4')
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-loop', '1', '-i', str(png),
                        '-vf', f'scale={W * 2}:-2,zoompan=z=\'min(1+0.0009*on,1.25)\':'
                        f'x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':d={fps * seg}:s={W}x{H}:fps={fps}',
                        '-t', str(seg), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(dest)],
                       check=True)
        log(f'  cena {n:03d}: imagem com zoom lento ({seg}s)')


# ---------------------------------------------------------------- 3. narrar
def cmd_narrar(t, d):
    sys.path.insert(0, str(Path.home() / 'projetos/videos-agnes'))
    import pipeline as va   # narrar() do videos-agnes: inemavox chatterbox com voz de referência
    p = plano(d)
    for c in p['cenas']:
        dest = d / f'narracao/{c["n"]:03d}.wav'
        if dest.exists() and dest.stat().st_size > 10000:
            continue
        s = va.narrar(str(dest), c['narracao'], voz=t.get('voz', 'nei'))
        if not s:
            sys.exit(f'narrar: cena {c["n"]} falhou (inemavox :8010 no ar?)')
        log(f'  narração {c["n"]:03d}: {s:.1f}s')
    log('narrar: ok')


# ---------------------------------------------------------------- 4. montar
def cmd_montar(t, d):
    from montagem import montar
    p = plano(d)
    musica = os.path.expanduser(t['musica']) if t.get('musica') else None
    final = montar(d, [c['n'] for c in p['cenas']], t['formato'], musica, d / 'final.mp4', log)
    log(f'montar: {final}')


# ---------------------------------------------------------------- 5. publicar
MOTORES = {
    'agnes': ['Imagens: Agnes AI (agnes-image-2.1-flash), por API',
              'Vídeo de cada cena: Agnes AI (agnes-video-v2.0, imagem → vídeo), por API'],
    'flow': ['Imagens e vídeos: Google Flow (agente), automatizado no navegador'],
}


def descricao(p, t):
    """Descrição do YouTube = texto do roteiro + como foi feito (projeto, APIs) + INEMA.CLUB."""
    musica = Path(os.path.expanduser(t.get('musica', ''))).stem
    m = re.match(r'freesound_(\d+)_(.*)', musica)
    credito = f'"{m.group(2).replace("_", " ")}" (Freesound #{m.group(1)})' if m else musica
    linhas = [p['youtube']['descricao'].strip(), '',
              *([f'📌 Fontes: {t["fontes"].strip()}', ''] if t.get('fontes') else []),
              '🛠️ Como este vídeo foi feito',
              'Produzido de ponta a ponta pelo docflow, projeto aberto do INEMA que transforma '
              'um tema em documentário curto narrado: https://github.com/inematds/docflow',
              '• Roteiro, texto da narração e prompts: Codex (OpenAI), pela assinatura',
              *('• ' + x for x in MOTORES.get(t.get('motor', 'agnes'), [])),
              f'• Narração: inemavox, TTS local (chatterbox, voz {t.get("voz", "nei")})',
              *([f'• Música: {credito}'] if musica else []),
              '• Montagem: ffmpeg, local',
              '• Publicação: YouTube Data API, via yt-pubx (https://github.com/inematds/yt-pubx)',
              '',
              '📚 INEMA.CLUB: plataforma de educação gratuita, com cursos, guias e projetos '
              'abertos de inteligência artificial. Acesse: https://inema.club']
    return '\n'.join(linhas)


def cmd_descricao(t, d, video):
    """Atualiza a descrição de um vídeo já publicado com o rodapé do docflow."""
    texto = descricao(plano(d), t)
    (d / 'descricao.txt').write_text(texto + '\n')
    if not video:
        print(texto)
        log(f'descricao: salva em {d / "descricao.txt"} (passe --video URL para aplicar)')
        return
    yt = Path.home() / 'projetos/yt-pubx/yt-pubx'
    r = subprocess.run([str(yt), 'atualizar', video, '--canal', t.get('canal', 'lives1'),
                        '--description-arquivo', str(d / 'descricao.txt')],
                       capture_output=True, text=True)
    print(r.stdout[-800:], r.stderr[-800:])
    if r.returncode:
        sys.exit('descricao: o yt-pubx recusou a atualização')

def cmd_publicar(t, d, enviar=False):
    p = plano(d)
    final = d / 'final.mp4'
    if not final.exists():
        sys.exit('publicar: falta final.mp4')
    yt = Path.home() / 'projetos/yt-pubx/yt-pubx'
    plano_yt = d / 'yt-plano.json'
    if enviar:
        if not plano_yt.exists():
            sys.exit('publicar --enviar: rode primeiro sem --enviar e confira a thumb')
        cmd = [str(yt), 'publicar', str(final), '--canal', t.get('canal', 'lives1'),
               '--plano', str(plano_yt)]
    else:
        y = p['youtube']
        cmd = [str(yt), 'publicar', str(final), '--canal', t.get('canal', 'lives1'),
               '--title', y['titulo'], '--description', descricao(p, t),
               '--tags', ','.join(y['tags']), '--thumb-arte', str(d / f'imagens/{int(t.get("thumb_cena", 1)):03d}.png'),
               '--categoria', '27', '--dry-run']
    log(f'publicar: yt-pubx · canal {t.get("canal", "lives1")} · ' + ('ENVIANDO' if enviar else 'dry-run'))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-2500:], r.stderr[-1500:])
    m = re.search(r'(\S+plano\.json)', r.stdout + r.stderr)
    if m and not enviar and Path(m.group(1)).exists():
        Path(plano_yt).write_text(Path(m.group(1)).read_text())
        log(f'publicar: plano do yt-pubx copiado para {plano_yt} — confira e rode com --enviar')


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(prog='docflow', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=VERSAO)
    ap.add_argument('etapa', choices=['roteiro', 'gerar', 'narrar', 'montar', 'publicar', 'tudo',
                                      'estatica', 'descricao', 'flow-login'])
    ap.add_argument('tema', nargs='?', help='temas/<x>.yaml')
    ap.add_argument('--motor', help='flow | agnes (padrão: o do tema.yaml)')
    ap.add_argument('--refazer', action='store_true', help='refaz o roteiro')
    ap.add_argument('--cenas', help='estatica: números das cenas, ex. 6 ou 2,6')
    ap.add_argument('--video', help='descricao: URL do vídeo já publicado')
    ap.add_argument('--enviar', action='store_true', help='publicar de verdade (sem dry-run)')
    a = ap.parse_args()

    if a.etapa == 'flow-login':
        sys.exit(subprocess.run(['node', str(RAIZ / 'motores/flow.mjs'), 'login']).returncode)
    if not a.tema:
        ap.error('informe o tema (ex.: temas/egito.yaml)')
    t, d = carregar_tema(a.tema)
    motor = a.motor or t.get('motor', 'agnes')
    sys.path.insert(0, str(RAIZ))
    t0 = time.time()
    if a.etapa in ('roteiro', 'tudo'):
        cmd_roteiro(t, d, a.refazer)
    if a.etapa in ('gerar', 'tudo'):
        cmd_gerar(t, d, motor)
    if a.etapa in ('narrar', 'tudo'):
        cmd_narrar(t, d)
    if a.etapa in ('montar', 'tudo'):
        cmd_montar(t, d)
    if a.etapa == 'estatica':
        cmd_estatica(t, d, [int(x) for x in (a.cenas or '').split(',') if x])
    if a.etapa == 'descricao':
        cmd_descricao(t, d, a.video)
    if a.etapa == 'publicar':
        cmd_publicar(t, d, a.enviar)
    log(f'[{a.etapa}] {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
