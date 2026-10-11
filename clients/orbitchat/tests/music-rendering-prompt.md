Generate a Markdown **piano music rendering stress test** for TOPIC.

Requirements:
1. Output only Markdown, with short section labels and ABC notation in fenced code blocks labeled `abc`.
2. Include at least six **valid, self-contained** tunes. Each tune starts with `X:`, `T:`, `M:`, `L:`, `Q:`, and `K:` headers and ends with a complete final bar (`|]`).
3. Mix easy and intermediate piano passages: a single-staff melody, a two-hand score with treble and bass clefs, block chords, broken chords, rests, accidentals, ties, and at least two key signatures or meters.
4. Include a two-hand example that uses separate `V:` voices for right and left hands. If you use `%%score` or `%%staves`, keep treble and bass on separate staves; do not group them inside the same parentheses.
5. Include one multi-tune `abc` block with two tunes separated by a blank line immediately before the second `X:` header. Keep all other ABC blocks free of blank lines after `K:`.
6. Make every *valid* bar add up to its declared meter and `L:` value. Add a one-sentence note under each valid score stating what to check in the sheet music, playback, or MIDI export.
7. Add an **Invalid Examples** section with three separate `abc` blocks: one missing `K:`, one with an incomplete measure, and one with malformed notation. Clearly label them as negative tests, separate from the valid tunes.
8. Do not claim to have heard the audio or verified rendering. Generate source material for someone to inspect in the Orbit client.

Topic: TOPIC

Replace TOPIC with a musical idea such as a lullaby, a blues phrase, or a film-score motif.
