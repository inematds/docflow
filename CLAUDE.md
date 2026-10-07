# CLAUDE.md — docflow

Tema → documentário curto narrado → YouTube. Plano, tabela dos 3 caminhos e estado dos motores: README.md.

- Saída sempre em `~/projetos/output/docflow/<slug>/`; o repo só tem código e temas.
- Motor `flow` = Google Flow pelo navegador (conta inematds). Login é do Nei (VNC :5900), nunca do agente.
- API Agnes autorizada (07/10/2026). Kie/Gemini/outras APIs: só com autorização explícita.
- Publicar no YouTube só com `publicar --enviar` depois de o Nei aprovar vídeo e thumb.
- Commits: autor `inematds <inematds@gmail.com>`.

## Self-learning

When I correct you, or you catch yourself making a mistake: before continuing, add the lesson as a one-line rule under ## Lessons, so it never happens again.

## Lessons

- ffmpeg chamado por script: sempre `stdin=DEVNULL` e NUNCA vídeo com xfade + áudio com adelay das mesmas entradas num só filter_complex (trava no fim); renderizar imagem e som separados e juntar com `-c copy`. Testar com `timeout -s KILL` (o SIGTERM o ffmpeg ignora). (07/10/2026)
