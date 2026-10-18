# Prompt 2 D5 — Lighthouse (mobile)

Run with Chrome for Testing + Lighthouse 12.8, form-factor mobile, simulated throttling. Local Flask on `127.0.0.1`.

| Page | Performance | Accessibility | Best Practices | SEO | LCP | CLS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Home `/?stay=1&hl=en` | 100 | 100 | 100 | 100 | 1.1 s | 0 |
| Download `/download?hl=en` | 100 | 100 | 100 | 100 | 1.1 s | 0 |
| Pricing `/pricing?hl=en` | 100 | 100 | 100 | 100 | 1.1 s | 0 |

Targets: Performance ≥ 90, Accessibility = 100, Best Practices ≥ 95, SEO = 100, LCP ≤ 2.5 s, CLS ≤ 0.1.

Notes:
- Marketing pages use lean CSS (`tokens-marketing.css` + `public.css`), gzip for text assets, deferred chrome JS.
- Marketing skips the Inter variable font download on first paint (system stack); auth/product shell can still load Inter via `tokens.css`.
