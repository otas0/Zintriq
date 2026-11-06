## Summary

<!-- 1–3 bullets: why this change exists -->

## Type

- [ ] Typed MVP (`apps/*` / `packages/*`)
- [ ] Electron/Flask host (`desktop/` / `app.py`)
- [ ] HAL board pack (`fixtures/boards/`)
- [ ] Docs / CI only

## HAL board checklist (if applicable)

CI job **HAL boards / board.schema.json** auto-validates YAML on `fixtures/boards/**` changes.

- [ ] New/updated YAML matches `fixtures/boards/board.schema.json` (`mcuFamily` ∈ esp32|stm32|rp2040)
- [ ] `pnpm --filter @zintriq/hal-registry test` passes (local)
- [ ] `curl -s http://127.0.0.1:4317/boards` shows the board (paste text or screenshot)
- [ ] `POST /build` with the new `boardId` is not `BOARD_NOT_FOUND`

## Typed MVP checklist

- [ ] No proactive AI / auto-build-on-save / translation feature stubs
- [ ] Desktop talks only to core-service HTTP API
- [ ] `pnpm lint && pnpm typecheck && pnpm test && pnpm build` green locally when touching typed code

## Test plan

- [ ]
