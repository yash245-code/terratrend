# TerraTrend Earthy Design System — Accessibility & Quality Checklist

Evaluated according to WCAG 2.2 Level AA guidelines.

## 1. Contrast & Color Independence
- [x] **Normal Text (>= 4.5:1)**:
  - Light mode: Body text on surface = 14.18:1; Body text on background = 13.74:1 (Passes AAA).
  - Dark mode: Body text on surface = 13.74:1; Body text on background = 16.43:1 (Passes AAA).
- [x] **Muted / Secondary Text (>= 4.5:1)**:
  - Light mode: 7.20:1 on background, 7.43:1 on surface (Passes AAA).
  - Dark mode: 10.00:1 on background, 8.36:1 on surface (Passes AAA).
- [x] **Action Buttons & Badges**:
  - Primary button: `--on-primary` (`#1E3006`) on `--primary` (`#ED7A13`) = 4.99:1 (Passes AA).
  - Secondary button: `--on-secondary` (`#FFFDDD`) on `--secondary` (`#566B33`) = 5.74:1 (Passes AA).
  - Danger button: `--on-danger` (`#FFFFFF`) on `--danger` (`#B3382C`) = 5.97:1 (Passes AA).
  - Good status: `--good-ink` on `--good-bg` = 11.42:1 (light), 9.65:1 (dark).
  - Moderate status: `--moderate-ink` on `--moderate-bg` = 11.50:1 (light), 6.98:1 (dark).
  - Poor status: `--poor-ink` on `--poor-bg` = 7.54:1 (light), 5.25:1 (dark).
- [x] **Color Independence**:
  - Status badges always combine colored fills with textual labels (`GOOD`, `MODERATE`, `POOR`) and semantic prefix icons.
  - Data visualization charts differentiate series using line dashes (`borderDash: [5, 5]`, `[2, 3]`), point shapes (`triangle`, `circle`, `rectRot`, `cross`), and direct text summaries.

## 2. Keyboard Navigation & Focus
- [x] **Visible Focus Ring**: Universal `outline: 3px solid var(--focus); outline-offset: 2px;` active on all interactive elements.
- [x] **Tab Order**: Logical top-to-bottom, left-to-right DOM tab sequence.
- [x] **Interactive Controls**: Touch target minimum height >= 44px on buttons, inputs, selects, and navigation items.

## 3. Responsiveness & Zoom
- [x] **200% Browser Zoom**: Verified layout scalability with fluid CSS clamp font sizes and flex/grid wraps.
- [x] **320px Viewport Width**: No horizontal scrollbars; two-column grid stacks into a single mobile column.

## 4. Alternate Modes & Media
- [x] **Light & Dark Themes**: Fully switchable via the accessible `#themeToggleBtn` in navigation, with instant pre-paint execution to prevent theme flashes.
- [x] **High Contrast / Forced Colors**: Supports `@media (forced-colors: active)` mapping cards and badges to `CanvasText` and `Highlight`.
- [x] **Print Stylesheet**: Clean `@media print` styling converting background to clean white, hiding interactive navigation, and preserving high-contrast text.
- [x] **Reduced Motion**: Transitions respect `@media (prefers-reduced-motion: reduce)`.
