# Oi Plugins


Bundled plugins for Oi: [`server-status`](./server-status/) and
[`bilibili-anime`](./bilibili-anime/).

Product plugins shipped with the wheel live in
`src/oi/infra/agents/plugins/bundled/`. `oi init` and `oi run`
copy missing ones into `~/.oi/plugins/` and set them **globally off**
in `config.json`. Uninstalled ids are not re-copied.

## Plugin layout

```text
my-plugin/
├── plugin.yaml    # id, version, name, kind, entry; optional ui
├── main.py        # must define setup(ctx)
├── skills/        # skill plugins only: <name>/SKILL.md
└── ui/            # optional prebuilt UI (no npm on install)
    └── dist/
        ├── index.js
        └── manifest.json
```

In `setup(ctx)`, use the API that matches `kind`:

| `kind` | API |
|--------|-----|
| `tool` | `ctx.tool(name, fn, description=..., config_fields=...)` |
| `skill` | `ctx.skills("skills")` — path relative to the plugin root |
| `hook` | `ctx.middleware(instance, priority=...)` |

### Optional icon + UI

```yaml
icon: "🧩"   # emoji or https://… image URL for Admin cards
ui:
  entry: ui/dist/index.js
  manifest: ui/dist/manifest.json
```

### Tool plugins with UI

```yaml
ui:
  entry: ui/dist/index.js
  manifest: ui/dist/manifest.json
```

Prefer JSON tool output:

```json
{
  "oi_ui": { "renderer": "demo_card", "version": 1 },
  "data": { "title": "…", "count": 1 },
  "text": "plain fallback"
}
```

The Dashboard loads `index.js` via `GET /api/plugins/{id}/ui/…`, calls
`setup(host)`, and resolves renderers in chat. Use `host.patchResult` for
interactive L2 updates; streaming still replaces `output` via SSE (L1).
Ship a self-contained ESM; React is provided as `window.__OI_REACT__` /
`__OI_JSX__`.

## Install locally

```bash
oi plugin install ./plugins/server-status --force
oi plugin install ./plugins/bilibili-anime --force
oi plugin list
```

Or pack a ZIP first (include prebuilt `ui/dist/` when present — the server
does **not** run `npm install`).

**Dashboard:** Admin → Plugins → Install. Paste a **direct ZIP download URL**.

After installing a **tool** plugin, open **Tool management** and enable the
tools. **Skill** plugins sync on agent start. **Hook** middleware attaches for
globally enabled plugins. **UI** loads when you open chat.

## Package rules

The ZIP must contain **exactly one** plugin root that includes `plugin.yaml`.

## Quick validity check

```bash
uv run python - <<'PY'
from pathlib import Path
from oi_harness.plugins import PluginRegistry, load_plugin_dir

for name in ("server-status", "bilibili-anime"):
    PluginRegistry.reset()
    p = load_plugin_dir(Path("plugins") / name, install_deps=False)
    print(p.manifest.id, p.manifest.kind, len(p.tools))
PY
```
