---
version: 1
slug: "codevault-web-static-landing-html"
primary_target: "codevault/web/static/landing.html"
related_targets: ["codevault/web/static/landing.css","codevault/web/static/landing.js"]
---

# Surface brief: CodeVault landing page

Scope: `codevault/web/static/landing.html` (+ landing.css, landing.js), served by `codevault ui` at `/`. Mode: Persuade.
Audience: developers and students (and the professor at the demo) deciding what CodeVault is and whether to use it.
Action: open the dashboard, or install from GitHub. Proof: the visitor's own recent snapshots, read live from the local API; real commands. No testimonials, counts or benchmarks exist; demo data is labelled.
User brief (binding): light theme only; must stand out and be clearly about CodeVault, not generic or "AI-looking"; heading first, then scroll through the story of how it works and what it is for. Rejected so far: grey/brass vault boxes, and a dark navy/green page called plain and AI-generated.

## Direction contract

THESIS: Every save is a floppy disk. CodeVault keeps a labelled disk for each save between commits, colour-coded by whether GitHub has it. Refuses the centred headline over feature cards, the dark-with-neon developer page, and cream-and-serif editorial.

OWN-WORLD: Cool desk-grey ground #eceef1, white label stock, ink #15171c. Disk plastics carry meaning: black = in git, blue #1f4fd1 = committed not pushed, red #d7263d = only on this machine, yellow #f5c400 labels for AI edits. Brushed shutter metal #b9bfc8. Bricolage Grotesque 800 for display, Permanent Marker only for what is hand-written on labels, JetBrains Mono for commands and hashes. Disks are drawn in CSS with chamfered corner, shutter and write-protect tab; no icons, no pills.

STORY: Git keeps commits; everything between them is lost unless saved. CodeVault turns each save into a labelled disk, tells you which disks GitHub has, labels AI edits, and puts any disk back. The visitor opens the dashboard or follows three commands.

FIRST VIEWPORT: Top bar with the disk wordmark, chapter links and a black Open dashboard button. Headline "Every save, kept." at about 120px on the left, with the support line and the two actions to its right. Below a 2px ink rule, a live status line, then a full-width row of 6 to 7 overlapping disks labelled in marker with the project's real recent files and times, plastic colour by git state, slightly rotated as if dropped on the desk (approved by the user at the landing checkpoint).

FORM: Floppy disk labels, candidate 6 of 7 on my ordered list. seed:b71bd0397f7fce84. Signature interaction: hovering or focusing a disk slides its shutter open to show the snapshot's hash. Motion: the disks drop onto the desk once on load. Raises: preview before an irreversible step (darkroom); one huge element allowed to cross section seams (vinyl wrap); state shown maturing over time (pickling calendar); data as the picture (ASCII render); one signature border motif, the label's ruled lines (secession page); every item keeps its origin tag (moon bazaar).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
