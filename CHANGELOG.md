# Changelog

## 0.2.0 — 2026-10-07
- Descrição do YouTube com rodapé automático: projeto, APIs usadas por etapa, crédito da música e INEMA.CLUB.
- `docflow descricao --video URL` reaplica a descrição num vídeo publicado (usa `yt-pubx atualizar`).
- `thumb_cena` no tema escolhe a imagem da thumb.
- Guia de uso PT/EN/ES em `guia/` (GitHub Pages) e README trilíngue.

## 0.1.0 — 2026-10-07
- Primeira versão: roteiro (Codex), motor agnes (testado), motor flow (escrito, não validado), montagem ffmpeg, publicar via yt-pubx (dry-run).
- Comando `estatica`: troca o clipe de IA de uma cena pela imagem com zoom lento.
- Montagem em duas passadas (imagem e som) + mux, sem travar; ffmpeg sempre com stdin fechado.
- Vídeo modelo: Egito Antigo em um minuto.
