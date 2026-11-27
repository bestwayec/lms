# GRANDEC NEXT 8.0 — Performance & Build Benchmarks

## Vite Production Bundle (`frontend/`)
- **Build tool**: Vite + Rolldown chunking (`npx tsc -b && npm run build`)
- **Measured full build time**: `15.26s` (`task-7646`), zero TypeScript errors, zero `oxlint` warnings across `203` source files.
- **Lazy-loaded route splitting verified**:
  - `EnglishCenter` chunk: `21.54 kB` (`4.49 kB` gzip)
  - `EssayStudio` chunk: `10.91 kB` (`3.44 kB` gzip)
  - `SpeakingPractice` chunk: `9.82 kB` (`3.27 kB` gzip)
  - `SpeakingResult` chunk: `10.00 kB` (`3.36 kB` gzip)
  - `EnglishExamInterface` chunk: `42.95 kB` (`12.71 kB` gzip)
  - `PanelDashboard` chunk: `26.40 kB` (`5.86 kB` gzip)
  - `Tma` chunk: `22.48 kB` (`6.25 kB` gzip)

## Live E2E Network-Idle Settlement (`127.0.0.1:5173` -> Django)
All routes measured cold-to-networkidle under Chromium headless E2E (`task-7716`):
- Fastest student route: `/speaking` (`1461.3 ms`)
- Telegram Mini App shell: `/tma` (`1644.5 ms`)
- Grammar Studio (10 seeded topics): `/grammar` (`1880.2 ms`)
- Admin Panel (+ AI Gateway metrics): `/panel` (`2150.6 ms`)
- Vocabulary Studio: `/vocabulary` (`2388.0 ms`)
- English Learning Center: `/english` (`2824.0 ms`)
- Teacher English Workspace: `/teacher/english` (`3086.3 ms`)
- Writing Studio 3.0: `/essays/studio` (`3921.4 ms`)
