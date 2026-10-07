"""Motor Agnes: imagem (agnes-image-2.1-flash) + imagem->vídeo (agnes-video-v2.0, ti2vid).

Reaproveita o cliente medido do ~/projetos/videos-agnes/pipeline.py (retry, rate limit 6/min,
polling, download imediato). Regras da API em ~/projetos/agnes-nei/NOTAS-API.md:
prompts em inglês, size em pixels, ~34% de 503 -> retry.
"""
import json, struct, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'projetos/videos-agnes'))
import pipeline as va  # noqa: E402

TAMANHO = {'16:9': (1312, 736), '9:16': (736, 1312), '1:1': (1024, 1024)}
NEGATIVO = 'text, watermark, logo, subtitles, deformed hands, extra limbs, blurry'


def imagem(dest, prompt, w, h, log, tentativas=6):
    body = {'model': 'agnes-image-2.1-flash',
            'prompt': f'{prompt}. No text, no letters, no watermark.',
            'size': f'{w}x{h}', 'extra_body': {'response_format': 'url'}}
    for t in range(1, tentativas + 1):
        try:
            u = va._post(va.IMG_API, body)['data'][0]['url']
            b = urllib.request.urlopen(u, timeout=180).read()
            dest.write_bytes(b)
            iw, ih = struct.unpack('>II', b[16:24])
            log(f'  imagem {dest.stem}: {iw}x{ih}')
            return True
        except Exception as e:
            log(f'    imagem {dest.stem} falha {t}: {str(e)[:90]}')
            time.sleep(5 * t)
    return False


def video(dest, png, prompt, w, h, frames, log, tentativas=5):
    body = {'model': 'agnes-video-v2.0',
            'prompt': f'{prompt}. Cinematic documentary shot, natural motion, stable scene.',
            'negative_prompt': NEGATIVO,
            'num_frames': frames, 'frame_rate': va.FPS, 'seed': va.SEED,
            'width': w, 'height': h,
            'extra_body': {'image': [va.keyframe(str(png))], 'mode': 'ti2vid'}}
    vid = None
    for t in range(1, tentativas + 1):
        try:
            r = va._post(va.VID_API, body, timeout=300)
            vid = r.get('video_id') or r.get('task_id') or r.get('id')
            break
        except urllib.error.HTTPError as e:
            log(f'    vídeo {dest.stem} HTTP {e.code}: {e.read()[:100].decode(errors="ignore")}')
            time.sleep(70 if e.code == 429 else 8 * t)
        except Exception as e:
            log(f'    vídeo {dest.stem} erro: {str(e)[:90]}')
            time.sleep(8 * t)
    if not vid:
        return False
    t0 = time.time()
    while time.time() - t0 < va.ESPERA_VIDEO:
        try:
            r = va._get(va.VID_GET + vid)
            st = r.get('status')
            if st == 'completed':
                u = r.get('url') or (r.get('data') or [{}])[0].get('url') or r.get('video_url')
                dest.write_bytes(urllib.request.urlopen(u, timeout=300).read())
                log(f'  vídeo {dest.stem}: {va.dur(str(dest)):.1f}s')
                return True
            if st == 'failed':
                log(f'  ❌ vídeo {dest.stem} falhou: {json.dumps(r)[:150]}')
                return False
        except Exception:
            pass
        time.sleep(12)
    log(f'  ❌ vídeo {dest.stem}: timeout (video_id={vid}) — rode de novo')
    return False


def gerar(p, t, d, log):
    w, h = TAMANHO.get(t['formato'], TAMANHO['16:9'])
    frames = va.frames_para(t['duracao_cena'])
    cenas = p['cenas']
    # imagens: 3 em paralelo (a API de imagem aguenta; o 503 é tratado por retry)
    def img(c):
        dest = d / f'imagens/{c["n"]:03d}.png'
        return dest.exists() or imagem(dest, c['prompt_imagem'], w, h, log)
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(img, cenas))
    # vídeos: escalonados de 11 em 11 s para não estourar 6 req/min
    def vid(i_c):
        i, c = i_c
        dest = d / f'videos/{c["n"]:03d}.mp4'
        png = d / f'imagens/{c["n"]:03d}.png'
        if dest.exists() or not png.exists():
            return dest.exists()
        time.sleep(11 * i)
        return video(dest, png, c['prompt_video'], w, h, frames, log)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(vid, enumerate(cenas)))
