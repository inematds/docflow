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
VERSAO = '0.8.0'
os.environ.setdefault('NODE_PATH', str(Path.home() / '.npm-global/lib/node_modules'))


# ---------------------------------------------------------------- estilos
# `estilo:` no tema liga os padrões abaixo (o que o tema disser explicitamente vence).
ESTILOS = {
    'documentario': {
        'resumo': 'Documentário narrado com cenas geradas por IA (imagem -> vídeo), ritmo calmo.',
        'exemplo': 'https://www.youtube.com/watch?v=TsVY4UUc5gI (Egito)',
        'tema': {'motor': 'agnes', 'ritmo': 'calmo', 'formato': '16:9'}},
    'reais': {
        'resumo': 'Assunto atual com mapas, satélite e fotos reais, gráficos animados e números na tela.',
        'exemplo': 'https://www.youtube.com/watch?v=IE_D18omUjE (El Niño em números)',
        'tema': {'motor': 'reais', 'ritmo': 'dinamico', 'formato': '16:9'}},
    'turismo': {
        'resumo': 'Promocional de destino: abertura de impacto, fotos reais com licença, mapas animados '
                  '(pontos e rota), capítulos com o nome grande e, no fim, os endereços para pesquisar.',
        'exemplo': 'cânions dos Aparados da Serra (RS/SC)',
        'tema': {'motor': 'reais', 'ritmo': 'dinamico', 'formato': '16:9',
                 'tom': 'promocional de viagem: encantado, sensorial, convidativo, sem exagero nem superlativo falso'}},
    'alerta-vertical': {
        'resumo': 'Short 9:16 em tom de alerta: ALERTA no topo, imagem em cima, mapa ao vivo embaixo, '
                  'legenda palavra a palavra. (Protótipo montado à mão; ainda não é motor.)',
        'exemplo': 'https://www.youtube.com/watch?v=6OzZWiQHHdw (El Niño ALERTA)',
        'tema': None},
    'historia': {
        'resumo': 'Explicativo no estilo dos canais de divulgação: gancho de cena com paradoxo, '
                  'promessa, analogia, prova na tela (print grifado), grafismos animados, mapas ao vivo '
                  'e b-roll de cinema (Agnes); corte a cada 4–5 s.',
        'exemplo': '~/projetos/output/docflow/elnino-historia/final-sem-apresentador.mp4 (piloto)',
        'tema': {'motor': 'historia', 'ritmo': 'dinamico', 'formato': '16:9', 'duracao_cena': 30}},
    'historia-apresentador': {
        'resumo': 'O estilo historia com o avatar do Nei (HeyGen, pago) abrindo e fechando blocos.',
        'exemplo': '~/projetos/output/docflow/elnino-historia/final-com-apresentador.mp4 (piloto)',
        'tema': {'motor': 'historia', 'ritmo': 'dinamico', 'formato': '16:9', 'duracao_cena': 30,
                 'apresentador': True}},
}


def cmd_estilos():
    print(f'docflow {VERSAO} · estilos (use `estilo: <nome>` no tema)\n')
    for nome, e in ESTILOS.items():
        print(f'  {nome}\n    {e["resumo"]}\n    exemplo: {e["exemplo"]}\n')


# ---------------------------------------------------------------- tema / plano
def carregar_tema(caminho):
    t = yaml.safe_load(open(caminho))
    for k, v in ((ESTILOS.get(t.get('estilo', '')) or {}).get('tema') or {}).items():
        t.setdefault(k, v)
    t['n_cenas'] = max(1, round(t['duracao_total'] / t['duracao_cena']))
    t['palavras_cena'] = int(t['duracao_cena'] * 2.2)   # ~2,2 palavras/s em narração calma
    t.setdefault('fatos', 'nenhum fato fornecido: use só conhecimento consolidado')
    t.setdefault('estrutura', 'livre, em ordem cronológica')
    t.setdefault('ritmo', 'calmo')   # calmo | dinamico (cortes a cada 2–3 s)
    t.setdefault('tom', 'ritmo de notícia')
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
    if t.get('motor') == 'reais':   # imagens reais: o roteiro escolhe do catálogo
        from motores import reais
        itens = reais.catalogo(t, d)
        t['catalogo'] = reais.texto_catalogo(itens)
        t['planos_cena'] = '2 a 4' if t.get('ritmo') == 'dinamico' else '1 a 2'
        pedido = (RAIZ / 'roteiro/flow-reais.md').read_text().format(**t)
    elif t.get('motor') == 'historia':
        pedido = (RAIZ / 'roteiro/flow-historia.md').read_text().format(**t)
    else:
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
        img.append(f'{c["n"]:03d}: ' + (c.get('prompt_imagem') or
                   ' + '.join(q.get('imagem', '') for q in c.get('planos', []))))
        vid.append(f'{c["n"]:03d}: {c.get("prompt_video", "(imagem real com movimento)")}')
    (d / 'bloco-imagens.txt').write_text('\n'.join(img) + '\n')
    (d / 'bloco-videos.txt').write_text('\n'.join(vid) + '\n')
    (d / 'narracao.txt').write_text('\n'.join(c['narracao'] for c in p['cenas']) + '\n')
    (d / 'musica.txt').write_text(p.get('prompt_musica', '') + '\n')


# ---------------------------------------------------------------- 2. gerar
def cmd_gerar(t, d, motor):
    p = plano(d)
    if motor == 'agnes':
        from motores import agnes
        agnes.gerar(p, t, d, log)
    elif motor == 'reais':
        from motores import reais
        import montagem
        cmd_narrar(t, d)   # o clipe é cortado no tempo exato da fala
        reais.gerar(p, t, d, log, transicao(t), montagem.FOLGA)
    elif motor == 'historia':   # b-roll do Agnes + narração; mapas e prints saem na montagem
        from motores import historia
        historia.gerar_broll(p, d, log)
        historia.gerar_gancho(p, d, log)
        historia.Montador(p, d, log).narrar()
        log('gerar: b-roll e narração prontos (mapas ao vivo e prints são feitos no montar)')
        return
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
    if t.get('motor') == 'historia':
        from motores import historia
        return historia.Montador(plano(d), d, log).narrar()
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
CTA = 999   # número da cena de encerramento (CTA INEMA.CLUB), depois da última cena
CTA_FALA = ('Quer aprender a criar vídeos assim com inteligência artificial? '
            'Acesse inema ponto club. É gratuito.')
CTA_TEXTO = ('INEMA.CLUB', 'Cursos, guias e projetos de IA. Grátis.')
FONTE = Path.home() / '.local/share/fonts/Montserrat-ExtraBold.ttf'


def cmd_cta(t, d, ultima):
    """Cena final: a última imagem desfocada e escura, INEMA.CLUB no centro e a voz chamando.
    Desliga com `cta: false` no tema; `cta_fala` troca a frase."""
    from montagem import RES
    W, H = RES.get(t['formato'], RES['16:9'])
    wav, mp4 = d / f'narracao/{CTA}.wav', d / f'videos/{CTA}.mp4'
    if not (wav.exists() and wav.stat().st_size > 10000):
        sys.path.insert(0, str(Path.home() / 'projetos/videos-agnes'))
        import pipeline as va
        if not va.narrar(str(wav), t.get('cta_fala', CTA_FALA), voz=t.get('voz', 'nei')):
            sys.exit('cta: narração falhou (inemavox :8010 no ar?)')
    if not mp4.exists():
        marca, linha = CTA_TEXTO
        (d / 'tmp').mkdir(exist_ok=True)
        from motores.reais import pad   # ffmpeg 6.1 corta letras de texto com acento
        (d / 'tmp/cta-marca.txt').write_text(pad(marca))
        (d / 'tmp/cta-linha.txt').write_text(pad(linha))
        fps, seg = 30, 8
        aparece = "alpha='min(1,max(0,(t-0.6)/0.8))'"
        sh_vf = (f'scale={W * 2}:-2,zoompan=z=\'min(1+0.0006*on,1.15)\':x=\'iw/2-(iw/zoom/2)\':'
                 f'y=\'ih/2-(ih/zoom/2)\':d={fps * seg}:s={W}x{H}:fps={fps},'
                 f'gblur=sigma=18,eq=brightness=-0.28:saturation=0.7,'
                 f"drawtext=expansion=none:fontfile={FONTE}:textfile={d}/tmp/cta-marca.txt:fontsize={H // 6}:"
                 f"fontcolor=#f0e805:x=(w-text_w)/2:y=(h/2)-text_h:{aparece},"
                 f"drawtext=expansion=none:fontfile={FONTE}:textfile={d}/tmp/cta-linha.txt:fontsize={H // 22}:"
                 f"fontcolor=white:x=(w-text_w)/2:y=(h/2)+{H // 18}:{aparece}")
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-loop', '1',
                        '-i', os.path.expanduser(t.get('cta_imagem') or str(d / f'imagens/{ultima:03d}.png')),
                        '-vf', sh_vf, '-t', str(seg),
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(mp4)], check=True)
    log('  cta: INEMA.CLUB no fim')


def transicao(t):
    """Fusão entre cenas: 0,7 s no ritmo calmo, 0,35 s no dinâmico."""
    return 0.35 if t.get('ritmo') == 'dinamico' else 0.7


def cmd_montar(t, d):
    from montagem import montar
    p = plano(d)
    musica = os.path.expanduser(t['musica']) if t.get('musica') else None
    if t.get('motor') == 'historia':   # o CTA já é a última cena do roteiro
        from motores import historia
        historia.Montador(p, d, log, data_mapa=time.strftime('%d/%m/%y')).montar(d / 'final.mp4', musica)
        return
    numeros = [c['n'] for c in p['cenas']]
    if t.get('cta', True):
        cmd_cta(t, d, numeros[-1])
        numeros.append(CTA)
    final = montar(d, numeros, t['formato'], musica, d / 'final.mp4', log, x=transicao(t),
                   fade_in=0 if (d / 'gancho.png').exists() and p.get('gancho') else 1.2)
    log(f'montar: {final}')


# ---------------------------------------------------------------- 5. publicar
MOTORES = {
    'agnes': ['Imagens: Agnes AI (agnes-image-2.1-flash), por API',
              'Vídeo de cada cena: Agnes AI (agnes-video-v2.0, imagem → vídeo), por API'],
    'flow': ['Imagens e vídeos: Google Flow (agente), automatizado no navegador'],
    'reais': ['Imagens: mapas, satélite e fotos reais (créditos abaixo), sem IA',
              'Gráficos: matplotlib, com os dados das fontes citadas'],
    'historia': ['Cenas de cinema: Agnes AI (imagem e imagem → vídeo), por API',
                 'Mapas animados ao vivo: earth.nullschool.net (Cameron Beccario), dados NOAA',
                 'Prints de páginas oficiais com o trecho grifado (fonte e data na tela)',
                 'Grafismos animados: Python/PIL, com os dados das fontes citadas'],
}


def creditos_imagens(p, t):
    if t.get('motor') != 'reais':
        return []
    from motores import reais
    return ['', '🖼️ Créditos das imagens', *('• ' + x for x in reais.creditos_usados(p, t, SAIDA / t['slug']))]


def descricao(p, t):
    """Descrição do YouTube = texto do roteiro + como foi feito (projeto, APIs) + INEMA.CLUB."""
    musica = Path(os.path.expanduser(t.get('musica', ''))).stem
    m = re.match(r'freesound_(\d+)_(.*)', musica)
    credito = f'"{m.group(2).replace("_", " ")}" (Freesound #{m.group(1)})' if m else musica
    linhas = [p['youtube']['descricao'].strip(), '',
              *(['🔎 Para pesquisar', *('• ' + x for x in t['links']), ''] if t.get('links') else []),
              *([f'📌 Fontes: {t["fontes"].strip()}', ''] if t.get('fontes') else []),
              '🛠️ Como este vídeo foi feito',
              'Produzido de ponta a ponta pelo docflow, projeto aberto do INEMA que transforma '
              'um tema em documentário curto narrado: https://github.com/inematds/docflow',
              '• Roteiro, texto da narração e prompts: Codex (OpenAI), pela assinatura',
              *('• ' + x for x in MOTORES.get(t.get('motor', 'agnes'), [])),
              *(['• Fotos refeitas por IA a partir das originais: Agnes AI (agnes-image-2.1-flash, '
                 'imagem → imagem), por API; aparecem marcadas "Ilustração IA"'] if t.get('refazer_ia') else []),
              f'• Narração: inemavox, TTS local (chatterbox, voz {t.get("voz", "nei")})',
              *([f'• Música: {credito}'] if musica else []),
              '• Montagem: ffmpeg, local',
              '• Publicação: YouTube Data API, via yt-pubx (https://github.com/inematds/yt-pubx)',
              *creditos_imagens(p, t),
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
        arte = d / f'imagens/{int(t.get("thumb_cena", 1)):03d}.png'
        if t.get('motor') == 'historia':
            arte = d / f'broll/{t.get("thumb_broll", next(iter(p.get("broll", {})), ""))}.png'
        cmd = [str(yt), 'publicar', str(final), '--canal', t.get('canal', 'lives1'),
               '--title', y['titulo'], '--description', descricao(p, t),
               '--tags', ','.join(y['tags']), '--categoria', '27', '--dry-run']
        # thumb = a arte do gancho (Codex, texto já desenhado); sem ela, b-roll + frase do yt-pubx
        cmd += ['--thumb', str(d / 'thumb.jpg')] if (d / 'thumb.jpg').exists() else ['--thumb-arte', str(arte)]
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
                                      'estatica', 'descricao', 'flow-login', 'estilos', 'apresentador'])
    ap.add_argument('tema', nargs='?', help='temas/<x>.yaml')
    ap.add_argument('--motor', help='flow | agnes (padrão: o do tema.yaml)')
    ap.add_argument('--refazer', action='store_true', help='refaz o roteiro')
    ap.add_argument('--cenas', help='estatica: números das cenas, ex. 6 ou 2,6')
    ap.add_argument('--video', help='descricao: URL do vídeo já publicado')
    ap.add_argument('--enviar', action='store_true', help='publicar de verdade (sem dry-run)')
    ap.add_argument('--look', help='apresentador: look do avatar do Nei no HeyGen (ex.: computador)')
    ap.add_argument('--teste', action='store_true', help='apresentador: gera só a 1ª cena, para medir o custo')
    ap.add_argument('--modelo', help='apresentador: vídeo-modelo do estúdio HeyGen que define o look (padrão TEMPLATE-AVATAR16)')
    ap.add_argument('--seco', action='store_true', help='apresentador: monta o rascunho no estúdio e para antes de Gerar')
    ap.add_argument('--api', action='store_true', help='apresentador: usa o wallet de API (heygen-cli) em vez do estúdio')
    a = ap.parse_args()

    if a.etapa == 'estilos':
        return cmd_estilos()

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
    if a.etapa == 'apresentador':
        from motores import historia
        if a.api:   # wallet de API: só com autorização explícita
            if not a.look:
                sys.exit('apresentador --api: informe --look')
            historia.gerar_apresentador(plano(d), d, a.look, log, so_primeira=a.teste)
        else:       # padrão: estúdio, créditos da assinatura; o look é o do modelo
            historia.gerar_apresentador_estudio(plano(d), d, a.modelo or t.get('modelo_heygen', 'TEMPLATE-AVATAR16'),
                                                log, so_primeira=a.teste, seco=a.seco)
    log(f'[{a.etapa}] {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
