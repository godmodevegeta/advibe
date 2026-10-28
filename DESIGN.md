---
version: alpha
name: advibe
description: >-
  advibe is an autonomous AI ad campaign engineer that transforms complex engineering workflows into streamlined, autonomous
  execution. The design system reflects a minimalist, high-contrast aesthetic centered on clarity and technical
  precision.
logo:
  src: https://advibe.ai/favicon.svg
colors:
  surface: '#f8f8f8'
  surface-dim: '#f0f0f0'
  surface-bright: '#ffffff'
  surface-container-lowest: '#efefef'
  surface-container-low: '#f3f4f6'
  surface-container: '#f8f8f8'
  surface-container-high: '#e5e7eb'
  surface-container-highest: '#d9d9d9'
  on-surface: '#191919'
  on-surface-variant: '#6c757d'
  inverse-surface: '#191919'
  inverse-on-surface: '#ffffff'
  outline: '#c2c2c2'
  outline-variant: '#d0d0d0'
  surface-tint: '#000000'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#1e2939'
  on-primary-container: '#e7e7e7'
  inverse-primary: '#ffffff'
  secondary: '#3080ff'
  on-secondary: '#ffffff'
  secondary-container: '#e5f0ff'
  on-secondary-container: '#003d99'
  tertiary: '#ff544e'
  on-tertiary: '#ffffff'
  tertiary-container: '#ffe5e3'
  on-tertiary-container: '#cc3a31'
  error: '#fb2c36'
  on-error: '#ffffff'
  error-container: '#ffb4ab'
  on-error-container: '#93000a'
  primary-fixed: '#1e2939'
  primary-fixed-dim: '#0f1419'
  on-primary-fixed: '#ffffff'
  on-primary-fixed-variant: '#c2c2c2'
  secondary-fixed: '#3080ff'
  secondary-fixed-dim: '#0052cc'
  on-secondary-fixed: '#ffffff'
  on-secondary-fixed-variant: '#e5f0ff'
  tertiary-fixed: '#ff544e'
  tertiary-fixed-dim: '#cc3a31'
  on-tertiary-fixed: '#ffffff'
  on-tertiary-fixed-variant: '#ffe5e3'
  background: '#ffffff'
  on-background: '#191919'
typography:
  display:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 60px
    fontWeight: '400'
    lineHeight: 68px
    letterSpacing: '-0.04em'
  headline-lg:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 40px
    fontWeight: '400'
    lineHeight: 48px
    letterSpacing: '-0.02em'
  headline-md:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 28px
    fontWeight: '400'
    lineHeight: 36px
    letterSpacing: '-0.01em'
  title-lg:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 20px
    fontWeight: '400'
    lineHeight: 28px
    letterSpacing: 0em
  body-lg:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
    letterSpacing: 0em
  body-md:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  label-md:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: nbInternationalPro, system-ui, sans-serif
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 40px
  xl: 64px
  gutter: 24px
  container-max: 1400px
elevation:
  sm: 0 1px 2px rgba(0, 0, 0, 0.06)
  md: 0 3px 8px rgba(0, 0, 0, 0.15)
  lg: 0 12px 24px -8px rgba(0, 0, 0, 0.18), 0 4px 10px -2px rgba(0, 0, 0, 0.1)
layout:
  containerMaxWidth: 1400px
  gridColumns: 12
components:
  button-primary:
    backgroundColor: '{colors.primary}'
    textColor: '{colors.on-primary}'
    typography: '{typography.label-md}'
    rounded: '{rounded.full}'
    padding: 12px 20px
    height: 40px
    boxShadow: none
    border: none
  button-primary-hover:
    backgroundColor: '{colors.primary-container}'
    textColor: '{colors.on-primary-container}'
  button-secondary:
    backgroundColor: transparent
    textColor: '{colors.on-surface}'
    typography: '{typography.label-md}'
    rounded: '{rounded.DEFAULT}'
    padding: 12px 16px
    height: 40px
    border: 1px solid {colors.outline}
  button-secondary-hover:
    backgroundColor: '{colors.surface-container-high}'
    textColor: '{colors.on-surface}'
  card:
    backgroundColor: '{colors.surface-container}'
    rounded: '{rounded.md}'
    padding: '{spacing.md}'
    boxShadow: '{elevation.md}'
    border: 1px solid {colors.outline-variant}
  card-hover:
    backgroundColor: '{colors.surface-container-high}'
    boxShadow: '{elevation.lg}'
  input-field:
    backgroundColor: '{colors.surface-bright}'
    textColor: '{colors.on-surface}'
    typography: '{typography.body-md}'
    rounded: '{rounded.DEFAULT}'
    padding: '{spacing.sm}'
    border: 1px solid {colors.outline}
    height: 40px
  input-field-focus:
    borderColor: '{colors.primary}'
    boxShadow: 0 0 0 3px rgba(0, 0, 0, 0.08)
  list-item:
    backgroundColor: transparent
    rounded: '{rounded.md}'
    padding: '{spacing.sm}'
    textColor: '{colors.on-surface}'
  list-item-hover:
    backgroundColor: '{colors.surface-container-high}'
    textColor: '{colors.primary}'
  badge:
    backgroundColor: '{colors.secondary-container}'
    textColor: '{colors.secondary}'
    typography: '{typography.label-sm}'
    rounded: '{rounded.full}'
    padding: 4px 8px
  dropdown-panel:
    backgroundColor: '{colors.surface-bright}'
    rounded: '{rounded.md}'
    boxShadow: '{elevation.md}'
    border: 1px solid {colors.outline-variant}
    padding: 0px
  dropdown-option:
    padding: 6px 12px
    textColor: '{colors.on-surface}'
    typography: '{typography.body-md}'
  dropdown-option-hover:
    backgroundColor: '{colors.surface-container-high}'
    textColor: '{colors.primary}'
---

## Overview

advibe embodies a **Minimalist-Technical** aesthetic that prioritizes clarity, precision, and direct communication. The design system serves an autonomous AI ad campaign engineer platform, targeting serious engineering teams who value efficiency and unambiguous visual hierarchy. The UI evokes a sense of technical competence and reliability through high contrast, generous whitespace, and a monochromatic foundation punctuated by functional accent colors. The emotional response is one of calm confidence: users trust that advibe will execute complex tasks without distraction or visual noise.

The brand voice is direct, matter-of-fact, and jargon-aware. advibe speaks to engineers in their language—precise, action-oriented, with zero marketing fluff. The vocabulary emphasizes autonomy, execution, and results: "From problem to merged PR, advibe gets hard engineering work done." Tone is never breathless or hyperbolic; instead, it's reassuring and grounded. Example sentence in brand voice: "advibe runs in the cloud or on your machine, tests in its own browser, and won't stop until the PR is ready to merge."

## Colors

The color system is anchored in a **high-contrast, monochromatic foundation** with surgical accent colors for interaction and status. Primary (#000000) is pure black, used exclusively for CTAs, primary navigation, and the most critical interactive elements. It commands attention through its absolute contrast against the light surface (#f8f8f8). Secondary (#3080ff) is a vivid, saturated blue reserved for secondary actions, links, and informational highlights—it provides visual relief without competing with primary. Tertiary (#ff544e) is a warm red-orange used sparingly for warnings, errors, and high-urgency states.

The surface stack uses a tight, near-white palette: surface (#f8f8f8) is the default canvas, surface-container-high (#e5e7eb) is used for hover states and subtle elevation, and

## Typography

The type system uses **nbInternationalPro** as the sole typeface family, a geometric sans-serif that conveys technical precision without coldness. The hierarchy is built on weight (400 for body and headlines, 500 for labels and emphasis) and size alone—no italic or decorative variants. Display (60px, 400 weight, -0.04em tracking) is reserved for hero headlines and sets the tone of authority. Headline-lg (40px, 400 weight, -0.02em tracking) is used for section titles and major content blocks. Body-md (16px, 400 weight) is the workhorse for all body copy, maintaining 1.5 line-height (24px) for comfortable reading. Label-md (14px, 500 weight, 0.01em tracking) is used for buttons, form labels, and UI chrome. On small labels over busy backgrounds (e.g., status badges on code diffs), apply text-

## Layout

The layout system uses a **fluid, container-based grid** with a max-width of 1400px and 12-column structure. Pages are built with a gutter of 24px on desktop, reducing to 16px on tablet and 12px on mobile. Sections are separated using lg spacing (40px) for major breaks and md spacing (24px) for subsections. The hero section uses a two-column layout (text left, visual right) with asymmetric padding: 68px top, 90px bottom on the first card, creating visual breathing room. Container widths vary by content type: 800px for narrow text-heavy sections, 960px for balanced layouts, 1400px for full-width hero and showcase sections. White-space is intentional and never filled; empty space is a design decision, not a mistake. Use the spacing scale semantically: xs (4px) for micro-interactions, sm (12p

## Elevation & Depth

Depth is conveyed through **subtle, restrained shadows and border definition**, never through color or blur. The elevation system uses three levels: Level 1 (Base, no shadow) for the default surface and body content; Level 2 (Standard Card, box-shadow: 0 3px 8px rgba(0, 0, 0, 0.15)) for cards, dropdowns, and modals; Level 3 (Elevated, box-shadow: 0 12px 24px -8px rgba(0, 0, 0, 0.18), 0 4px 10px -2px rgba(0, 0, 0, 0.1)) for floating panels and overlays. All shadows use black with 15–18% opacity, never colored shadows. Borders (1px solid #d0d0d0 or #c2c2c2) define container edges and separate se

## Shapes

The shape philosophy is **Geometric Restraint**: rounded corners are used functionally to soften interactive elements, not decoratively. Buttons use full (9999px) border-radius to create pill-shaped CTAs that are unmistakably clickable. Cards and containers use md (0.75rem / 12px) or lg (1rem / 16px) radius to signal containment without visual softness. Input fields use DEFAULT (0.5rem / 8px) radius for a neutral, technical appearance. Dropdowns and panels use md (12px) radius to match cards. The reasoning: full radius on buttons creates a visual affordance ("this is clickable"), while moderat

## Components

### Action Elements
Buttons are the primary interaction pattern. Button-primary uses backgroundColor: #000000, textColor: #ffffff, padding: 12px 20px, height: 40px, and full border-radius (9999px). On hover, shift to button-primary-hover with backgroundColor: #1e2939 (primary-container) and textColor: #e7e7e7. Button-secondary uses transparent background with a 1px border at #c2c2c2, textColor: #191919, and DEFAULT border-radius (8px). On hover, apply backgroundColor: #e5e7eb (surface-container-high). All buttons use label-md typography (14px, 500 weight). Transition all color changes with cubic-bezier(0.4, 0, 0.2, 1) over 150ms for smooth, responsive feedback.

### Containers & Surfaces
Cards use backgroundColor: #f8f8f8, rounded: 12px, padding: 24px, and box-shadow: 0 3px 8px rgba(0, 0,

## Do's and Don'ts

**Do**
- Do use primary (#000000) exclusively on CTAs and primary navigation; it is the brand's most valuable real estate.
- Do maintain 16:1 contrast between text and background on all surfaces; test with WCAG AA standards.
- Do use the full border-radius (9999px) on all buttons to create unmistakable affordance; never use sharp corners on interactive elements.
- Do separate major sections with lg spacing (40px) and subsections with md spacing (24px); whitespace is a design tool.
- Do apply box-shadow: 0 3px 8px rgba(0, 0, 0, 0.15) to cards and dropdowns; never use colored or blurred shadows.
- Do use nbInternationalPro at 400 weight for headlines and body; reserve 500 weight for labels and emphasis only.
- Do transition all interactive state changes (hover, focus, active) with 150ms cubic-bezier(0.4, 0, 0.2, 1) timing for responsive feedback.

**Don't**
- Don't use secondary (#3080ff) or tertiary (#ff544e) on primary CTAs; they dilute the primary's authority and confuse users about action priority.
- Don't add decorative elements, gradients, or blur effects; the system is flat, direct, and functional.
- Don't use border-radius smaller than 8px on any component; it appears unfinished and conflicts with the geometric restraint philosophy.
- Don't mix typefaces or use italic, condensed, or decorative font variants; nbInternationalPro at 400/500 weight is the entire type system.
- Don't use shadows larger than 0 12px 24px -8px rgba(0, 0, 0, 0.18) on any element; excessive shadow depth contradicts the minimalist aesthetic.
- Don't apply color to text smaller than 14px without sufficient contrast testing; small labels must maintain 12:1 contrast minimum.
- Don't use the surface-container stack for interactive elements; reserve it for passive containers and backgrounds only.
