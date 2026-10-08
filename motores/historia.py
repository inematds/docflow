"""Motor "historia": documentário explicativo no estilo dos canais de divulgação (gancho de cena,
promessa, analogia, prova na tela), com paleta fixa e corte a cada 3–5 s.

Entrada: plano.json com cenas -> narracao + visuais (lista). Cada visual vira um clipe:
  mapa (earth.nullschool ao vivo), broll (Agnes ti2vid em <saida>/broll/<id>.mp4),
  prova (print real grifado), termometro, contador, capitulo, bolso, linha_tempo,
  citacao, oceano, cta, imagem (arquivo).
A duração de cada visual = narração da cena dividida entre eles (capítulo tem duração fixa).
Opcional: apresentador (vídeo do avatar do Nei por cena, em <saida>/apresentador/NN.mp4):
quando existe, a cena usa o áudio dele e alterna avatar e visuais.
"""
import json, subprocess as sp, sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from motores import grafismo as g  # noqa: E402

W, H, FPS = 1920, 1080, 30
NAV = Path(__file__).resolve().parent / 'navegador.mjs'
CRED_MAPA = 'Mapa ao vivo: earth.nullschool.net · dados NOAA'
EARTH = 'https://earth.nullschool.net/#current/'
VISTAS = {   # mapas ao vivo prontos; o plano pode trazer outros em "mapas"
    'pacifico': EARTH + 'ocean/primary/waves/overlay=sea_surface_temp_anomaly/orthographic=-110.00,-3.00,900',
    'globo': EARTH + 'ocean/primary/waves/overlay=sea_surface_temp_anomaly/orthographic=-130.00,0.00,520',
    'brasil-temp': EARTH + 'wind/surface/level/overlay=temp/orthographic=-55.00,-14.00,1300',
    'sul-vento': EARTH + 'wind/surface/level/overlay=wind/orthographic=-53.00,-29.00,3000',
    'brasil-chuva': EARTH + 'wind/surface/level/overlay=precip_3hr/orthographic=-55.00,-14.00,1300',
    'atlantico-mar': EARTH + 'ocean/primary/waves/overlay=sea_surface_temp_anomaly/orthographic=-35.00,-10.00,900',
    'mundo-vento': EARTH + 'wind/surface/level/orthographic=-60.00,0.00,350',
}


def sh(*a):
    r = sp.run([str(x) for x in a], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'{a[0]} falhou: {r.stderr[-400:]}')
    return r.stdout


def dur(p):
    return float(sh('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p))


def norm(entrada, saida, segundos, extra=''):
    """Qualquer clipe -> 1920x1080/30fps, exatamente `segundos` (estica até 1,6x, depois congela)."""
    d = dur(entrada)
    fator = min(1.6, max(1.0, segundos / d)) if d > 0 else 1.0
    vf = (f"setpts={fator:.3f}*PTS,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fps={FPS}{extra},tpad=stop_mode=clone:stop_duration={segundos},trim=duration={segundos},setsar=1,format=yuv420p")
    sh('ffmpeg', '-v', 'error', '-y', '-i', entrada, '-an', '-vf', vf, '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', saida)


def selo_mapa(tmp, data_txt):
    p = tmp / 'selo-mapa.png'
    if not p.exists():
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((48, 40), data_txt, font=g.fonte(64), fill='white', stroke_width=5, stroke_fill='black')
        f = g.fonte(26, False)
        tw = d.textlength(CRED_MAPA, font=f)
        d.rounded_rectangle((W - tw - 60, H - 70, W - 24, H - 24), 10, fill=(0, 0, 0, 170))
        d.text((W - tw - 42, H - 64), CRED_MAPA, font=f, fill=(235, 235, 235))
        im.save(p)
    return p


class Montador:
    def __init__(self, plano, saida, log=print, data_mapa='08/10/26'):
        self.p, self.d, self.log = plano, Path(saida).resolve(), log
        self.tmp = self.d / 'tmp'
        for x in ('tmp', 'clipes', 'mapas', 'provas', 'narracao'):
            (self.d / x).mkdir(parents=True, exist_ok=True)
        self.uso_mapa = {}
        self.data_mapa = data_mapa

    # ------------------------------------------------------------ fontes
    def mapa_bruto(self, vista):
        out = self.d / f'mapas/{vista}.webm'
        if not out.exists():
            self.log(f'  gravando mapa {vista}')
            sh('node', NAV, 'mapa', self.p.get('mapas', {}).get(vista) or VISTAS[vista], out, 48, W, H)
        return out

    def prova_base(self, v):
        import hashlib
        k = hashlib.md5((v['url'] + v['trecho']).encode()).hexdigest()[:10]
        base = self.d / f'provas/{k}'
        if not Path(f'{base}-grifo.png').exists():
            self.log(f'  print {v["url"][:60]}')
            sh('node', NAV, 'prova', v['url'], base, v['trecho'], W, H)
        return base

    # ------------------------------------------------------------ um visual
    def clipe(self, nome, v, seg):
        out = self.d / f'clipes/{nome}.mp4'
        if out.exists() and abs(dur(out) - seg) < 0.05:
            return out
        t = v['tipo']
        kw = {k: x for k, x in v.items() if k not in ('tipo', 'segundos')}
        if t == 'mapa':
            bruto = self.mapa_bruto(v['vista'])
            ini = 7 + self.uso_mapa.get(v['vista'], 0)
            if ini + seg > 46:
                ini = 7
            self.uso_mapa[v['vista']] = ini - 7 + seg
            tmp = self.tmp / f'{nome}-m.mp4'
            sh('ffmpeg', '-v', 'error', '-y', '-ss', ini, '-i', bruto, '-i', selo_mapa(self.tmp, self.data_mapa),
               '-filter_complex', f'[0:v]crop={W}:{H}:0:0,fps={FPS}[m];[m][1:v]overlay=0:0,format=yuv420p',
               '-t', seg, '-c:v', 'libx264', '-crf', '19', tmp)
            norm(tmp, out, seg)
        elif t == 'broll':
            mp4, png = self.d / f'broll/{v["id"]}.mp4', self.d / f'broll/{v["id"]}.png'
            if mp4.exists():
                norm(mp4, out, seg, extra=",zoompan=z='min(1+0.0008*on,1.12)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=30")
            else:
                self.log(f'  (sem vídeo do b-roll {v["id"]}: usando a imagem com zoom)')
                fr = int(seg * FPS) + 1
                sh('ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', png, '-vf',
                   f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},zoompan=z='min(1+0.0012*on,1.2)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={fr}:s={W}x{H}:fps={FPS},format=yuv420p",
                   '-t', seg, '-c:v', 'libx264', '-crf', '19', out)
        elif t == 'prova':
            g.prova(out, seg, W, H, self.prova_base(v), selo=v.get('selo', ''))
        elif t == 'imagem':
            fr = int(seg * FPS) + 1
            sh('ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', v['arquivo'], '-vf',
               f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},zoompan=z='min(1+0.0012*on,1.2)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={fr}:s={W}x{H}:fps={FPS},format=yuv420p",
               '-t', seg, '-c:v', 'libx264', '-crf', '19', out)
        else:
            if 'cor' in kw:
                kw['cor'] = tuple(kw['cor'])
            if t == 'linha_tempo':
                kw['pontos'] = [tuple(x) for x in kw['pontos']]
            if t == 'bolso':
                kw['itens'] = [tuple(x) for x in kw['itens']]
            getattr(g, t)(out, seg, W, H, **kw)
        return out

    # ------------------------------------------------------------ narração
    def narrar(self):
        sys.path.insert(0, str(Path.home() / 'projetos/videos-agnes'))
        import pipeline as va
        for c in self.p['cenas']:
            bruto = self.d / f'narracao/{c["n"]:02d}-bruto.wav'
            final = self.d / f'narracao/{c["n"]:02d}.wav'
            if not (bruto.exists() and bruto.stat().st_size > 10000):
                if not va.narrar(str(bruto), c['narracao'], voz=self.p.get('voz', 'nei')):
                    raise RuntimeError(f'narração da cena {c["n"]} falhou (inemavox :8010?)')
            if not final.exists():
                sh('ffmpeg', '-v', 'error', '-y', '-i', bruto, '-af',
                   'silenceremove=start_periods=1:start_threshold=-45dB,areverse,'
                   'silenceremove=start_periods=1:start_threshold=-45dB,areverse,'
                   f'atempo={self.p.get("atempo", 1.06)},apad=pad_dur=0.35', '-ar', '48000', '-ac', '2', final)
            self.log(f'  narração {c["n"]}: {dur(final):.1f}s')

    # ------------------------------------------------------------ cena
    def cena(self, c):
        n = c['n']
        aval = self.d / f'apresentador/{n:02d}.mp4'
        com_avatar = c.get('apresentador') and aval.exists()
        audio = self.d / f'narracao/{n:02d}.wav'
        if com_avatar:
            audio = self.tmp / f'av{n:02d}.wav'
            sh('ffmpeg', '-v', 'error', '-y', '-i', aval, '-vn', '-ar', '48000', '-ac', '2', audio)
        total = dur(audio)
        vis = list(c['visuais'])
        fixos = sum(v.get('segundos', 0) for v in vis)
        livres = [v for v in vis if 'segundos' not in v]
        if com_avatar:   # avatar abre a cena e volta entre os visuais
            pedaco = (total - fixos) / (len(livres) + 2) if livres else total
        else:
            pedaco = (total - fixos) / max(1, len(livres))
        clipes, t = [], 0.0
        seq = []
        if com_avatar:
            seq.append(('avatar', None))
            for i, v in enumerate(vis):
                seq.append(('v', v))
                if i == len(vis) // 2 - 1 and len(vis) > 1:
                    seq.append(('avatar', None))
            if len(vis) <= 1:
                seq.append(('avatar', None))
        else:
            seq = [('v', v) for v in vis]
        n_av = sum(1 for k, _ in seq if k == 'avatar')
        if com_avatar:
            pedaco = (total - fixos) / (len(livres) + n_av)
        for i, (k, v) in enumerate(seq):
            seg = (v.get('segundos') if v and 'segundos' in v else pedaco)
            if i == len(seq) - 1:
                seg = max(1.0, total - t)
            nome = f'{n:02d}-{i:02d}'
            if k == 'avatar':
                out = self.d / f'clipes/{nome}-av.mp4'
                sh('ffmpeg', '-v', 'error', '-y', '-ss', t, '-i', aval, '-t', seg, '-an', '-vf',
                   f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p',
                   '-c:v', 'libx264', '-crf', '19', out)
                clipes.append(out)
            else:
                clipes.append(self.clipe(nome, v, round(seg, 3)))
            t += seg
        lista = self.tmp / f'cena{n:02d}.txt'
        lista.write_text(''.join(f"file '{x}'\n" for x in clipes))
        vid = self.tmp / f'cena{n:02d}-v.mp4'
        sh('ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lista, '-c', 'copy', vid)
        out = self.tmp / f'cena{n:02d}.mp4'
        sh('ffmpeg', '-v', 'error', '-y', '-i', vid, '-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
           '-c:a', 'aac', '-b:a', '192k', '-t', total, out)
        self.log(f'  cena {n}: {total:.1f}s, {len(clipes)} cortes' + (' (com apresentador)' if com_avatar else ''))
        return out, len(clipes)

    def montar(self, final, musica=None):
        cenas, cortes = [], 0
        for c in self.p['cenas']:
            o, k = self.cena(c)
            cenas.append(o); cortes += k
        lista = self.tmp / 'cenas.txt'
        lista.write_text(''.join(f"file '{x}'\n" for x in cenas))
        junto = self.tmp / 'junto.mp4'
        sh('ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lista, '-c', 'copy', junto)
        total = dur(junto)
        if musica:
            sh('ffmpeg', '-v', 'error', '-y', '-i', junto, '-stream_loop', '-1', '-i', musica, '-filter_complex',
               f'[1:a]volume=0.11,afade=out:st={total - 3}:d=3[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,'
               'loudnorm=I=-16:TP=-1.5[a]', '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
               '-movflags', '+faststart', final)
        else:
            sh('ffmpeg', '-v', 'error', '-y', '-i', junto, '-af', 'loudnorm=I=-16:TP=-1.5', '-c:v', 'copy',
               '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', final)
        self.log(f'historia: {final} ({total:.0f}s, {cortes} cortes, um a cada {total / cortes:.1f}s)')
        return final


def gerar_broll(p, d, log=print):
    """plano['broll'] = {id: prompt em inglês} -> <d>/broll/<id>.png + .mp4 (Agnes, 3 em paralelo)."""
    from concurrent.futures import ThreadPoolExecutor
    from motores import agnes
    b = Path(d) / 'broll'
    b.mkdir(parents=True, exist_ok=True)

    def um(k):
        png, mp4 = b / f'{k}.png', b / f'{k}.mp4'
        if not png.exists() and not agnes.imagem(png, p['broll'][k], 1312, 736, log):
            return k, False
        return k, mp4.exists() or agnes.video(mp4, png, p['broll'][k], 1312, 736, 121, log)
    with ThreadPoolExecutor(3) as ex:
        falhas = [k for k, ok in ex.map(um, p.get('broll', {})) if not ok]
    if falhas:
        log(f'  b-roll sem vídeo: {falhas} (a montagem usa a imagem com zoom)')


HEYGEN = Path.home() / '.claude/skills/heygen-cli/scripts/heygen.mjs'


def gerar_apresentador(p, d, look, log=print, so_primeira=False):
    """Avatar do Nei (HeyGen, PAGO) falando a narração das cenas com "apresentador": true.
    Grava <d>/apresentador/NN.mp4 e o custo real de cada render em custo.json."""
    d = Path(d)
    (d / 'apresentador').mkdir(parents=True, exist_ok=True)
    custo_p = d / 'apresentador/custo.json'
    custos = json.load(open(custo_p)) if custo_p.exists() else {}
    for c in [c for c in p['cenas'] if c.get('apresentador')][:1 if so_primeira else None]:
        out = d / f'apresentador/{c["n"]:02d}.mp4'
        if out.exists():
            continue
        slug = f'{d.name}-cena{c["n"]:02d}'
        log(f'  HeyGen cena {c["n"]} ({look}, 16:9, 1080p)...')
        r = sp.run(['node', HEYGEN, '--text', c['narracao'], '--look', look, '--ratio', '16:9', '--res', '1080p',
                    '--slug', slug, '--out-dir', d / 'apresentador/bruto', '--no-send', '--title', slug],
                   capture_output=True, text=True, timeout=3600)
        if r.returncode:
            raise RuntimeError(f'HeyGen falhou na cena {c["n"]}: {r.stderr[-400:] or r.stdout[-400:]}')
        res = json.load(open(d / f'apresentador/bruto/{slug}/resultado.json'))
        Path(res['file']).rename(out)
        custos[str(c['n'])] = res.get('cost_api_credits')
        json.dump(custos, open(custo_p, 'w'), indent=1)
        log(f'  cena {c["n"]}: {dur(out):.1f}s · custo {res.get("cost_api_credits")} créditos · restam {res.get("quota_after")}')
    return custos


def gerar(plano_path, saida, final_nome='final.mp4', musica=None, log=print):
    p = json.load(open(plano_path))
    m = Montador(p, saida, log)
    m.narrar()
    return m.montar(Path(saida) / final_nome, musica)


if __name__ == '__main__':
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument('plano'); a.add_argument('saida')
    a.add_argument('--final', default='final.mp4'); a.add_argument('--musica')
    x = a.parse_args()
    gerar(x.plano, x.saida, x.final, x.musica)
