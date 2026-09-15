---
name: CORTEX
description: A criminal network read the way India reads a railway network — junction map, timetable index, platform-grey ground, route colour on the line edges only.
colors:
  platform-terrazzo: "#E4E7E4"
  platform-inset: "#D6DAD6"
  timetable-paper: "#EEF0ED"
  rule-hair: "#C3C8C3"
  rule-strong: "#A7AEA7"
  board-black: "#141613"
  ink-soft: "#4C534C"
  ink-faint: "#606760"
  signal-amber: "#F0A81E"
  amber-deep: "#6B4600"
  amber-wash: "rgba(240, 168, 30, 0.14)"
  signal-red: "#B02821"
  signal-red-soft: "#E39D99"
  signal-red-wash: "rgba(200, 50, 43, 0.09)"
  route-money-blue: "#1F6FB2"
  route-green: "#2E7D4F"
  route-ochre: "#8A5A04"
  route-violet: "#7A4FA3"
  route-teal: "#0F7B8A"
  route-rust: "#B5532A"
typography:
  monument:
    fontFamily: "Archivo Narrow, Archivo, sans-serif"
    fontSize: "3.5rem"
    fontWeight: 700
    lineHeight: 0.92
    letterSpacing: "0.015em"
  sheet:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.2
  lead:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1, \"lnum\" 1"
  label:
    fontFamily: "Archivo Narrow, Archivo, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.08em"
  note:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  all: "0px"
  mark: "9999px"
spacing:
  xs: "4px"
  sm: "6px"
  md: "12px"
  lg: "24px"
  xl: "32px"
components:
  nameplate:
    backgroundColor: "{colors.board-black}"
    textColor: "{colors.signal-amber}"
    typography: "{typography.label}"
    rounded: "{rounded.all}"
    padding: "4px 10px"
  lens-tab:
    textColor: "{colors.ink-soft}"
    typography: "{typography.label}"
    padding: "6px 10px"
  lens-tab-active:
    textColor: "{colors.board-black}"
    typography: "{typography.label}"
    padding: "6px 10px"
  button-outline:
    backgroundColor: "{colors.platform-terrazzo}"
    textColor: "{colors.board-black}"
    typography: "{typography.label}"
    rounded: "{rounded.all}"
    padding: "6px 8px"
  button-outline-hover:
    backgroundColor: "{colors.board-black}"
    textColor: "{colors.platform-terrazzo}"
  button-chip:
    backgroundColor: "{colors.timetable-paper}"
    textColor: "{colors.ink-soft}"
    typography: "{typography.label}"
    rounded: "{rounded.all}"
    padding: "2px 8px"
  status-pill:
    backgroundColor: "transparent"
    textColor: "{colors.board-black}"
    typography: "{typography.note}"
    rounded: "{rounded.all}"
    padding: "0.05rem 0.3rem 0.05rem 0.45rem"
  track-row:
    backgroundColor: "transparent"
    textColor: "{colors.board-black}"
    typography: "{typography.body}"
    rounded: "{rounded.all}"
    padding: "6px 12px"
  track-row-hover:
    backgroundColor: "{colors.timetable-paper}"
  card-note-paper:
    backgroundColor: "{colors.timetable-paper}"
    textColor: "{colors.board-black}"
    rounded: "{rounded.all}"
    padding: "20px"
  input-search:
    backgroundColor: "{colors.timetable-paper}"
    textColor: "{colors.ink-soft}"
    typography: "{typography.note}"
    rounded: "{rounded.all}"
    padding: "4px 10px"
---

# Design System: CORTEX

## Overview

**Creative North Star: "The Junction Map"**

CORTEX is an investigation console drawn as Indian Railways information design. The ground is platform terrazzo, not paper and not a dark console: a speckled grey concourse (#E4E7E4) with two offset dot fields at coprime sizes so no repeat is legible at any zoom. The network is a junction map at the size of the room. The key players are a timetable you scan down the left. One dark strip — the board — is the only black field on the page and the only place signal amber is allowed to burn.

The world's form is borrowed from the station; its vocabulary is not. A departure board was built into this app and then removed, and what survives is the *form*: condensed board caps, tabular figures, split-flap arrival of a state change, timetable rules, docked margins. The words stay the register's own. An alert is Critical / High / Medium / Low. It is never Cancelled, Delayed, Diverted or On Time, because the officer is reading a case record, not a train.

Density is Operate: 13px body, 11px marginalia, 1px hairlines, zero radius, and a type ramp that only ever changes *scale* in presentation mode. Depth is not spent on chrome — every plane separation is a rule, a tonal step, or an inset stripe. The build refuses the glowing dark force-graph console and its KPI tiles: there are no cards floating over the map, no glow, no gradient, no coloured score.

**Key Characteristics:**
- Platform-grey ground; exactly one dark field (the board) per page.
- Route colour rides line edges and marks only; the text field stays achromatic.
- Zero radius everywhere (`--radius: 0px`); a curve only appears as a 45° bend on the map or a 2px severity dot.
- Every state carries a name and a shape, never colour alone.
- Every score sits beside the evidence that produced it, and the figure itself stays ink.

## Colors

Platform materials under tubelight: four greys of terrazzo and rule, one board black that doubles as type, one amber that only burns on the board, one red that only means stop, and six route inks that never touch text.

### Primary
- **Board Black** (`{colors.board-black}`): type at full strength, the nameplate and footer plate ground, section rules that carry weight (`border-b border-ink`), and the filled half of every split bar. Measured 14.6:1 on platform terrazzo.
- **Signal Amber** (`{colors.signal-amber}`): display only. The nameplate's 2px inset underline, the platform-edge stud pattern, board type on black, `::selection`. Never carries text on the light ground.
- **Amber Deep** (`{colors.amber-deep}`): the working amber. Active-lens underline, the "On record" word, the record half of the priority bar, the caret in inputs, the "Presenting" state. Measured 6.74:1.

### Secondary
- **Signal Red** (`{colors.signal-red}`, token `--pencil`): stop. Critical severity, the selected mark and its dashed halo on the map, the drawn route, destructive/flagged words, the focus ring, disruption flow-cut figures. Measured 5.31:1.
- **Signal Red Soft / Wash** (`{colors.signal-red-soft}` / `{colors.signal-red-wash}`): the shadcn accent surface and disabled red. Backgrounds only.

### Tertiary — route inks
Six community inks carried on line edges and station strokes. `ROUTE_INKS` in `src/lib/notation.ts` is the source of truth and is deliberately six entries, each separable in greyscale weight as well as in hue: **Money Blue**, **Green**, **Ochre**, **Violet**, **Teal**, **Rust**. Money Blue doubles as the money-relationship ink (`TRANSFERRED_TO`, `OWNS_ACCOUNT`) and as the bank-account station stroke. Route inks measure 4.0–4.9:1 — inside the 3:1 non-text bar, outside the 4.5:1 text bar.

### Neutral
- **Platform Terrazzo** (`{colors.platform-terrazzo}`): the ground, and the label plate behind a station name on canvas (at 0.9 alpha).
- **Platform Inset** (`{colors.platform-inset}`): rails, gutters, unfilled bar track, the chrome bar, scrollbar track.
- **Timetable Paper** (`{colors.timetable-paper}`): raised registers, the service index, the detail rail, docked control bars, `.track:hover`, and the fill inside every station mark on the map.
- **Rule Hair** (`{colors.rule-hair}`) / **Rule Strong** (`{colors.rule-strong}`): the two rule weights. Hair divides rows within a register; strong divides one region from another and draws the ghost border of an unstated pill.
- **Ink Soft** (`{colors.ink-soft}`, 6.36:1) and **Ink Faint** (`{colors.ink-faint}`, 4.67:1): secondary prose and field labels respectively. Both clear AA at 13px and 11px.

### Named Rules

**The Stop Rule.** Signal red means stop and nothing else: critical alerts, the selected mark, the drawn route, destructive actions. It is absent from `ROUTE_INKS` on purpose — a community that happened to be numbered first is not an emergency.

**The Number Is Not An Accusation Rule.** Red never colours a score figure or a role word. Priority, position and record figures are always `text-ink`. Role state rides the pill's 1px border and 2px inset rule (`--status-tone`), and the word inside stays ink. A role set in red reads as a verdict on a person.

**The One Amber Rule.** `--amber` #F0A81E is display-only — rules, studs, board type on black, selection. `--amber-deep` #6B4600 is the only amber allowed to carry text on the light ground.

**The Line-Colour Rule.** Community colour rides the line edge and the station stroke. It never fills a field behind text, and it never carries body copy. A cross-community line stays neutral ink-soft, which is what makes an interchange visible without labelling it.

**The Named State Rule.** Every state carries a word and a shape as well as a hue: "On record" beside an amber-deep pill border, a square severity chip beside its severity word, a double ring on an interchange.

## Typography

**Display Font:** Archivo Narrow (via `--font-condensed`, falling back to Archivo)
**Body Font:** Archivo (via `--font-sans`, falling back to system-ui)
**Mono:** ui-monospace / Cascadia Mono — reserved for nothing in the console; figures use Archivo's tabular numerals instead.

**Character:** One industrial grotesque superfamily at two widths, the way station signage and a printed timetable are the same voice set differently. Wide enough to read across a concourse, narrow enough to fit a service name in a column. Body text runs `font-feature-settings: "tnum" 1, "lnum" 1` globally, so every figure on the sheet aligns in its column without a second face.

### Hierarchy
- **Monument** (`--fs-monument`, 3.5rem / 4.5rem presenting, Narrow 700, lh 0.92): reserved for a single full-bleed figure. Spent once in the shipped build; it is a scale step, not a habit.
- **Sheet** (`--fs-sheet`, 1.75rem / 2.25rem, 600, lh 1): the lens's own H1 — "Key players".
- **Title** (`--fs-title`, 1.125rem / 1.375rem, 600): the detail rail's subject name (set in `.sign`), the footer nameplate, a player's priority figure.
- **Lead** (`--fs-lead`, 0.9375rem / 1.125rem, 600): the CORTEX stencil in the chrome, an index score, a severity count.
- **Body** (`--fs-body`, 0.8125rem / 1rem, 400, lh 1.45): the default, set on `body`. Prose paragraphs cap around 46ch.
- **Label** (`--fs-label`, 0.75rem / 0.875rem, Narrow 600, +0.08em, uppercase): station signage caps. Applied through the `.label` class, not through a size utility — that is why there are zero direct `--fs-label` call sites.
- **Note** (`--fs-note`, 0.6875rem / 0.8125rem, 400): marginalia, reasons, provenance, the map key. Applied through `.note`.

Presentation mode (`.presentation` on the sheet root) changes only the seven scale steps and `--notes-w`. No colour, weight or spacing token moves.

### Named Rules

**The `[length:]` Rule (hard).** A font size from a custom property must be written `text-[length:var(--fs-body)]`. `text-[var(--fs-body)]` is silently dropped — Tailwind cannot infer whether an opaque `var()` is a size or a colour, and guesses colour. 127 call sites carried this bug at once and the whole app rendered with no hierarchy at all: every heading, every figure, every caption at 13px. The console is now clean at 114 correct call sites; the marketing landing page (`src/app/page.tsx`) still carries 12 broken ones. Grep `text-\[var\(--fs` before shipping; the result must be zero.

**The Sign Rule.** The largest lettering on any lens is set in `.sign` — condensed, 700, uppercase, +0.015em, lh 0.92 — the way a platform sign is set. Nothing else in the world is set in condensed caps at display size.

**The Figure Rule.** Any number a reader compares down a column carries `.figure` (tabular lining numerals). Identifiers are never grouped: an ID is printed `10127533`, never `1,01,27,533`. Quantities are grouped `en-IN`. Money is `₹` + `en-IN`.

## Layout

One uncut sheet. `SheetLayout` is a fixed `h-dvh` column that never scrolls: chrome bar on top, a flex region for the lens, the command bar. Each lens owns its own scroll.

- **Chrome:** a single dense bar — nameplate, eight lens tabs in a horizontally scrollable nav, controls pushed to `ml-auto`. Control labels collapse to their glyphs as the viewport narrows; nothing wraps and nothing is dropped.
- **Concourse (Overview):** a three-column stretch layout, `19rem` service index (`21rem` at xl) / fluid map / `18rem` detail rail. The index hides below `md`, the detail rail below `xl`. The map takes the whole remaining viewport, minimum 26rem tall (34rem at sm).
- **Register lenses (Players, etc.):** a 12-column grid inside `max-w-[1500px]`, `px-6 py-6`, `gap-x-6 gap-y-8`, splitting 7/5 at `lg`.
- **Rhythm:** dense rows are `py-1.5 px-3`; register list items `py-2`–`py-3`; section headings sit on a `border-b border-ink` with `pb-1` and `mt-8` above. The recurring spacing steps are 4 / 6 / 12 / 24 / 32px.
- **Register grid:** `.register-row` fixes the dense five-column timetable at `2.5rem 5.5rem 1fr 9rem 6rem`, widening to `3rem 6.5rem 1fr 10rem 7rem` in presentation.
- **Footer:** the title block is a bordered strip of fixed `min-w-[9rem]` cells laid flat in the page flow at the bottom of a scrolling lens — never floated over content.

### Named Rules

**The Docked Controls Rule.** Controls dock to an edge; they never float over the map. A panel lying on a route map hides exactly the lines the map exists to show, and a presenter on a projector cannot move it. The only thing permitted over the plate is the hover caption (it is about the mark under the pointer), the map's own title plate, and its key along the bottom edge.

**The Map Gets The Viewport Rule.** On the first screen the network is at the size of the room. The sheet's own title, counts and specification are read second, below the fold.

## Elevation & Depth

Flat by construction. There is no elevation ramp and no ambient shadow vocabulary; separation is carried by 1px rules, three tonal steps of grey (`#D6DAD6` / `#E4E7E4` / `#EEF0ED`), and inset stripes. Four box-shadows exist in the whole build and three of them are lines, not lifts:

- **Nameplate underline** (`inset 0 -2px 0 var(--amber)`): the lit amber rule under the station nameplate.
- **Active lens underline** (`inset 0 -2px 0 var(--amber-deep)`): the lit platform.
- **Status pill inset** (`inset 2px 0 0 var(--status-tone)`) and **`.pencil-line`** (`inset 0 -2px 0 var(--pencil)`): state as a rule, not a fill.
- **`.note-paper`** (`0 1px 0 var(--rule-strong), 0 8px 22px -14px rgba(20,22,19,0.4)`): the only genuine lift. A sheet of timetable paper resting on the concourse — used for the empty-chart card and error cards. The 1px hard line under it is the paper's edge; the diffuse part is inset far enough that it reads as contact, not levitation.
- **Notes drawer** (`-8px 0 24px -16px rgba(31,31,31,0.5)`): the drawer's edge against the sheet.

### Named Rules

**The Rule-Not-Shadow Rule.** To separate two planes, draw a rule (`--rule` within a register, `--rule-strong` between regions, `--ink` under a section heading). Reach for a shadow only when a surface genuinely sits on top of the ground, and then only `.note-paper`.

## Shapes

`--radius: 0px`, and every derived radius (`--radius-sm/md/lg/xl`) is 0px too. Every box in the console is a true rectangle: buttons, pills, cards, inputs, plates, chips. A curve appears in exactly three places, all of them marks rather than containers:

- the 45° bend on a map line, rounded by up to 9px at scale;
- circular severity dots and the interchange ring (2–3px marks);
- the nine notation shapes on the map, which encode entity type.

**Notation shapes** (`SHAPE` in `src/lib/notation.ts`) are the system's real form language: circle = person, square = organisation, diamond = phone, hexagon = bank account, triangle = vehicle, rect = case/report, pin = location, tag = handle, ring = government ID. `Glyph` renders the same shapes inline in registers and keys so the sheet and the map speak one alphabet.

**Line style is evidence grade** (`DASH`): solid `[]` = structured or checksum record; dashed `[11, 3.5]` = rule-extracted from text; dotted `[1.5, 4]` = model-inferred. With no extractor on the edge, confidence decides — ≥0.95 solid, <0.7 dotted, else dashed.

### Named Rules

**The Zero Radius Rule.** Nothing that contains content is rounded. If a corner is curved, it is a mark on the map, not a box on the sheet.

## Components

### Buttons
- **Shape:** square (0px), 1px border, no fill at rest.
- **Outline (primary action):** `border border-ink`, `.label` type, `px-2 py-1.5`; hover inverts to `bg-ink text-film`. Used for "Open full record".
- **Chip (secondary action):** `border border-rule-strong px-2 py-0.5`, `text-ink-soft`; hover raises the border to `border-ink` and the text to `text-ink`. Used for "Emphasise on chart", "Draw route", member shortcuts.
- **Text action:** `.label text-ink-soft` with `hover:text-ink`, no border. Used for "clear emphasis", "show all".
- **Toggle / sort:** `aria-pressed` + `.pencil-line` (2px signal-red inset underline) marks the chosen sort; unchosen sits `text-ink-faint`.
- **Focus:** global `:focus-visible` — `2px solid var(--pencil)`, `2px` offset. Never removed, never restyled per component.

### Chips and Status Pills
- **Status pill (`.status`):** inline-flex, condensed 11px, +0.09em, uppercase, `text-ink`, 1px border and a 2px inset left rule both drawn in `--status-tone`. Tones: `--pencil` at suspicion ≥0.5, `--amber-deep` at ≥0.2, `--rule-strong` otherwise. The word never changes colour with the state.
- **Line-group filter:** off-state adds `line-through` and `text-ink-faint`; on-state is `label-ink bg-film-deep`.

### Cards / Containers
- **Register (`.track`):** a row, not a card. `border-bottom: 1px solid var(--rule)`, `hover: background var(--film-lift)`. This is the default container for every dense list.
- **Rail panel:** `bg-film-lift` with a `border-r`/`border-l border-rule-strong` against the map. No radius, no shadow.
- **Map plate:** `border border-ink bg-film-lift/95 px-3 py-2`, pinned top-left of the map, `pointer-events-none`, max `26rem` — a printed map's title in its corner.
- **Note paper (`.note-paper`):** the only lifted surface. `p-4`–`p-5`.

### Inputs / Fields
- **Search trigger:** `border border-rule-strong bg-film-lift px-2.5 py-1`, inline 14px Lucide glyph, `text-ink-soft`; hover raises border and text to ink; a `.label` kbd hint at `xl`.
- **Checkbox:** native, `accent-ink`, with a `.note`-sized label beside it. No custom control.
- **Caret:** `--amber-deep` in every input and textarea.

### Navigation
- **Nameplate:** `.board` — black ground, condensed uppercase, `board-white` type, 2px amber inset underline. The only dark field in the chrome.
- **Lens tabs:** `.label` at `px-2.5 py-1.5`; inactive `text-ink-soft`, hover `text-ink`; active is `label-ink` plus a 2px `--amber-deep` inset underline and `aria-current="page"`. The lit platform.
- **Overflow:** the nav scrolls horizontally with `.scrollbar-hide`; the control cluster never shrinks.

### The Junction Map (signature)

Canvas 2D, chosen because the notation needs true dashed and dotted strokes and nine node shapes that WebGL edge programs do not give. graphology holds the graph; ForceAtlas2 places the stations (strong repulsion, weak gravity, a second size-aware pass to pull overlaps apart); disconnected components are shelf-packed largest-first with a 28px gutter so a sheet of small networks does not become dust on an enormous canvas. Layout seeds are deterministic per node id, so a re-render draws the same map.

- **Ground:** `.sheet-ground` terrazzo. Station fill is always `#EEF0ED`; only the stroke carries meaning.
- **Station stroke:** route ink by community; `--blue` for a bank account; `--ink-soft` for infrastructure; `--pencil` when selected or on the drawn route. Stroke weight 1.6 at rest, 2.3 for a person of interest or an interchange, 3 for selection.
- **Adverse record:** a filled signal-red dot at 34% of the mark's radius, persons and organisations only.
- **Radius:** `nodeRadius` — persons/organisations `6.5 + priority × 15`; everything else `4 + min(degree, 30) × 0.1`; ×1.35 in presentation. Priority carries size; infrastructure sits small.
- **Selection:** signal-red stroke plus a dashed `[2,3]` halo at r+5.
- **Line ink:** money blue for `TRANSFERRED_TO` / `OWNS_ACCOUNT`; the community's route ink when both endpoints ride the same route; neutral ink-soft when the line crosses between routes. Width `1.5 + √(relative weight) × 2.2`; receded lines drop to 0.08 alpha.

**The Octilinear Rule.** No line is drawn at an arbitrary angle. Every link leaves its station on an axis, turns once through a single rounded 45° bend (radius ≤ half the shorter joined segment), and arrives. The straight axis run is always spent at the busier endpoint, so trunks leave an interchange square and the eye can follow one route across a crowded field. A run too short to bend is drawn as a plain segment.

**The Interchange Rule.** A double ring — a second stroke at r + 3.2 — marks a station where more than one route calls, and marks nothing else. It is the broker standing on two communities at once, which is the mark an investigator opens first.

**The Give-Up-The-Slot Rule.** A station name tries four slots in order: right, left, below, above. If every slot would collide with a name already set or run off the plate, the name is not printed. Names are never overprinted and never clipped — except the current selection, which always gets its name. Names sit on a 0.9-alpha terrazzo plate so a line never runs through a letter.

**The Canvas Face Rule.** Canvas cannot read a CSS custom property. `LABEL_FACE` in `LinkChart.tsx` names the station face outright and must be changed in the same commit as `--font-condensed` in `globals.css`, or the map silently drifts off the world's type.

Keyboard: the canvas is `role="application"`, focusable, with arrows to pan, `+`/`-` to zoom, `0` to fit, Enter to cycle persons of interest, Escape to clear, and an `aria-label` that states all of it.

### Split-flap state change
`.flap` (`rotateX(-88deg) → 12deg → 0`, 260ms, `cubic-bezier(0.16, 1, 0.3, 1)`, `transform-origin: 50% 0`) lands a status change as a physical event rather than a silent repaint. `.flap-seam` draws the 1px seam across a character cell. `.thread-wipe` strikes a rule across a tray once (1100ms) and deliberately carries no `fill-mode`, so if the animation never runs the element keeps its declared full width instead of collapsing to nothing. All three are disabled under `prefers-reduced-motion`.

## Do's and Don'ts

### Do:
- **Do** write every custom-property font size as `text-[length:var(--fs-NAME)]`. Grep `text-\[var\(--fs` before shipping; the answer must be zero.
- **Do** keep score figures in `text-ink` and let state ride the pill's border and inset rule (`--status-tone`).
- **Do** use `--amber-deep` #6B4600 for any amber that carries text on the light ground, and reserve #F0A81E for rules, studs, board type and selection.
- **Do** dock controls to an edge of the map region; the map keeps its plate clear.
- **Do** give every state a word and a shape as well as a hue.
- **Do** put the evidence beside the score — reasons under a rank, an extractor grade on every line.
- **Do** name severity in the register's own words: Critical, High, Medium, Low.
- **Do** keep every line on the map octilinear with one 45° bend, the axis run at the busier end.
- **Do** update `LABEL_FACE` in `LinkChart.tsx` whenever `--font-condensed` changes.
- **Do** separate planes with a rule or a tonal step before reaching for a shadow.

### Don't:
- **Don't** borrow station *vocabulary*. The form is the station's; the words are the register's. No Cancelled, Delayed, Diverted, On Time, Platform 4.
- **Don't** spend signal red on anything but stop — never on a route, never on a score figure, never on a role word. It stays out of `ROUTE_INKS`.
- **Don't** set body text in a route ink; they measure 4.0–4.9:1 and are cleared for lines and marks only.
- **Don't** put a coloured fill behind text to signal a community. Colour rides the edge.
- **Don't** float a panel over the junction map. Only the hover caption, the title plate and the bottom key may sit on the plate.
- **Don't** round a container. `--radius` is 0px and every derived radius is 0px; curves belong to marks.
- **Don't** add a KPI tile grid, a glow, a gradient or a dark force-graph ground. This world refuses all four by name.
- **Don't** print a row that says nothing — an empty property, a "0 named accused", a blank cell. A row that is always there teaches the reader to stop reading the line.
- **Don't** overprint or clip a station name; drop it instead.
