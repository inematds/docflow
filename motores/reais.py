"""Motor `reais`: a cena é feita com imagens REAIS (mapas, satélite, fotos com licença) e
gráficos de dados, em vez de imagem/vídeo de IA.

Cada cena tem 1 a 4 "planos" (o roteiro escolhe as imagens do catálogo). Cada plano é uma
imagem com movimento de câmera (zoom ou pan), o crédito no canto e, se houver, um número
em destaque (ex.: "+1,8 °C"). Gráfico vira animação (a linha ou as barras vão aparecendo).
Ritmo `dinamico` = cortes secos a cada 2–3 s; `calmo` = 1–2 planos por cena.

O catálogo é uma pasta com `creditos.json` (lista de {arquivo, descricao, credito, ...}).
Os gráficos vêm do tema (`graficos:`), com os números e a fonte.
"""
import json, subprocess
from pathlib import Path

FONTE = Path.home() / '.local/share/fonts/Montserrat-ExtraBold.ttf'
FPS = 30
MOVIMENTOS = ['zoom-in', 'esquerda', 'zoom-out', 'direita', 'subir']


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError('ffmpeg: ' + r.stderr[-600:])


def dur(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def tamanho(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries',
                        'stream=width,height', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    w, h = r.stdout.strip().split('\n')[0].split(',')[:2]
    return int(w), int(h)


# ---------------------------------------------------------------- catálogo
def catalogo(t, d):
    """Imagens reais (creditos.json) + gráficos do tema (renderizados como PNG de prévia)."""
    pasta = Path(t['imagens_reais']).expanduser()
    dados = json.load(open(pasta / 'creditos.json'))
    if isinstance(dados, dict):   # {"imagens": [...], ...}
        dados = dados.get('imagens', [])
    itens = [dict(x, caminho=str(pasta / x['arquivo']), tipo='imagem')
             for x in dados
             if (pasta / x['arquivo']).exists()]
    for g in t.get('graficos', []):
        itens.append({'arquivo': g['arquivo'], 'tipo': 'grafico', 'grafico': g,
                      'descricao': f'GRÁFICO: {g["titulo"]} ({g.get("unidade", "")}) — '
                                   + ', '.join(f'{r}: {v}' for r, v in zip(g['rotulos'], g['valores'])),
                      'credito': f'Dados: {g["fonte"]}'})
    return itens


def texto_catalogo(itens):
    return '\n'.join(f'- {x["arquivo"]}: {x.get("descricao", "")} [{x.get("data", "")}]'
                     for x in itens)


# ---------------------------------------------------------------- gráfico animado
def grafico(g, saida, segundos, W, H):
    """Linha ou barras que vão aparecendo em 70% do tempo e param com o último valor marcado."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.animation import FFMpegWriter
    import logging
    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    try:
        font_manager.fontManager.addfont(str(FONTE))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(FONTE)).get_name()
    except Exception:
        pass
    rot, val = g['rotulos'], [float(v) for v in g['valores']]
    destaque = g.get('destaque_cor', '#f0e805')
    fig, ax = plt.subplots(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor('#0d1117'); ax.set_facecolor('#0d1117')
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#8b949e')
    ax.tick_params(colors='#c9d1d9', labelsize=13)
    fig.text(0.06, 0.92, g['titulo'], color='white', fontsize=26)
    fig.text(0.06, 0.865, g.get('subtitulo', g.get('unidade', '')), color='#8b949e', fontsize=15)
    fig.text(0.06, 0.03, f'Fonte: {g["fonte"]}', color='#8b949e', fontsize=12)
    fig.subplots_adjust(left=0.08, right=0.95, top=0.80, bottom=0.14)
    xs = list(range(len(val)))
    lo, hi = min(0, min(val)), max(val)
    ax.set_ylim(lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.18)
    ax.set_xlim(-0.6, len(val) - 0.4)
    from matplotlib.ticker import FuncFormatter
    br = (lambda x: x.replace('.', ',')) if g.get('decimal', ',') == ',' else (lambda x: x)
    if g.get('milhar'):   # 12562 -> 12.562
        fmt_y = lambda v: f'{v:,.0f}'.replace(',', '.')
    else:
        fmt_y = lambda v: br(f'{v:g}')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_y(v)))
    passo = max(1, len(rot) // 12)
    ax.set_xticks(xs[::passo]); ax.set_xticklabels(rot[::passo])
    if lo < 0:
        ax.axhline(0, color='#8b949e', lw=1)
    for lim, cor in g.get('limiares', []):
        ax.axhline(lim, color=cor, lw=1, ls='--', alpha=0.7)
    n_frames = int(segundos * FPS)
    cresce = max(1, int(n_frames * 0.7))
    tipo = g.get('tipo', 'linha')
    barras = ax.bar(xs, [0] * len(val), color='#e2a23b') if tipo == 'barras' else None
    if barras is not None and g.get('realce') is not None:
        barras[g['realce']].set_color(destaque)
    linha, = ax.plot([], [], color='#e2a23b', lw=4) if tipo == 'linha' else (None,)
    ponto = ax.scatter([], [], s=140, color=destaque, zorder=5)
    rotulo = ax.text(0, 0, '', color=destaque, fontsize=22, ha='center')
    fmt = g.get('formato', '{:.1f}')
    w = FFMpegWriter(fps=FPS, codec='libx264', extra_args=['-pix_fmt', 'yuv420p', '-crf', '18'])
    with w.saving(fig, str(saida), dpi=100):
        for f in range(n_frames):
            k = min(1.0, (f + 1) / cresce)
            if tipo == 'barras':
                for i, b in enumerate(barras):   # cada barra cresce na sua vez
                    ki = min(1.0, max(0.0, k * len(val) - i))
                    b.set_height(val[i] * ki)
                i = min(len(val) - 1, int(k * len(val) - 1e-9))
                x, y = i, val[i] * min(1.0, max(0.0, k * len(val) - i))
            else:
                pos = k * (len(val) - 1)
                i = int(pos)
                fr = pos - i
                px = xs[:i + 1] + ([i + fr] if i + 1 < len(val) else [])
                py = val[:i + 1] + ([val[i] + (val[i + 1] - val[i]) * fr] if i + 1 < len(val) else [])
                linha.set_data(px, py)
                x, y = px[-1], py[-1]
            ponto.set_offsets([[x, y]])
            rotulo.set_position((x, y + (hi - lo) * 0.06))
            rotulo.set_text(((fmt_y(y) if g.get('milhar') else br(fmt.format(y))) + g.get('sufixo', '')) if f >= cresce - 1 or tipo == 'linha' else '')
            w.grab_frame()
    plt.close(fig)


def previa_grafico(g, saida, W, H):
    """PNG do gráfico completo (thumb e CTA usam imagens/NNN.png)."""
    tmp = Path(saida).with_suffix('.mp4')
    grafico(g, tmp, 1.0, W, H)
    sh(['ffmpeg', '-loglevel', 'error', '-sseof', '-0.1', '-i', str(tmp), '-frames:v', '1',
        '-y', str(saida)])
    tmp.unlink()


# ---------------------------------------------------------------- plano (uma imagem)
def plano(img, saida, segundos, mov, credito, destaque, rotulo, W, H, tmp, fade=True, zoom0=1.0):
    """Imagem com movimento + crédito + número em destaque + rótulo do lugar/data."""
    n = int(segundos * FPS)
    iw, ih = tamanho(img)
    caber = abs((iw / ih) - (W / H)) > 0.25   # mapa/gráfico fora de 16:9: cabe inteiro, fundo desfocado
    W2, H2 = W * 2, H * 2
    if caber:
        base = (f'[0:v]split[a][b];[a]scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},'
                f'gblur=sigma=30,eq=brightness=-0.25[fundo];[b]scale={int(W2 * 0.92)}:{int(H2 * 0.92)}:'
                f'force_original_aspect_ratio=decrease[frente];[fundo][frente]overlay=(W-w)/2:(H-h)/2,')
        z = 0.05   # movimento mais contido para não cortar o mapa
    else:
        base = f'[0:v]scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},'
        z = 0.14
    zz = {'zoom-in': f'{zoom0}+{z}*on/{n}', 'zoom-out': f'{zoom0 + z}-{z}*on/{n}'}.get(mov, f'{zoom0 + z}')
    xx = {'esquerda': f'(iw-iw/zoom)*(1-on/{n})', 'direita': f'(iw-iw/zoom)*on/{n}'}.get(mov, 'iw/2-(iw/zoom/2)')
    yy = {'subir': f'(ih-ih/zoom)*(1-on/{n})'}.get(mov, 'ih/2-(ih/zoom/2)')
    vf = base + f"zoompan=z='{zz}':x='{xx}':y='{yy}':d={n}:s={W}x{H}:fps={FPS}"
    vf += textos(credito, destaque, rotulo, W, H, tmp, saida, fade)
    sh(['ffmpeg', '-loglevel', 'error', '-loop', '1', '-i', str(img), '-filter_complex', vf + '[v]',
        '-map', '[v]', '-t', f'{segundos:.3f}', '-r', str(FPS), '-c:v', 'libx264', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-y', str(saida)])


def pad(txt):
    """ffmpeg 6.1 (drawtext com harfbuzz) come 1 letra do fim por byte extra de acento:
    "Pacífico" vira "Pacífic". Completar com espaços devolve as letras."""
    txt = txt.replace('\u2212', '-').replace('\u2013', '-')   # a Montserrat não tem o "−" tipográfico
    return txt + ' ' * (len(txt.encode()) - len(txt))


def textos(credito, destaque, rotulo, W, H, tmp, saida, fade=True):
    """drawtext lendo de arquivo (sem escapar aspas, dois-pontos e acentos)."""
    def arq(nome, txt):
        p = Path(tmp) / f'{Path(saida).stem}-{nome}.txt'
        p.write_text(pad(txt))
        return p
    vf = ''
    entra = "alpha='min(1,max(0,(t-0.25)/0.35))'" if fade else "alpha=1"
    if credito:
        vf += (f",drawtext=expansion=none:fontfile={FONTE}:textfile={arq('cred', credito)}:fontsize={H // 40}:"
               f"fontcolor=white@0.85:shadowcolor=black@0.8:shadowx=2:shadowy=2:"
               f"x=w-text_w-{W // 40}:y=h-text_h-{H // 30}")
    if rotulo:
        vf += (f",drawtext=expansion=none:fontfile={FONTE}:textfile={arq('rot', rotulo.upper())}:fontsize={H // 30}:"
               f"fontcolor=white:box=1:boxcolor=0xE2A23B@0.92:boxborderw={H // 70}:"
               f"x={W // 25}:y={H // 14}:{entra}")
    if destaque and destaque.get('numero'):
        y0 = int(H * 0.62)
        vf += (f",drawbox=x={W // 25 - 10}:y={y0 - 14}:w={int(W * 0.46)}:h={int(H * 0.27)}:"
               f"color=black@0.55:t=fill:enable='gte(t,{0.2 if fade else 0})'"
               f",drawtext=expansion=none:fontfile={FONTE}:textfile={arq('num', destaque['numero'])}:fontsize={H // 9}:"
               f"fontcolor=0xF0E805:x={W // 25 + 8}:y={y0}:{entra}"
               f",drawtext=expansion=none:fontfile={FONTE}:textfile={arq('txt', destaque.get('texto', ''))}:"
               f"fontsize={H // 30}:fontcolor=white:x={W // 25 + 8}:y={y0 + H // 8}:{entra}")
    return vf


# ---------------------------------------------------------------- cena
def cena(c, itens, segundos, ritmo, W, H, tmp, saida, log):
    """Junta os planos da cena com cortes secos (dinâmico) ou fundidos (calmo), no tempo exato."""
    por_nome = {x['arquivo']: x for x in itens}
    planos = [p for p in c.get('planos', []) if p.get('imagem') in por_nome] or \
             [{'imagem': itens[(c['n'] - 1) % len(itens)]['arquivo']}]
    cada = segundos / len(planos)
    partes = []
    if ritmo == 'dinamico':   # foto longa vira 2 cortes (abre e fecha), troca a cada 2–3 s
        novos = []
        for p in planos:
            x = por_nome[p['imagem']]
            if x['tipo'] == 'imagem' and cada > 3.6:
                mov = p.get('movimento') or 'zoom-in'
                outro = {'zoom-in': 'direita', 'zoom-out': 'esquerda', 'esquerda': 'zoom-in',
                         'direita': 'zoom-out', 'subir': 'zoom-in'}[mov]
                novos += [dict(p, movimento=mov, _dur=cada / 2),
                          dict(p, movimento=outro, _dur=cada / 2, _segundo=True)]
            else:
                novos.append(dict(p, _dur=cada))
        planos = novos
    for i, p in enumerate(planos):
        cada = p.get('_dur', segundos / len(planos))
        x = por_nome[p['imagem']]
        out = Path(tmp) / f'plano-{c["n"]:03d}-{i}.mp4'
        rot = c.get('rotulo') if i == 0 or (i == 1 and planos[1].get('_segundo')) else None
        if x['tipo'] == 'grafico':
            g = Path(tmp) / f'grafico-{c["n"]:03d}-{i}.mp4'
            grafico(x['grafico'], g, cada, W, H)
            vf = f'scale={W}:{H},fps={FPS}'   # gráfico já tem título: sem rótulo por cima
            sh(['ffmpeg', '-loglevel', 'error', '-i', str(g), '-vf', vf, '-t', f'{cada:.3f}',
                '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-y', str(out)])
        else:
            mov = p.get('movimento') or MOVIMENTOS[(c['n'] + i) % len(MOVIMENTOS)]
            seg2 = bool(p.get('_segundo'))   # 2º corte: mais perto, textos já na tela
            plano(x['caminho'], out, cada, mov, x.get('credito'), p.get('destaque'), rot, W, H, tmp,
                  fade=not seg2, zoom0=1.18 if seg2 else 1.0)
        partes.append(out)
    lista = Path(tmp) / f'cena-{c["n"]:03d}-lista.txt'
    lista.write_text(''.join(f"file '{p}'\n" for p in partes))
    sh(['ffmpeg', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lista),
        '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-map', '0:v', '-map', '1:a',
        '-t', f'{segundos:.3f}', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-y', str(saida)])
    log(f'  cena {c["n"]:03d}: {len(planos)} planos · {segundos:.1f}s')


# ---------------------------------------------------------------- entrada do docflow
def gerar(p, t, d, log, x_transicao, folga):
    """Um clipe por cena no tempo exato da fala (a montagem não precisa acelerar nada)."""
    from montagem import RES
    W, H = RES.get(t['formato'], RES['16:9'])
    itens = catalogo(t, d)
    ritmo = t.get('ritmo', 'calmo')
    tmp = d / 'tmp/reais'
    tmp.mkdir(parents=True, exist_ok=True)
    por_nome = {x['arquivo']: x for x in itens}
    ultima = p['cenas'][-1]['n']
    for c in p['cenas']:
        n = c['n']
        wav, dest = d / f'narracao/{n:03d}.wav', d / f'videos/{n:03d}.mp4'
        if dest.exists():
            continue
        if not wav.exists():
            raise SystemExit(f'reais: falta a narração da cena {n} (o motor reais narra antes de gerar)')
        seg = dur(wav) + folga + (x_transicao if n != ultima or t.get('cta', True) else 1.5)
        cena(c, itens, seg, ritmo, W, H, tmp, dest, log)
        png = d / f'imagens/{n:03d}.png'   # 1ª imagem da cena: serve à thumb e ao CTA
        if not png.exists():
            prim = next((por_nome[q['imagem']] for q in c.get('planos', []) if q.get('imagem') in por_nome), None)
            if prim and prim['tipo'] == 'grafico':
                previa_grafico(prim['grafico'], png, W, H)
            elif prim:
                sh(['ffmpeg', '-loglevel', 'error', '-i', prim['caminho'], '-vf',
                    f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}',
                    '-frames:v', '1', '-y', str(png)])


def creditos_usados(p, t, d):
    """Linhas de crédito das imagens que entraram no vídeo (para a descrição)."""
    por_nome = {x['arquivo']: x for x in catalogo(t, d)}
    vistos = []
    for c in p['cenas']:
        for q in c.get('planos', []):
            x = por_nome.get(q.get('imagem'))
            if not x:
                continue
            linha = x.get('credito', '')   # licença fica no creditos.json; na descrição, crédito + link
            if x.get('fonte_url') and x['tipo'] == 'imagem':
                linha += f' {x["fonte_url"]}'
            if linha and linha not in vistos:
                vistos.append(linha)
    return vistos
