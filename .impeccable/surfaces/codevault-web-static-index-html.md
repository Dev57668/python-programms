---
version: 1
slug: "codevault-web-static-index-html"
primary_target: "codevault/web/static/index.html"
related_targets: ["codevault/web/static/style.css","codevault/web/static/app.js"]
---

# Surface brief: CodeVault dashboard

Scope: `codevault/web/static/index.html` (+ style.css, app.js), served by `codevault ui` at `/dashboard`. Mode: Operate.
Audience: developers who keep it open beside the editor and AI tools; first question "is my work safe?".
Constraints: keep every feature (files, history, diffs, restore, pin, git sync, switch project, timeline, recover, integrity, settings, watcher, shortcuts), the JSON API, polling, focus handling and restore safety; AA contrast; 375px phones.
User brief (binding): light theme only, same world as the approved floppy-disk landing page; no pills, few icons, less data per page, nothing generic.

## Direction contract

THESIS: The working side of the floppy-disk world: every snapshot is a disk whose plastic says where it lives, and the Overview answers "is my work safe?" before anything else. Refuses dark mode, pills, icon-on-everything and stat-tile walls.

OWN-WORLD: Desk grey #eceef1 ground, white panels, ink #15171c with 2px ink rules, square corners (4px max). Disk plastics: black in git, blue #1f4fd1 committed not pushed, red #d7263d only on this machine, yellow #f5c400 AI edits. Bricolage Grotesque for UI, JetBrains Mono for paths, hashes and code; Permanent Marker only on disk labels.

STORY: Glance, see whether work is safe, open a file, read its snapshots as a stack of disks, compare, restore.

FIRST VIEWPORT: Ink-ruled sidebar with the disk wordmark linking home, text nav with counts, watcher block. Main: one status sentence with the primary action, the git sync line, then the latest snapshots as a short row of small disks and a short activity list.

FORM: Extension of the floppy-disk world chosen for the landing page. seed:b71bd0397f7fce84. Signature: snapshot state drawn as disk plastic colour wherever a snapshot appears.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
