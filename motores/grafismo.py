"""Grafismos animados do estilo "historia" (paleta fixa azul-escura, traço plano).

Cada função desenha quadro a quadro com PIL e manda direto para o ffmpeg (rawvideo),
sem HTML nem navegador: termômetro, contador, capítulo, cartões "no seu bolso",
linha do tempo e citação. Todas aceitam (saida, segundos, W, H).
"""
import math, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTES = Path.home() / '.local/share/fonts'
F_BLACK = str(FONTES / 'Montserrat-Black.ttf')
F_BOLD = str(FONTES / 'Montserrat-ExtraBold.ttf')
F_EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'
FPS = 30

FUNDO = (11, 29, 62)
FUNDO2 = (19, 46, 92)
QUENTE = (255, 98, 44)
AMARELO = (255, 201, 60)
FRIO = (76, 195, 255)
BRANCO = (245, 247, 250)
CINZA = (150, 165, 190)


def fonte(tam, black=True):
    return ImageFont.truetype(F_BLACK if black else F_BOLD, tam)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = max(0.0, min(1.0, t))
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


_fundo_cache = {}


def fundo(W, H):
    """Azul-escuro com vinheta e grade sutil (fixo; o movimento vem da grade deslizando)."""
    if (W, H) not in _fundo_cache:
        im = Image.new('RGB', (W, H), FUNDO)
        glow = Image.new('L', (W, H), 0)
        ImageDraw.Draw(glow).ellipse((W * 0.15, H * 0.05, W * 0.85, H * 0.95), fill=255)
        glow = glow.filter(ImageFilter.GaussianBlur(W // 6))
        im.paste(Image.new('RGB', (W, H), FUNDO2), (0, 0), glow)
        _fundo_cache[(W, H)] = im
    return _fundo_cache[(W, H)].copy()


def grade(d, W, H, f):
    passo = W // 16
    off = (f * 0.6) % passo
    for x in range(-passo, W + passo, passo):
        d.line((x + off, 0, x + off, H), fill=(28, 52, 96), width=1)
    for y in range(0, H + passo, passo):
        d.line((0, y + off * 0.5, W, y + off * 0.5), fill=(28, 52, 96), width=1)


def num_br(v, casas=0):
    s = f'{v:,.{casas}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


class Saida:
    def __init__(self, path, W, H):
        self.p = subprocess.Popen(
            ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
             '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
             '-pix_fmt', 'yuv420p', str(path)], stdin=subprocess.PIPE)

    def put(self, im):
        self.p.stdin.write(im.tobytes())

    def fim(self):
        self.p.stdin.close()
        self.p.wait()


def texto_c(d, xy, txt, f, cor, **kw):
    d.text(xy, txt, font=f, fill=cor, anchor='mm', **kw)


def rotulo_rodape(d, W, H, txt, f_alpha=1.0):
    if not txt:
        return
    f = fonte(int(H * 0.028), black=False)
    d.text((W - int(W * 0.03), H - int(H * 0.04)), txt, font=f, fill=CINZA, anchor='rs')


# ---------------------------------------------------------------- termômetro
def termometro(saida, segundos, W, H, valor, frac=0.85, rotulo='', fonte_txt=''):
    """Termômetro enchendo + número contando até `valor` (ex.: 3.2 -> "+3,2 °C")."""
    out, n = Saida(saida, W, H), int(segundos * FPS)
    cx, topo, base = int(W * 0.32), int(H * 0.16), int(H * 0.80)
    larg, bulbo = int(W * 0.045), int(W * 0.06)
    for f in range(n):
        t = ease(f / (FPS * 1.8))
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        d.rounded_rectangle((cx - larg, topo, cx + larg, base), larg, fill=(30, 50, 90), outline=BRANCO, width=6)
        d.ellipse((cx - bulbo, base - bulbo // 2, cx + bulbo, base + bulbo * 3 // 2), fill=QUENTE, outline=BRANCO, width=6)
        nivel = base - int((base - topo - larg) * frac * t)
        cor = tuple(int(FRIO[i] + (QUENTE[i] - FRIO[i]) * t) for i in range(3))
        d.rounded_rectangle((cx - larg + 14, nivel, cx + larg - 14, base + 10), larg - 14, fill=cor)
        for k in range(1, 9):
            y = base - (base - topo) * k // 9
            d.line((cx + larg + 10, y, cx + larg + 40, y), fill=BRANCO, width=4)
        v = valor * t
        texto_c(d, (int(W * 0.66), int(H * 0.42)), f'+{num_br(v, 1)} °C', fonte(int(H * 0.17)), QUENTE)
        if rotulo:
            texto_c(d, (int(W * 0.66), int(H * 0.62)), rotulo, fonte(int(H * 0.045), False), BRANCO)
        rotulo_rodape(d, W, H, fonte_txt)
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- contador
def contador(saida, segundos, W, H, valor, casas=0, prefixo='', sufixo='', rotulo='', antes='', cor=AMARELO, fonte_txt='', milhar=True):
    """Número grande contando de 0 até `valor`, com rótulo e linha "antes" opcional."""
    out, n = Saida(saida, W, H), int(segundos * FPS)
    for f in range(n):
        t = ease(f / (FPS * 1.6))
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        v = num_br(valor * t, casas) if milhar else f'{valor * t:.{casas}f}'
        s = prefixo + v + sufixo
        esc = 0.85 + 0.15 * ease_back(f / (FPS * 0.6))
        texto_c(d, (W // 2, int(H * 0.44)), s, fonte(int(H * 0.22 * esc)), cor)
        if rotulo:
            texto_c(d, (W // 2, int(H * 0.66)), rotulo, fonte(int(H * 0.05), False), BRANCO)
        if antes and f > FPS * 0.8:
            a = ease((f - FPS * 0.8) / FPS)
            texto_c(d, (W // 2, int(H * 0.76 + 30 * (1 - a))), antes, fonte(int(H * 0.04), False), CINZA)
        rotulo_rodape(d, W, H, fonte_txt)
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- capítulo
def capitulo(saida, segundos, W, H, numero, titulo):
    out, n = Saida(saida, W, H), int(segundos * FPS)
    for f in range(n):
        t = ease(f / (FPS * 0.9))
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        r = int(H * 0.09 * ease_back(f / (FPS * 0.7)))
        d.ellipse((W // 2 - r, int(H * 0.33) - r, W // 2 + r, int(H * 0.33) + r), fill=QUENTE)
        texto_c(d, (W // 2, int(H * 0.33)), str(numero), fonte(int(r * 1.2) or 1), BRANCO)
        x = int(W // 2 + (1 - t) * W * 0.3)
        texto_c(d, (x, int(H * 0.58)), titulo, fonte(int(H * 0.075)), BRANCO)
        d.rectangle((W // 2 - int(W * 0.12 * t), int(H * 0.67), W // 2 + int(W * 0.12 * t), int(H * 0.675)), fill=AMARELO)
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- no seu bolso
def bolso(saida, segundos, W, H, itens, titulo='NO SEU BOLSO'):
    """itens = [(emoji, texto)]; cartões entram um a um."""
    out, n = Saida(saida, W, H), int(segundos * FPS)
    fe = ImageFont.truetype(F_EMOJI, 109)
    emojis = {}
    for e, _ in itens:
        ei = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(ei).text((80, 80), e, font=fe, embedded_color=True, anchor='mm')
        emojis[e] = ei.resize((int(H * 0.13), int(H * 0.13)))
    k = len(itens)
    cw = int(W * 0.8 / k)
    for f in range(n):
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        texto_c(d, (W // 2, int(H * 0.17)), titulo, fonte(int(H * 0.07)), AMARELO)
        for i, (e, txt) in enumerate(itens):
            a = ease_back((f - FPS * (0.3 + 0.45 * i)) / (FPS * 0.5))
            if a <= 0:
                continue
            x0 = int(W * 0.1 + i * cw + cw * 0.06)
            y0 = int(H * 0.30 + (1 - a) * H * 0.15)
            d.rounded_rectangle((x0, y0, x0 + int(cw * 0.88), y0 + int(H * 0.52)), 28, fill=(24, 44, 84), outline=QUENTE, width=5)
            ei = emojis[e]
            im.paste(ei, (x0 + int(cw * 0.44) - ei.width // 2, y0 + int(H * 0.05)), ei)
            linhas, cur = [], ''
            ft = fonte(int(H * 0.036), False)
            for w in txt.split():
                if d.textlength((cur + ' ' + w).strip(), font=ft) > cw * 0.78:
                    linhas.append(cur); cur = w
                else:
                    cur = (cur + ' ' + w).strip()
            linhas.append(cur)
            for j, l in enumerate(linhas):
                texto_c(d, (x0 + int(cw * 0.44), y0 + int(H * 0.27) + j * int(H * 0.05)), l, ft, BRANCO)
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- linha do tempo
def linha_tempo(saida, segundos, W, H, pontos, titulo='', unidade='', realce=-1, fonte_txt=''):
    """pontos = [(rotulo, valor)]; barras sobem sobre uma linha do tempo, o realce fica quente."""
    out, n = Saida(saida, W, H), int(segundos * FPS)
    vmax = max(v for _, v in pontos)
    k = len(pontos)
    base, alt = int(H * 0.80), int(H * 0.50)
    for f in range(n):
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        if titulo:
            texto_c(d, (W // 2, int(H * 0.12)), titulo, fonte(int(H * 0.06)), BRANCO)
        d.line((int(W * 0.08), base, int(W * 0.92), base), fill=BRANCO, width=5)
        for i, (rot, v) in enumerate(pontos):
            a = ease((f - FPS * (0.2 + 0.35 * i)) / (FPS * 0.8))
            x = int(W * 0.08 + (i + 0.5) * W * 0.84 / k)
            bw = int(W * 0.84 / k * 0.42)
            hh = int(alt * v / vmax * a)
            cor = QUENTE if i == (realce % k) else FRIO
            if hh > 0:
                d.rounded_rectangle((x - bw // 2, base - hh, x + bw // 2, base), 10, fill=cor)
                texto_c(d, (x, base - hh - int(H * 0.04)), num_br(v * a, 2) + unidade, fonte(int(H * 0.042)), cor)
            texto_c(d, (x, base + int(H * 0.05)), rot, fonte(int(H * 0.036), False), BRANCO)
        rotulo_rodape(d, W, H, fonte_txt)
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- citação
def citacao(saida, segundos, W, H, texto, autor):
    """Citação digitada letra a letra, aspas grandes, autor embaixo."""
    out, n = Saida(saida, W, H), int(segundos * FPS)
    ft = fonte(int(H * 0.058), False)
    d0 = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    linhas, cur = [], ''
    for w in texto.split():
        if d0.textlength((cur + ' ' + w).strip(), font=ft) > W * 0.72:
            linhas.append(cur); cur = w
        else:
            cur = (cur + ' ' + w).strip()
    linhas.append(cur)
    total = sum(len(l) for l in linhas)
    for f in range(n):
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        d.text((int(W * 0.1), int(H * 0.12)), '“', font=fonte(int(H * 0.3)), fill=QUENTE)
        mostra = int(total * min(1, f / (FPS * max(1.2, segundos * 0.55))))
        y = int(H * 0.5 - len(linhas) * H * 0.04)
        for l in linhas:
            parte = l[:max(0, mostra)]
            mostra -= len(l)
            d.text((int(W * 0.16), y), parte, font=ft, fill=BRANCO)
            y += int(H * 0.085)
        if f > FPS * 1.0:
            a = ease((f - FPS) / FPS)
            d.text((int(W * 0.16), y + int(H * 0.04)), '— ' + autor, font=fonte(int(H * 0.04)), fill=tuple(int(c * a) for c in AMARELO))
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- oceano (corte do Pacífico)
def oceano(saida, segundos, W, H, de=0.0, ate=1.0, esquerda='ÁSIA', direita='AMÉRICA DO SUL'):
    """Corte do Pacífico na linha do Equador. estado 0 = normal (vento forte para oeste, água
    quente acumulada na Ásia); 1 = El Niño (vento fraco, água quente espalhada até a América).
    Anima de `de` até `ate`."""
    out, n = Saida(saida, W, H), int(segundos * FPS)
    sup, fundo_y = int(H * 0.42), int(H * 0.86)
    x0, x1 = int(W * 0.06), int(W * 0.94)
    fl = fonte(int(H * 0.04))
    for f in range(n):
        e = de + (ate - de) * ease((f - FPS * 0.5) / max(1, n - FPS * 1.5))
        im = fundo(W, H); d = ImageDraw.Draw(im)
        # água fria
        d.rectangle((x0, sup, x1, fundo_y), fill=(24, 92, 170))
        # camada quente: espessa à esquerda no normal, plana e longa no El Niño
        pts = []
        for i in range(61):
            x = x0 + (x1 - x0) * i / 60
            u = i / 60
            normal = 0.30 * (1 - u) ** 1.6 + 0.02
            nino = 0.14 * (1 - 0.25 * u) + 0.03 * math.sin(u * 9 + f * 0.08)
            esp = (normal * (1 - e) + nino * e) * (fundo_y - sup)
            pts.append((x, sup + esp))
        poly = [(x0, sup)] + pts + [(x1, sup)]
        d.polygon(poly, fill=QUENTE)
        d.line(pts, fill=AMARELO, width=4)
        # termoclina rotulada
        d.line((x0, fundo_y, x1, fundo_y), fill=BRANCO, width=4)
        texto_c(d, (int(W * 0.12), int(H * 0.93)), esquerda, fl, BRANCO)
        texto_c(d, (int(W * 0.86), int(H * 0.93)), direita, fl, BRANCO)
        # vento: setas para a esquerda, fortes no normal, somem no El Niño
        forca = 1 - e
        for k in range(5):
            y = int(H * 0.16 + k * H * 0.045)
            desloc = (f * (6 + 10 * forca) + k * 140) % (W * 0.9)
            xa = int(x1 - desloc)
            comp = int(W * 0.12 * (0.25 + forca))
            cor = tuple(int(c * (0.35 + 0.65 * forca)) for c in BRANCO)
            d.line((xa, y, xa + comp, y), fill=cor, width=6)
            d.polygon([(xa - 18, y), (xa + 4, y - 14), (xa + 4, y + 14)], fill=cor)
        legenda = 'VENTO FORTE' if e < 0.5 else 'VENTO FRACO'
        texto_c(d, (W // 2, int(H * 0.08)), legenda, fonte(int(H * 0.05)), AMARELO if e < 0.5 else QUENTE)
        texto_c(d, (W // 2, int(H * 0.37)), 'ÁGUA QUENTE', fonte(int(H * 0.035)), AMARELO)
        texto_c(d, (W // 2, int(H * 0.80)), 'ÁGUA FRIA DO FUNDO', fonte(int(H * 0.035)), FRIO)
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- CTA
def cta(saida, segundos, W, H, marca='INEMA.CLUB', linha='Cursos, guias e projetos de IA. Grátis.'):
    out, n = Saida(saida, W, H), int(segundos * FPS)
    for f in range(n):
        im = fundo(W, H); d = ImageDraw.Draw(im); grade(d, W, H, f)
        a = ease_back(f / (FPS * 0.7))
        texto_c(d, (W // 2, int(H * 0.45)), marca, fonte(max(1, int(H * 0.16 * a))), (240, 232, 5))
        if f > FPS * 0.6:
            b = ease((f - FPS * 0.6) / FPS)
            texto_c(d, (W // 2, int(H * 0.62 + 20 * (1 - b))), linha, fonte(int(H * 0.045), False),
                    tuple(int(c * b) for c in BRANCO))
        out.put(im)
    out.fim()


# ---------------------------------------------------------------- prova na tela
def prova(saida, segundos, W, H, base, selo=''):
    """Print real (base-limpo.png / base-grifo.png / base.json do navegador.mjs): aproxima do
    trecho e passa o marca-texto amarelo linha a linha; `selo` = domínio da fonte no canto."""
    import json
    limpo = Image.open(f'{base}-limpo.png').convert('RGB')
    grifo = Image.open(f'{base}-grifo.png').convert('RGB')
    rects = json.load(open(f'{base}.json'))
    sw, sh = limpo.size
    k = sw / W                     # print em 2x: os retângulos vêm em px CSS
    rects = [{c: v * k for c, v in r.items()} for r in rects]
    bx0 = min(r['x'] for r in rects); bx1 = max(r['x'] + r['w'] for r in rects)
    by0 = min(r['y'] for r in rects); by1 = max(r['y'] + r['h'] for r in rects)
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    zmax = min(2.6, max(1.15, 0.86 * sw / (bx1 - bx0)))
    out, n = Saida(saida, W, H), int(segundos * FPS)
    total = sum(r['w'] for r in rects) or 1
    fs_ = fonte(int(H * 0.03))
    for f in range(n):
        t_z = ease(f / (FPS * max(2.0, segundos * 0.8)))
        z = 1.0 + (zmax - 1.0) * t_z
        quadro = limpo.copy()
        feito = total * ease((f - FPS * 0.6) / (FPS * 1.4))
        for r in rects:
            if feito <= 0:
                break
            w = min(r['w'], feito)
            box = (int(r['x']), int(r['y']), int(r['x'] + w), int(r['y'] + r['h']))
            quadro.paste(grifo.crop(box), box[:2])
            feito -= r['w']
        vw, vh = sw / z, sh / z
        x0 = min(max(cx - vw / 2, 0), sw - vw) * t_z + (sw - vw) / 2 * (1 - t_z)
        y0 = min(max(cy - vh / 2, 0), sh - vh) * t_z + (sh - vh) / 2 * (1 - t_z)
        im = quadro.crop((int(x0), int(y0), int(x0 + vw), int(y0 + vh))).resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        if selo:
            tw = d.textlength(selo, font=fs_)
            d.rounded_rectangle((int(W * 0.03), int(H * 0.04), int(W * 0.03 + tw + 50), int(H * 0.04 + H * 0.06)), 14, fill=FUNDO)
            d.text((int(W * 0.03 + 25), int(H * 0.07)), selo, font=fs_, fill=AMARELO, anchor='lm')
        out.put(im)
    out.fim()


if __name__ == '__main__':   # amostras rápidas
    import sys
    o = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/grafismo'); o.mkdir(parents=True, exist_ok=True)
    W, H = 1920, 1080
    termometro(o / 'termo.mp4', 4, W, H, 3.2, rotulo='acima do normal no Pacífico', fonte_txt='NOAA CPC · 30/09/2026')
    contador(o / 'cont.mp4', 4, W, H, 12562, rotulo='focos de fogo na Amazônia em setembro', antes='setembro de 2025: 7.211', fonte_txt='INPE')
    capitulo(o / 'cap.mp4', 3, W, H, 1, 'De onde vem esse calor?')
    bolso(o / 'bolso.mp4', 4, W, H, [('🔥', 'Fogo e fumaça no Norte'), ('🌊', 'Enchentes no Sul'), ('🌡️', 'Calor extremo'), ('📱', 'SMS 40199')])
    linha_tempo(o / 'linha.mp4', 5, W, H, [('1982-83', 2.14), ('1997-98', 2.37), ('2015-16', 2.59), ('2023-24', 1.99), ('2026', 2.16)], titulo='Os maiores El Niños', unidade=' °C', fonte_txt='NOAA CPC (ONI)')
    citacao(o / 'cit.mp4', 5, W, H, 'Já é o El Niño mais forte para esta época do ano desde 1950, e ainda está crescendo.', 'NOAA, setembro de 2026')
