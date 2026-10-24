# P27 scope — 24 October 2026

## Question
Can a small, accessible static portfolio present Furkan Akkaya's computational biology work using attributable repository evidence rather than hand-written achievements?

## One-day implementation
Build a dependency-free Python generator and plain HTML/CSS site for molecular biology, structural bioinformatics and computational drug discovery. Inspect the explicit P01–P30 repository inventory in `data/repositories.json`. Include a repository only when its README has a question, a substantive Results section and a Limitations section, and no planned status. This conservative rule may omit implemented tools that have no results section. Exclude P23 because its README explicitly says the atomistic EGFR profile is not established (model-only method benchmark). Exclude P27 itself to prevent recursive self-inclusion. A negative scientific result is eligible; unfinished work is not presented as complete.

Cards quote the README title, first question paragraph, first numerical prose result containing a complete sentence (skipping tables and captions) (falling back to the first results paragraph) and first limitation paragraph or list item. Preserve qualifying language; do not synthesize scientific claims. Store those excerpts, original README SHA-256, source commit and line ranges. Build offline from that snapshot; refresh explicitly from sibling repositories. Link to the immutable GitHub README and provide a local evidence page. No API-powered runtime, tracking, contact details, thesis ligand information, homelab infrastructure or external fonts.

## Acceptance criteria
1. Audit exactly 30/30 configured repositories; record inclusion/exclusion reasons. Every included card has all four source fields and a pinned README link.
2. Rebuilding twice yields identical output. Every local HTML link and fragment resolves; each external README is authenticated and verified at its pinned commit before delivery. Remote checks are recorded separately from offline CI.
3. Pytest checks provenance, conservative selection (including planned and unfinished fixtures), escaping, determinism, HTML structure, link integrity and the inactive Pages workflow.
4. Layout fits 390 px and 1440 px viewports without horizontal overflow. Keyboard focus is visible; semantic landmarks, a skip link, descriptive links and WCAG AA text contrast are checked. Capture both viewports in Chromium if available; report accessibility checks as bounded checks, not certification.
5. CI builds and tests the snapshot on pushes and pull requests. Provide a Pages workflow with manual dispatch and a hard-false job gate. Do not enable Pages, dispatch deployment, change repository visibility or publish a website.
6. English README documents question, approach, observed results, reproduction and limitations. Commit and push to the existing private main branch as explicitly requested; verify the remote commit and observe hosted CI.

## Limits
README results are source claims, not independent scientific replication. Link existence does not establish scientific validity. Private repository links require access. No claim that the original live/API deployment proposal is implemented. No full WCAG audit, scientific reruns, GitHub API auto-refresh or site publication in this scope.
