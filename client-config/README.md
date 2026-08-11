# client-config

Reference snapshot of the live Nelderim shard's `.def`/`mobtypes.txt`
registration files, as of 2026-08-11. These are the actual files this
pipeline reads and writes against - kept here so the repo documents real
state, not a hypothetical one, and so a fresh setup has something to diff
against.

**These are reference copies, not the live files.** Deploying always means
copying a tool's *output* (from `--out`) into the real client folder -
never copy these committed files directly over a live client.

## What's in here

| File | Role in the resolution order |
|---|---|
| `body.def` | Hard redirect of a living mobile's body id. Checked first - a body listed here never reaches anything below. |
| `Bodyconv.def` | Legacy multi-file anim routing (anim2-5.mul). Already split into four documented sections: **live** (364 entries that actually take effect), **inert - overridden by UOP** (270, kept for when `AnimationFrame*.uop` is ever removed), **inert - shadowed by body.def** (122, listed for completeness even though body.def already redirected the id), **broken** (4, target slot empty/OOB and not in UOP - genuinely invisible, deliberately left rather than silently patched). |
| `mobtypes.txt` | Declares each body's animation TYPE (MONSTER/SEA_MONSTER/ANIMAL/HUMAN/EQUIPMENT), which decides its `anim.idx` stride. Ends with this pipeline's own additions: the kostur (1011, EQUIPMENT) and the Fire Giant Hammer (1974, MONSTER). |
| `Equipconv.def` | Per-bodyType equipment art override (e.g. so human clothing doesn't look wrong on gargoyle bodies). Written by `nelderim_core.add_equipconv_entries()`. |
| `gump.def` | Paperdoll gump substitutions (male base 0xC350 / 50000; female = male+10000). |
| `art.def` | Static/item art substitutions. |

## One fix made while adding these

`mobtypes.txt`'s tail had the Fire Giant Hammer's entry duplicated
verbatim (two identical `1974 MONSTER 0` blocks) - the result of
re-running `vd_inject.py` on the same body after fixing the offset-model
bug earlier in this project, before the tool checked for an existing
declaration. Deduplicated here, and `vd_inject.py` itself was patched to
check before appending, so a re-run on an already-declared body now warns
and skips instead of duplicating.

No other content was changed. The header comments on each file
("Reorganized for readability. SEMANTICS UNCHANGED") predate this repo
and are preserved as-is.
