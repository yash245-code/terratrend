# TerraTrend Design System — Earthy Palette & Production Token Reference

TerraTrend utilizes an organic **Earthy Palette** rooted in natural agronomic tones: Herb, Gleam, Pearl, Radiate, and Moss. The design system is implemented with **CSS custom properties** as a single source of truth in `frontend/css/theme.css`.

---

## 1. Core Brand & Functional Palette

| Token Name | Hex Code | Visual Role | Contrast / Rules |
| :--- | :---: | :--- | :--- |
| **Pearl** (`--pearl`, `--bg`) | `#FFFDDD` | Light mode primary background canvas | Warm off-white surface |
| **Deep Moss** (`--bg` dark) | `#142004` | Dark mode primary background canvas | Deep organic night tone |
| **Moss** (`--moss`, `--text`) | `#1E3006` | Primary body text in light mode; dark mode card surface | 13.74:1 on Pearl |
| **Herb** (`--herb`) | `#6A8042` | Vegetation tone, strong input outlines | Natural leaf green |
| **Herb Deep** (`--herb-deep`) | `#566B33` | Secondary button fills, dark badges | 5.74:1 with Pearl |
| **Radiate** (`--radiate`, `--primary`) | `#ED7A13` | Primary action button fill | 4.99:1 with Moss text |
| **Radiate Deep** (`--radiate-deep`) | `#B35500` | Text links, focus indicators in light mode | 4.83:1 on Pearl |
| **Gleam** (`--gleam`) | `#FFE787` | Moderate status badge, dark mode focus indicator | Warm sun yellow |
| **Water** (`--water`, `--viz-water`)| `#2F6F8F` | Rainfall, soil moisture, and hydrological metrics | Muted river blue |
| **Clay Red** (`--clay-red`, `--danger`) | `#B3382C` | High-risk alerts, destructive actions, C2 cost overruns | Earth terracotta |

---

## 2. Approved Color Pairings & Measured Contrast Ratios

All tokens are verified computationally via `scripts/check_contrast.py`:

```
=======================================================
 Checking LIGHT Theme Contrast (WCAG 2.2)
=======================================================
Foreground         Background       Ratio    Req    Result   Description
--------------------------------------------------------------------------------
--text             --bg             13.74:1  4.5:1  PASS     Body text on page background
--text             --surface        14.18:1  4.5:1  PASS     Body text on card surface
--text-muted       --bg              7.20:1  4.5:1  PASS     Muted text on page background
--text-muted       --surface         7.43:1  4.5:1  PASS     Muted text on card surface
--on-primary       --primary         4.99:1  4.5:1  PASS     Text on primary action button
--on-secondary     --secondary       5.74:1  4.5:1  PASS     Text on secondary action button
--on-danger        --danger          5.97:1  4.5:1  PASS     Text on danger action button
--link             --bg              4.83:1  4.5:1  PASS     Text link on page background
--good-ink         --good-bg        11.42:1  4.5:1  PASS     Good status badge text on background
--moderate-ink     --moderate-bg    11.50:1  4.5:1  PASS     Moderate status badge text on background
--poor-ink         --poor-bg         7.54:1  4.5:1  PASS     Poor status badge text on background
--info-ink         --info-bg        10.06:1  4.5:1  PASS     Info status badge text on background

=======================================================
 Checking DARK Theme Contrast (WCAG 2.2)
=======================================================
Foreground         Background       Ratio    Req    Result   Description
--------------------------------------------------------------------------------
--text             --bg             16.43:1  4.5:1  PASS     Body text on page background
--text             --surface        13.74:1  4.5:1  PASS     Body text on card surface
--text-muted       --bg             10.00:1  4.5:1  PASS     Muted text on page background
--text-muted       --surface         8.36:1  4.5:1  PASS     Muted text on card surface
--on-primary       --primary         4.99:1  4.5:1  PASS     Text on primary action button
--on-secondary     --secondary       6.44:1  4.5:1  PASS     Text on secondary action button
--on-danger        --danger          5.71:1  4.5:1  PASS     Text on danger action button
--link             --bg              5.97:1  4.5:1  PASS     Text link on page background
--good-ink         --good-bg         9.65:1  4.5:1  PASS     Good status badge text on background
--moderate-ink     --moderate-bg     6.98:1  4.5:1  PASS     Moderate status badge text on background
--poor-ink         --poor-bg         5.25:1  4.5:1  PASS     Poor status badge text on background
--info-ink         --info-bg         7.55:1  4.5:1  PASS     Info status badge text on background
```

---

## 3. Usage Guidelines

### Rules to Respect
1. **Never use Radiate (`#ED7A13`) for text on light backgrounds**: The contrast of `#ED7A13` on `#FFFDDD` is only 2.8:1 (failing WCAG). Always use **Radiate Deep** (`#B35500`) for text and links on light surfaces (4.83:1).
2. **Always pair fills with designated ink tokens**:
   - Primary buttons: `--primary` background paired with `--on-primary` text (`#1E3006`).
   - Secondary buttons: `--secondary` background paired with `--on-secondary` text.
   - Status badges: `--good-bg` with `--good-ink`, `--moderate-bg` with `--moderate-ink`, and `--poor-bg` with `--poor-ink`.
3. **Color is never the only signal**: Charts differentiate series with varying line styles (solid, dashed, dotted) and marker shapes (`triangle`, `circle`, `rectRot`). Status tags explicitly state `GOOD`, `MODERATE`, or `POOR`.

### Copy-Paste Component Patterns

#### Primary Action Button
```html
<button type="button" class="btn btn-primary">
  <span>Evaluate Land & Economics</span>
</button>
```

#### Status Badge
```html
<span class="rating-tag good">
  <span>✓</span> <span>GOOD</span>
</span>
```

#### Card Container
```html
<div class="analytics-switch-card">
  <h3 style="color: var(--text);">Card Title</h3>
  <p style="color: var(--text-muted);">Secondary description...</p>
</div>
```

---

## 4. Left-Panel Switchable Micro-Grid Analytics
The empty column on the left beneath the map hosts an interactive multi-tab analytics engine (`#analyticsSwitchCard`):
- **🌱 Eco**: 12-Month seasonal rainfall and temperature climatology.
- **💰 Costs**: CACP Cost $A_2$, Family Labour, Land Rent & Capital ($C_2$), and Gross Revenue.
- **⚖️ P&L**: Monte Carlo P10 (drought), P50 (median), and P90 (favorable) net profit percentiles.
- **📈 Return**: Sensitivity curves across $\pm10\%$ variations in Yield, Mandi Price, and Cultivation Cost.
