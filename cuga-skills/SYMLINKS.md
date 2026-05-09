# Skill symlinks (one source of truth)

The two skills (`hiking_research`, `lead_hunter`) live here:

```
/Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills/
├── hiking_research/
│   ├── SKILL.md
│   └── scripts/hike_tools.py
└── lead_hunter/
    ├── SKILL.md
    └── scripts/lead_tools.py
```

This is the **canonical source**. Edit here. All other locations are
symlinks that resolve back to these folders, so changes propagate
without copying.

---

## Why symlinks (and not copies)

Three different cuga consumers expect skill folders in three different
places, and any of them being stale breaks the agent in confusing ways:

| Consumer | Where it expects skills | Why |
|---|---|---|
| **cuga marketplace UI** (`cuga-skills-ui/main.py`) | `cuga-skills-ui/.cuga/skills/<name>/` | `discover_skills` registers the `load_skill` tool and `<available_skills>` block from this folder |
| **marketplace's host-side `run_command`** | `/tmp/skills/<name>/` | The agent subprocess scripts via `python /tmp/skills/<name>/scripts/...`. This path is hardcoded in [main.py:191](../cuga-skills-ui/main.py#L191) for parity with OpenSandbox's mount path |
| **cuga-agent-skills-branch dev runs** | `cuga-agent-skills-branch/.cuga/skills/<name>/` | Same purpose as the UI's `.cuga/skills/`, but for testing inside the agent repo |

Without symlinks you end up with 3+ copies and edits drift. Been there.

---

## The exact symlinks needed

Run this once:

```bash
SRC=/Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills

# ---------- 1. cuga-skills-ui marketplace ----------
UI=/Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills-ui/.cuga/skills
mkdir -p "$UI"
rm -rf "$UI/hiking_research" "$UI/lead_hunter" "$UI/-lead_hunter"
ln -s "$SRC/hiking_research" "$UI/hiking_research"
ln -s "$SRC/lead_hunter"     "$UI/lead_hunter"

# ---------- 2. /tmp/skills (host run_command's mount) ----------
mkdir -p /tmp/skills
rm -rf /tmp/skills/hiking_research /tmp/skills/lead_hunter
ln -s "$SRC/hiking_research" /tmp/skills/hiking_research
ln -s "$SRC/lead_hunter"     /tmp/skills/lead_hunter

# ---------- 3. cuga-agent-skills-branch dev repo ----------
BRANCH=/Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills
mkdir -p "$BRANCH"
rm -rf "$BRANCH/hiking_research" "$BRANCH/lead_hunter" \
       "$BRANCH/-lead_hunter" "$BRANCH/_hiking_research"
ln -s "$SRC/hiking_research" "$BRANCH/hiking_research"
ln -s "$SRC/lead_hunter"     "$BRANCH/lead_hunter"
```

After running this, every consumer reads the same files on disk.

---

## Verify

```bash
ls -la /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills-ui/.cuga/skills
ls -la /tmp/skills
ls -la /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills
```

Each should show two `lrwxr-xr-x` symlinks pointing at the canonical
`cuga-skills/` folder. Then:

```bash
# Smoke test the scripts (uses the symlinks transitively)
python /tmp/skills/hiking_research/scripts/hike_tools.py geocode 'Lake Placid, NY'
python /tmp/skills/lead_hunter/scripts/lead_tools.py    geocode 'Pleasantville, NY'
```

Both should print a JSON object with `lat`/`lon`/`display_name`.

---

## Caveats

### `/tmp/skills/` evaporates

macOS periodically wipes `/tmp/`, and reboots clear it entirely. If
`run_command` starts returning "No such file or directory", re-run the
`/tmp/skills/` block above. (Symlinks survive being recreated; the
canonical files don't move.)

### Marketplace's "Import" button overwrites symlinks

Clicking **Import** in the marketplace UI runs
[`shutil.copytree`](../cuga-skills-ui/main.py#L148) which deletes the
destination first — your symlink at
`cuga-skills-ui/.cuga/skills/<name>/` will be replaced with a real
copy. After that, edits in `cuga-skills/<name>/` no longer propagate.
Either:

- **Don't click Import** — the symlinks already make the skill visible
  to the marketplace's `discover_skills`. Just restart the server.
- Or **re-run the symlink commands above** after using Import.

A nicer fix would be to teach `import_skill()` to skip the copy when
the destination is already a symlink resolving to the source. Until
then, symlinks-or-Import is an either/or.

### Loader follows symlinks (recent fix)

`Path.rglob` doesn't follow directory symlinks. Cuga's
`_iter_skill_files` was updated to use `os.walk(followlinks=True)`
([loader.py](../../cuga-agent-skills-branch/src/cuga/backend/skills/loader.py)).
Make sure your `cuga` install picks up that change — the marketplace
runs the cuga that's installed via `pip install -e
/path/to/cuga-agent-skills-branch`, so editable installs pick up edits
on the next process restart.

### Stale shadow at `~/.config/agents/skills/`

If you have an old copy at `~/.config/agents/skills/--hiking_researc/`
or similar, project-local symlinks **win** over global, so it's
harmless. But you can clean it up:

```bash
rm -rf ~/.config/agents/skills/--hiking_researc
```

---

## Adding a new skill

1. Create the folder under `cuga-skills/`:
   ```
   cuga-skills/
     <new_skill>/
       SKILL.md          # frontmatter: name, description, optional requirements
       scripts/<file>.py
   ```
2. Symlink it into all three consumer locations:
   ```bash
   SRC=/Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills
   for DEST in \
     /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills-ui/.cuga/skills \
     /tmp/skills \
     /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills
   do
     ln -s "$SRC/<new_skill>" "$DEST/<new_skill>"
   done
   ```
3. Restart the marketplace server. The skill appears in
   `<available_skills>` and `GET /api/skills`.
