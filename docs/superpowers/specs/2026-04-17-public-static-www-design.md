# Public Static WWW Design

## Goal

Replace the current Streamlit-based public bundle with a truly static `www/` export that can be uploaded to any standard web server and shared online. The public site should feel editorial and elegant, stay tightly focused on programme and papers, and work well on both desktop and small screens.

## Product Direction

- Deployment target: static `www/` folder only
- Homepage priority: programme first
- Scope: programme, papers, download
- Visual tone: cleaner independent identity, editorial and elegant
- Interaction model:
  - desktop supports hover affordances where helpful
  - mobile uses tap/click expand patterns
  - cards and controls stay large enough for touch

## Why Static Instead of Streamlit

The current Streamlit public bundle is useful for a first draft, but it still behaves like a lightweight application rather than a publication. It constrains layout, touch behavior, spacing, and overall visual polish. A static site gives direct control over typography, rhythm, hit targets, responsive behavior, and hosting simplicity.

## Information Architecture

The public site stays narrowly focused on three surfaces:

### 1. Programme

This is the homepage.

- Day selector near the top
- Day view broken into time blocks
- Each block contains session cards
- Opening a session reveals its talks inline
- Talks can reveal abstracts without navigating away

Primary user jobs:

- understand what is happening at a given time
- scan across sessions quickly
- open a session and inspect the talks
- read an abstract without losing context

### 2. Papers

This is the secondary browsing surface.

- Searchable and filterable directory
- Lightweight rows/cards rather than dense tables
- Each paper preserves its session/day context
- Each paper can link back to the relevant session view

Primary user jobs:

- search by title or author
- browse papers across the whole conference
- jump from a paper back to its programme context

### 3. Download

This remains present but understated.

- Excel download available from the header or utility area
- Does not dominate the homepage

## Recommended Layout Direction

### Programme Ledger

This is the recommended direction.

The homepage behaves like a readable conference programme rather than a control panel:

- top utility bar with title, day switcher, and download action
- block-based vertical rhythm
- session cards grouped under each time block
- sessions open inline
- talks listed as readable editorial rows
- abstracts appear in place

Why this direction:

- best fit for programme-first browsing
- strongest alignment with editorial/elegant tone
- easiest to make readable on small screens
- works naturally as static HTML rendered from JSON

## Alternatives Considered

### Magazine Mosaic

More expressive and visually distinctive, but less efficient for schedule scanning and more likely to overcomplicate the homepage.

### Compact Matrix

Preserves the current cross-room comparison pattern, but tends to become dense and touch-unfriendly on small screens. It also risks feeling too much like an operations view.

## Interaction Design

### Session Opening

- Desktop: session cards open inline below the selected card or within the block stack
- Mobile: cards expand vertically in place
- Only one or a small number of sessions should be expanded at once to keep the page manageable

### Abstract Reveal

- Desktop: hover can preview that more detail exists, but click should still be supported
- Mobile: tap opens an accordion or drawer-style abstract panel within the talk list
- No hover-only dependency for critical information

### Tap Targets

- session cards must be comfortably tappable
- talk rows must not rely on tiny buttons
- controls should be visually clear and large enough for thumbs

### Navigation Behavior

- day switch preserves the programme-first mindset
- papers page has its own search/filter controls
- internal navigation should be lightweight and avoid full reloads where possible

## Visual Design

The site should feel like a lightweight publication.

### Tone

- calm
- spacious
- editorial
- readable before decorative

### Identity

Use a cleaner independent visual identity rather than reusing the existing conference tool styling directly.

### Palette

- warm off-white or soft paper background
- dark ink text
- restrained blue-gray structural accents
- one deeper accent color for active states and links

### Typography

- editorial serif for major headings and possibly session titles
- clean sans-serif for metadata, controls, labels, and utilities
- strong hierarchy driven by type, spacing, and contrast instead of heavy containers everywhere

### Layout Rhythm

- generous vertical spacing between blocks
- clear time markers
- session cards with comfortable padding
- lightweight metadata lines
- mobile layout collapses into a linear reading flow instead of preserving a desktop matrix

## Responsive Design

### Desktop

- allows richer block/session scanning
- hover affordances can complement click
- more breathing room for session cards and talk lists

### Tablet

- maintain block structure
- reduce side-by-side density
- keep filter and day controls accessible without crowding

### Mobile

- convert to a clear stacked layout
- day selector remains easy to reach
- sessions expand vertically
- abstracts reveal inline on tap
- avoid small secondary controls

## Technical Design

The bundle output should become a real static website package:

```text
www/
  index.html
  assets/
    styles.css
    app.js
  data/
    programme.json
  programme.xlsx
```

### Rendering Model

- bundle step generates `programme.json` and `programme.xlsx`
- static HTML shell loads the JSON in the browser
- JavaScript renders programme and papers views client-side
- no Python runtime required after export

### Data Source

Reuse the existing public JSON payload shape as the source of truth where possible. If small additions are needed for smoother client-side rendering, adjust the public payload generator rather than inventing a second parallel export format.

### Bundle Generation

Replace or extend the current public bundle assembly so that it:

- creates the `www/` directory
- copies static web assets into place
- writes the public JSON to `www/data/programme.json`
- writes the Excel file to `www/programme.xlsx`
- avoids shipping Streamlit runtime files in the static bundle

## Testing

Testing should cover both correctness and packaging expectations.

### Bundle Tests

- bundle contains static web files
- bundle contains public JSON and Excel
- bundle does not contain Streamlit runtime files
- bundle does not contain private/editor-only folders

### Front-End Tests

- verify expected labels and structural hooks exist in generated HTML/JS
- verify programme-first default rendering
- verify mobile-specific interaction hooks for expanding sessions and abstracts

### Data Safety

- preserve the existing public-data guarantees
- no private links, reviewer data, or editor-only metadata in the static site bundle

## Risks and Constraints

### Risk: Over-designed homepage

Mitigation:
- keep the programme itself central
- avoid magazine-style ornament that slows scanning

### Risk: Desktop interactions that fail on mobile

Mitigation:
- design all essential interactions around tap/click first
- treat hover as enhancement only

### Risk: Divergence between public JSON and static UI needs

Mitigation:
- evolve the public payload intentionally
- keep one public data contract serving both download and rendering needs

## Out of Scope

- conference overview/marketing homepage sections
- authentication or admin behavior
- editable public interface
- server-rendered runtime requirements

## Recommendation

Proceed with a static `www/` export built around the Programme Ledger layout. This gives the best combination of:

- elegant public-facing presentation
- clear mobile usability
- static hosting simplicity
- strong programme browsing
