# FALHAS — docflow

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-10-07 | Destaque "−13,6%" sumiu inteiro da tela: o drawtext lê "%" como código de expansão | `expansion=none` em todo drawtext (e hífen no lugar do − tipográfico) | infra |
| 2026-10-07 | drawtext do ffmpeg 6.1 cortava as últimas letras de texto com acento ("Pacífic", "Grátis" sem ponto no CTA) | completar o texto com 1 espaço por byte extra (`pad()` em motores/reais.py) | infra |
| 2026-10-07 | Clipe 6 do Agnes (ti2vid) derivou para porto barroco com cúpula e caravelas | prompt de vídeo com câmera quase parada + "keep the same buildings"; refazer só o clipe | prompt |
| 2026-10-07 | Montagem final travava para sempre (vídeo+áudio no mesmo filter_complex: xfade lê a cena N só no offset e o adelay do ambiente da mesma cena trava a fila) | duas passadas (imagem, som) + mux com `-c copy` | infra |
| 2026-10-07 | ffmpeg em segundo plano parava esperando o teclado | `stdin=subprocess.DEVNULL` em todo ffmpeg | infra |
