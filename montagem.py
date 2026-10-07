"""Montagem — faz no ffmpeg o que o vídeo de referência fazia à mão no CapCut.

Por cena: o clipe é ajustado ao tempo da narração (acelera/desacelera até ±25%, depois
corta ou congela o último quadro). Entre cenas: transição suave (xfade). No filme:
fade do preto no início e para o preto no fim, som ambiente dos clipes a ~16%,
música baixa com "ducking" (abaixa sozinha quando a voz fala) e fade out no final.
"""
import json, subprocess
from pathlib import Path

X = 0.7            # duração da transição entre cenas (s)
FOLGA = 0.9        # silêncio depois de cada fala (s)
AMBIENTE = 0.16    # volume do som dos clipes (ele usava 15–18)
MUSICA = 0.30      # volume da música antes do ducking
RES = {'16:9': (1280, 720), '9:16': (720, 1280), '1:1': (1080, 1080)}


def dur(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def tem_audio(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries',
                        'stream=index', '-of', 'json', str(p)], capture_output=True, text=True)
    return bool(json.loads(r.stdout or '{}').get('streams'))


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError('ffmpeg: ' + r.stderr[-600:])


def montar(d, numeros, formato, musica, saida, log):
    W, H = RES.get(formato, RES['16:9'])
    T = d / 'tmp'
    faltam = [n for n in numeros if not (d / f'videos/{n:03d}.mp4').exists()
              or not (d / f'narracao/{n:03d}.wav').exists()]
    if faltam:
        raise SystemExit(f'montar: faltam vídeo/narração das cenas {faltam}')

    # 1. cada cena no tempo da sua fala
    cenas, duracoes, falas = [], [], []
    for i, n in enumerate(numeros):
        v, a = d / f'videos/{n:03d}.mp4', d / f'narracao/{n:03d}.wav'
        dv, da = dur(v), dur(a)
        alvo = da + FOLGA + (X if i < len(numeros) - 1 else 1.5)
        fator = max(0.8, min(1.25, alvo / dv))       # setpts: >1 desacelera
        out = T / f'cena-{n:03d}.mp4'
        amb = ('[0:a]' if tem_audio(v) else '[1:a]')
        sh(['ffmpeg', '-loglevel', 'error', '-i', str(v), '-f', 'lavfi',
            '-i', 'anullsrc=r=48000:cl=stereo', '-filter_complex',
            f'[0:v]setpts={fator:.4f}*PTS,scale={W}:{H}:force_original_aspect_ratio=increase,'
            f'crop={W}:{H},fps=30,tpad=stop_mode=clone:stop_duration=10,trim=0:{alvo:.3f},'
            f'setpts=PTS-STARTPTS,format=yuv420p[v];'
            f'{amb}atempo={1 / fator:.4f},apad,atrim=0:{alvo:.3f},asetpts=PTS-STARTPTS,'
            f'aformat=sample_rates=48000:channel_layouts=stereo[a]',
            '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '18', '-c:a', 'aac',
            '-y', str(out)])
        cenas.append(out); duracoes.append(alvo); falas.append(a)
        log(f'  cena {n:03d}: fala {da:.1f}s · clipe {dv:.1f}s → {alvo:.1f}s (x{fator:.2f})')

    # 2. filme: xfade nas imagens, falas posicionadas no início de cada cena
    inicio, ini = [], 0.0
    for i, dd in enumerate(duracoes):
        inicio.append(ini)
        ini += dd - X
    total = sum(duracoes) - X * (len(duracoes) - 1)

    ins, fc = [], []
    for c in cenas:
        ins += ['-i', str(c)]
    for f in falas:
        ins += ['-i', str(f)]
    tem_musica = bool(musica) and Path(musica).exists()
    if tem_musica:
        voltas = int(total // max(dur(musica), 1))   # finito: -stream_loop -1 nunca fecha o grafo
        ins += ['-stream_loop', str(voltas), '-i', str(musica)]
    n = len(cenas)

    ult = '[0:v]'
    for i in range(1, n):
        off = inicio[i]
        fc.append(f'{ult}[{i}:v]xfade=transition=fade:duration={X}:offset={off:.3f}[vx{i}]')
        ult = f'[vx{i}]'
    fc.append(f'{ult}fade=t=in:st=0:d=1.2,fade=t=out:st={total - 1.6:.3f}:d=1.6[vout]')

    for i in range(n):   # ambiente de cada cena, no lugar dela
        fc.append(f'[{i}:a]volume={AMBIENTE},adelay={int(inicio[i] * 1000)}:all=1[amb{i}]')
    for i in range(n):   # fala começa meio segundo depois da transição
        ms = int((inicio[i] + (X / 2 if i else 0.4)) * 1000)
        fc.append(f'[{n + i}:a]aformat=sample_rates=48000:channel_layouts=stereo,'
                  f'adelay={ms}:all=1[f{i}]')
    fc.append(''.join(f'[f{i}]' for i in range(n)) +
              f'amix=inputs={n}:normalize=0,apad,atrim=0:{total:.3f}[voz]')
    fc.append(''.join(f'[amb{i}]' for i in range(n)) +
              f'amix=inputs={n}:normalize=0,apad,atrim=0:{total:.3f}[ambt]')
    if tem_musica:
        fc.append('[voz]asplit=2[voz1][vozsc]')
        fc.append(f'[{2 * n}:a]aformat=sample_rates=48000:channel_layouts=stereo,'
                  f'atrim=0:{total:.3f},volume={MUSICA},afade=t=in:d=1.5,'
                  f'afade=t=out:st={total - 2.5:.3f}:d=2.5[mus]')
        fc.append('[mus][vozsc]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=600[musd]')
        fc.append('[voz1][ambt][musd]amix=inputs=3:normalize=0,alimiter=limit=0.95[aout]')
    else:
        fc.append('[voz][ambt]amix=inputs=2:normalize=0,alimiter=limit=0.95[aout]')

    # Imagem e som em passadas separadas: no mesmo grafo o xfade (que só lê a cena N no
    # offset dela) e o adelay do ambiente da mesma cena travam a fila do ffmpeg no fim.
    fv = [l for l in fc if 'xfade' in l or '[vout]' in l]
    fa = [l for l in fc if l not in fv]
    (T / 'filtro-video.txt').write_text(';\n'.join(fv))
    (T / 'filtro-audio.txt').write_text(';\n'.join(fa))
    sh(['ffmpeg', '-loglevel', 'error', *ins[:2 * n], '-filter_complex_script',
        str(T / 'filtro-video.txt'), '-map', '[vout]', '-t', f'{total:.3f}',
        '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-pix_fmt', 'yuv420p',
        '-y', str(T / 'imagem.mp4')])
    sh(['ffmpeg', '-loglevel', 'error', *ins, '-filter_complex_script',
        str(T / 'filtro-audio.txt'), '-map', '[aout]', '-t', f'{total:.3f}',
        '-c:a', 'aac', '-b:a', '192k', '-y', str(T / 'som.m4a')])
    sh(['ffmpeg', '-loglevel', 'error', '-i', str(T / 'imagem.mp4'), '-i', str(T / 'som.m4a'),
        '-map', '0:v', '-map', '1:a', '-c', 'copy', '-shortest', '-movflags', '+faststart',
        '-y', str(saida)])
    log(f'  filme: {dur(saida):.1f}s · {saida.stat().st_size / 1048576:.1f} MB')
    return saida
