# Business OS — Application Shell Architecture

> **Status:** Canonical shell specification  
> **Code:** `static/bos/core/shell.js`, `static/bos/core/shell-nav.js`

## Philosophy

Business OS behaves like an **operating system**. Every module lives inside one shared shell. Navigation stays stable; only content changes.

## Shell Layers

```
Application Shell
├── Workspace Switcher (sidebar top)
├── Sidebar (platform navigation)
├── Top Bar (breadcrumb, search, notifications, user)
├── Command Palette (⌘K)
├── Main Content
├── Context Drawer
├── Bottom Action Bar
└── Status Layer (toasts)
```

## Rules

- Modules **never** implement their own application shell.
- The shell owns navigation, search, notifications, workspace context.
- Drawers are the default detail interaction model.
- Archive over delete; bulk actions in bottom bar.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| ⌘K | Command palette / global search |
| ⌘N | Create picker |
| / | Focus search |
| Esc | Close drawer / palette |
| ⌘S | Save (when editing in drawer) |

## Completion checklist

| Capability | Implementation |
|------------|----------------|
| Workspace switcher | `workspace-switcher.js` — sidebar top, soft switch via `bos:workspace-changed` |
| Sidebar platforms | `shell-nav.js` + `sidebar.html` |
| Top bar | `toolbar.html` — breadcrumb, workspace, search, notifications, user |
| Command palette / ⌘K | `command-palette.js` + workspace API search |
| Create picker / ⌘N | `create-picker.js` + FAB in `quick-actions.js` |
| Context drawer | `object-detail.js`, platform drawers |
| Bottom action bar | `selection.js` + `renderActionBar()` |
| Breadcrumbs | `nav.js` + `bos:object-opened` events |
| Keyboard shortcuts | `shell.js` |

## Related

- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
- [DOMAIN_MODEL.md](./DOMAIN_MODEL.md)
- [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md)
