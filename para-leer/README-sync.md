# google-share — what lives here and why

This folder is **outside both git repos on purpose**. Everything in here is a *planning
document* that Casilda and Felipe edit together and keep live on Google Drive.

Shared Drive folder: https://drive.google.com/drive/folders/1oxKdy2vHEbF5sF6B8FVOM59q6AaIlxkq

## Files

| File | What it is | Who edits |
|---|---|---|
| `PLAN.md` | The plan of record: architecture, decisions, task split | Both |
| `TRACKER.csv` | Daily standup board — import into Google Sheets | Both, daily |
| `felipe-original-plan.txt` | Felipe's original ChatGPT plan, kept for reference | Nobody — archive |

## The rule

- **Planning documents → this folder → Google Drive.** Never in the repo.
- **Code, data, index, summaries → the repo.** Never in Drive.

Reason: Drive gives live co-editing and no merge conflicts, which is what plans need.
Git gives history and reproducibility, which is what code needs. Mixing them means either
merge conflicts on prose or a stale plan nobody reads.

## Working the tracker

`TRACKER.csv` is the source of truth for *what is happening today*. Import it once into
Google Sheets (File → Import → Upload → Replace current sheet), then edit it there. Only
re-export to CSV if you want it back in this folder.

Each of you updates your own rows at the end of your working day — especially the
**Next pickup / notes** column, since the 7-hour timezone gap means the other person reads
it before you're awake. That column is the handover.

## Repos

| Repo | Path | Use |
|---|---|---|
| `ironhack-final-project` | `../ironhack-final-project` | **The team repo. All work goes here.** |
| `project-3-business-case-...` | `../project-3-business-case-...` | Ironhack's original brief + the 122 downloaded transcripts in `data/`. Being migrated. |
