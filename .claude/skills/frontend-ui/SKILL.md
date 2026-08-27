Frontend UI

Build interfaces that feel intentionally designed, not assembled from a component library.

Tailwind is the styling language, not the design system. Component libraries should provide behavior and accessibility, not visual identity.

When a product already has a visual language, preserve it. When it does not, define a coherent visual grammar before styling individual components.

Preferred stack

A good default is:

React / Next.js

Tailwind CSS

shadcn/ui

Radix primitives

Lucide icons

Motion for React when motion materially improves the experience

Do not add dependencies just because they are listed here. Inspect the project first and reuse its stack when reasonable.

shadcn philosophy

Use shadcn for behavior, not branding.

Use it for accessible:

dialogs

dropdowns

selects

popovers

tooltips

tabs

command palettes

form primitives

Aggressively restyle shadcn components so they match the product. Do not ship stock shadcn visuals unless they genuinely fit.

Prefer shadcn/Radix over manually rebuilding complex accessible controls.

Design the system before the components

Do not design component-by-component.

First establish:

Page background

Section background

Surface / panel

Raised or nested surface

Interactive controls

Hover / focus / selected states

Typography hierarchy

Accent colors

Border language

Radius language

Motion language

Then apply those rules consistently.

Visual hierarchy

Use layered surfaces instead of one flat background.

Example:

Page             #0A0B0D
Large panel       #0E1014
Nested surface    rgba(255,255,255,0.025)
Border            rgba(255,255,255,0.06)
Hover border      rgba(255,255,255,0.11)
Primary text      #DEDBD8
Secondary text    rgba(222,219,216,0.60)
Tertiary text     rgba(222,219,216,0.35)
Accent            #A4B4D0

The hierarchy should be understandable before the user reads the copy.

Color

Do not build the entire interface from stock Tailwind gray/slate colors.

Define a small custom palette with deliberate temperature.

For a technical-noir / aerospace / industrial-CAD aesthetic:

@theme {
  --color-bg: #0a0b0d;
  --color-bg-elevated: #111419;
  --color-surface: #1b2027;
  --color-surface-light: #353b45;
  --color-steel: #54575d;

  --color-text: #dedbd8;
  --color-text-secondary: #aaa7a3;
  --color-text-muted: #56585d;

  --color-accent-blue: #a4b4d0;
  --color-accent-blue-bright: #b5c9ea;
  --color-accent-red: #a16057;
  --color-accent-red-dark: #582823;
  --color-accent-brass: #9a7a32;

  --color-hardware-light: #dad7d3;
  --color-grid: #111820;
}

Characteristics:

cool, blue-biased blacks instead of pure black

warm off-whites instead of pure white

desaturated accents instead of loud colors

low-contrast texture and geometry

sparse steel blue, oxide red, and brass

Approximate distribution:

90% black / graphite / gray
7%  cool steel blue
2%  oxide red
1%  brass / metallic gold

Do not force this palette onto products with another established brand.

Typography

Typography is a major part of perceived quality.

Prefer:

one strong display or primary sans

one utilitarian mono for metadata and technical labels

fewer font sizes with stronger hierarchy through weight, tracking, opacity, and spacing

Avoid:

many nearly identical text sizes

equally bright labels everywhere

excessive bold

all-caps body copy

Example technical label:

function TechnicalLabel({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
      {children}
    </span>
  )
}

Use mono selectively for IDs, metrics, instrumentation, labels, and metadata rather than normal prose.

Spacing

Use a disciplined spacing vocabulary.

A useful baseline:

4px   micro spacing
8px   compact internal spacing
12px  control spacing
16px  standard component spacing
24px  panel spacing
32px  section spacing
48px+ major composition spacing

Do not scatter arbitrary gaps and paddings throughout the page.

Borders

Premium dark interfaces usually benefit from subtle borders.

Prefer:

border border-white/[0.06]

Typical states:

Default border    rgba(255,255,255,0.06)
Hover border      rgba(255,255,255,0.10)
Strong divider    rgba(255,255,255,0.14)

Borders should reinforce hierarchy without becoming decoration.

Surfaces

Use layered near-black or translucent surfaces.

Example:

<div
  className="
    rounded-md
    border border-white/[0.06]
    bg-white/[0.025]
    backdrop-blur-xl
    transition-colors duration-200
    hover:border-white/[0.10]
    hover:bg-white/[0.04]
  "
>
  {children}
</div>

Do not put every piece of information inside a card. Use a card only when the content has a meaningful boundary.

Geometry

Pick a radius language and stay consistent.

2–4px    industrial / technical / severe
6–10px   modern product UI
14–20px  soft / friendly / consumer

Do not randomly mix square components, large radii, and pills.

Reserve pills primarily for tags, statuses, segmented controls, and compact filters.

Custom primitives

Create product-specific primitives for repeated visual patterns.

Examples:

<Surface />
<SectionLabel />
<TechnicalLabel />
<Metric />
<StatusDot />
<IconButton />
<Divider />
<PanelHeader />
<DataValue />

These primitives should encode the visual system so new pages naturally remain consistent.

Do not abstract merely to reduce line count. Abstract when a repeated semantic or visual pattern exists.

Interaction states

Every interactive control should have intentional:

default

hover

focus-visible

active / pressed

selected

disabled

loading

error states where relevant

Do not rely on hover as the only sign that something is interactive.

Maintain accessible focus states.

Motion

Use motion to reinforce state and hierarchy, not as decoration.

Good defaults:

120–250 ms transitions

1–2 px lifts

subtle opacity changes

restrained scale changes

smooth panel expansion

diagram assembly

graph drawing

content reveals

subtle lighting shifts

Example:

<motion.div
  whileHover={{ y: -1 }}
  transition={{ duration: 0.16 }}
>
  {children}
</motion.div>

Avoid:

large springy motion on every element

gratuitous entrance animations

long delays

motion that slows task completion

many unrelated properties animating simultaneously

Respect reduced-motion preferences.

Large visual moments

Components alone do not make a memorable interface.

On important pages, consider one or two strong visual moments:

oversized typography

product render

technical diagram

chart or data visualization

subtle grid

low-contrast geometric background

interactive illustration

carefully composed empty state

dramatic but restrained hero composition

Keep surrounding areas quieter so focal elements remain meaningful.

Background texture

For technical interfaces, subtle geometry can add depth:

honeycomb

fine grid

radial guides

measurement ticks

blueprint-like lines

very soft noise

Keep it close to the background color.

Background    #0A0B0D
Grid          #111820

The texture should be felt before it is consciously noticed.

Icons

Prefer one icon family throughout the product. Lucide is a good default.

Keep icon size and stroke weight consistent.

Avoid mixing outline icons, filled icons, emoji, and unrelated icon packs without a deliberate reason.

Avoid generic SaaS design

Actively avoid interfaces that look like untouched component-library demos.

Common failure modes:

a card around every section

rounded-xl everywhere

giant gradients behind everything

excessive glassmorphism

purple/blue gradients as the only brand identity

default shadcn spacing and typography

stock Tailwind slate palette

repeated three-column card grids

excessive badges

excessive pills

excessive shadows

random icon containers

weak typography

too many separators

overly centered layouts

dashboard density with no hierarchy

Prefer composition, hierarchy, typography, and restraint.

Dark UI

Dark mode is not white text on black.

Use several near-black layers and avoid pure white for most text.

Background      #0A0B0D
Panel           #111419
Surface         #1B2027
Primary text    #DEDBD8
Secondary text  #AAA7A3
Muted text      #56585D

This creates depth and reduces the harshness of pure black/white contrast.

Responsive design

Do not treat mobile as a shrunken desktop.

At smaller widths:

collapse secondary information

reduce decoration

stack intentionally

preserve primary actions

keep touch targets large enough

simplify complex diagrams

maintain typography hierarchy

avoid horizontal scrolling unless necessary

For dense data interfaces, prefer an alternate mobile representation over squeezing a desktop table into a narrow viewport.

Implementation workflow

When asked to implement or redesign frontend UI:

Inspect the existing application.

Identify its framework, component library, fonts, tokens, and layout conventions.

Reuse good existing primitives.

Identify the page's primary user goal.

Establish or infer the visual system before editing many components.

Define background, surface, typography, border, radius, and accent rules.

Build the high-level composition first.

Create reusable primitives for repeated patterns.

Use shadcn/Radix for complex accessible behavior when available.

Add complete interaction states.

Add motion only where it improves comprehension or delight.

Check desktop and mobile layouts.

Remove unnecessary decoration.

Verify the page feels coherent at a glance.

Run the project's lint, typecheck, tests, and build commands when appropriate.

Finish checklist

Before considering the UI finished, ask:

Is there a clear visual hierarchy?

Is there one obvious primary focal point?

Are surface layers distinguishable without strong borders?

Is typography doing enough hierarchy work?

Are muted labels actually muted?

Are accent colors sparse enough to remain meaningful?

Is spacing consistent?

Is the radius language consistent?

Are there too many cards?

Are there too many pills?

Are gradients or shadows doing unnecessary work?

Does every control have hover and focus states?

Do loading, empty, disabled, and error states exist where needed?

Is motion restrained?

Does mobile feel intentionally designed?

Could any element be removed without losing information?

Does this look like the product, or like the default library?

If it looks like the default component library, keep refining.

Default aesthetic when no brand direction exists

When the task calls for a sophisticated technical product interface and provides no other style direction, prefer:

Technical noir / aerospace instrumentation / industrial CAD

Use:

deep blue-black backgrounds

graphite surfaces

warm ivory typography

subtle borders

monospaced technical metadata

restrained steel-blue highlights

occasional oxide-red or brass accents

low-contrast grid or geometric texture

compact, precise controls

strong compositional focal points

subtle motion

minimal decorative chrome

Do not apply this default when the product, audience, or requested emotional tone clearly calls for something else.