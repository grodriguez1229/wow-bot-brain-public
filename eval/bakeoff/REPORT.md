# Self-Improvement Cycle 2 — Model Bake-off + Compound Edit (2026-06-13)

Run unattended overnight on branch `optimizer-run`. Nothing merged to master; nothing
touched the live brain (`:5000`). All work is local/private per the standing privacy rule.

## TL;DR
- Found and fixed a **substrate bug** that had been silently flattening every prior run.
- Ran a **3-model bake-off** — no model beats qwen3.5:9b past the noise margin.
- Ran the **compound prompt/template edit** — it nominally *regressed*; gate reverted it.
- **Conclusion: the ~2.2 ceiling is architectural, not model- or wording-bound.**

## The substrate bug (the real story of this cycle)
The sim scenes referenced invented character names (Brumdar/Sylvara/Gus) that don't exist
in the game `characters` table. Combined with the game DB being down and pymysql missing
the `cryptography` package, the brain silently fell back to giving **every bot the same
L1 Human "Adventurer" identity**. So every prior eval compared identical generic bots —
a large hidden contributor to the repetitive filler and the ~2.0 ceiling.

Fixes:
- Started the `ac-database` container directly (the HA `StartWowServer` intent does not
  start containers).
- Pinned `cryptography==49.0.0` in `requirements.txt` (caching_sha2_password auth).
- Repointed `sim/scenes.py` to **real Alliance characters**: Geysse (L16 Dwarf Rogue),
  Lynea (L15 Night Elf Warrior), player "Gus".

## 3-point attribution
| Stage | Eval mean | Δ |
|---|---|---|
| Historical baseline (qwen, L1-Human fallback) | 1.975 | — |
| qwen with **real Alliance identities** (substrate fix) | **2.163** | **+0.188** |
| Best alternative model (mistral-small:22b) | 2.288 | +0.125 (sub-margin) |
| Compound prompt/template edit (qwen) | 1.975 | −0.188 (REVERTED) |

The only thing that actually moved the needle was **fixing the substrate** (+0.188).
That gain is real but still below the 0.5 promotion margin, and it's a one-time
correctness fix rather than an optimization — so it's kept as substrate, not "promoted."

## Phase A — model bake-off (`rows.jsonl`)
| model | eval mean | s/scene | notes |
|---|---|---|---|
| qwen3.5:9b (incumbent M*) | 2.163 | 4.15 | balanced |
| gemma4:latest | 2.263 | 4.09 | wittier, but **7 emoji/anachronism gate fails** |
| mistral-small:22b | 2.288 | 12.69 | cleanest (0 gate fails), best geography, **3× slower** |

No model clears qwen by the 0.5 noise margin. **M\* stays qwen3.5:9b.** The quality
ceiling is structural, not model-bound.

## Phase B — compound edit (`phaseB.json`)
Evaluated as one unit on qwen: diversified `pick_goal_for_level` ≤10/≤20 pools,
de-clichéd 3 typing styles, a specific SAY-tick prompt, and the CHAT "engage their LAST
message" rule. **Scored 1.975 vs 2.163 baseline (gain −0.188)** → gate REVERT on the eval
clause. All 16 eval-scene gates passed (0 new lore failures). Source reverted.

**Why it backfired:** the diversified ≤20 goal pool I wrote was dungeon/LFG-heavy
("find a group for Deadmines", "run Wailing Caverns for the quest gear", "find a guild to
run dungeons with"). Bots translated those goals directly into **LFG classified-ad spam**
("L16 Rogue LFG Deadmines need tank/healer"), which made the no-player ambient scenes
*worse*. Diversifying the goal *strings* is not the same as diversifying *behaviour*.

What did look better: **player-present SAY scenes** (orgrimmar-banter-s13 ≈ 3.0,
s12 ≈ 2.8) — there the CHAT engagement rule visibly helped (real back-and-forth, a
callback joke, well-motivated emotes). The dead weight is the **no-player ambient
scenes** (~1.5): with no human present, bots just broadcast WTB/LFG ads at each other
instead of conversing.

## Recommendation for the next cycle
Stop tuning wording inside the whitelist — it can't break ~2.2. The bottleneck is
**architectural**: bots have no shared scene memory and ticks are stateless, so with no
player they broadcast classified ads instead of holding a conversation. The high-value
move is a **stateful-tick / shared-scene-memory** change (outside the current prompt
whitelist), and separately fixing the **faction/geography coherence** (Alliance bots kept
asking for Mankrik's wife, a Horde Barrens quest).

## State left for review
- Branch `optimizer-run`, unmerged. Source files reverted to baseline (compound edit gone).
- Kept artifacts: `eval/bakeoff/rows.jsonl`, `eval/bakeoff/phaseB.json`, this report,
  the `sim/scenes.py` real-identity fix, `cryptography` pin, and the bake-off harness.
- `ac-database` container left UP. worldserver/authserver down. Live brain untouched.
