# FALHAS — docflow

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-10-07 | Clipe 6 do Agnes (ti2vid) derivou para porto barroco com cúpula e caravelas | prompt de vídeo com câmera quase parada + "keep the same buildings"; refazer só o clipe | prompt |
| 2026-10-07 | Montagem final travava para sempre (vídeo+áudio no mesmo filter_complex: xfade lê a cena N só no offset e o adelay do ambiente da mesma cena trava a fila) | duas passadas (imagem, som) + mux com `-c copy` | infra |
| 2026-10-07 | ffmpeg em segundo plano parava esperando o teclado | `stdin=subprocess.DEVNULL` em todo ffmpeg | infra |
