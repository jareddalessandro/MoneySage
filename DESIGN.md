# Design System Strategy: The Quantitative Archive

## 1. Overview & Creative North Star
In the world of high-stakes finance, clarity is the ultimate luxury. Most fintech platforms suffer from "Dashboard Fatigue"—a chaotic sprawl of boxes and borders that distract from the core data. 

Our Creative North Star is **"The Quantitative Archive."** This design system rejects the "template" look in favor of an editorial, high-end experience that feels like a bespoke intelligence report rather than a generic app. We achieve this by moving away from traditional grid lines and embracing **Tonal Layering**. By using subtle shifts in background values and intentional asymmetry, we guide the user’s eye to the most critical "Factors" without visual clutter.


---

## 2. Colors
This system is built on a foundation of "Deep Space" depth, using refined Material Design 3 logic to ensure every data point has room to breathe.

*   **Primary Foundation:** The `surface` (`#10131a`) acts as our canvas. It is a deep, immersive charcoal that reduces eye strain during long-form analysis.
*   **The Semantic Spectrum:** 
    *   **Positive (Secondary):** `secondary` (`#40e56c`) is a vibrant, neon-inflected green
    *   **Negative (Tertiary):** `tertiary_container` (`#ff5353`) is a clear, authoritative coral-red 
    *   **Accent (Primary):** `primary` (`#4cd6ff`) is a precision blue used for active states, indicators, and primary navigation.

### The "No-Line" Rule
To achieve a high-end feel, **1px solid borders are prohibited for sectioning.** Do not use lines to separate the sidebar from the main content or to divide cards. Boundaries must be defined solely through background color shifts. For example, a card using `surface_container_high` should sit on a section using `surface_container_low`. 

### The "Glass & Gradient" Rule
Floating panels and high-priority gauges should utilize **Glassmorphism**. Apply `surface_container` colors at 70% opacity with a `24px` backdrop-blur. To provide "visual soul," primary CTAs and hero data visualizations should use a subtle linear gradient from `primary` (`#4cd6ff`) to `primary_container` (`#009dc1`) at a 135-degree angle.

---

## 3. Typography
We utilize a dual-font strategy to balance character with readability.

*   **Display & Headlines (Manrope):** Chosen for its geometric precision. Use `display-lg` (3.5rem) for major price points and `headline-md` (1.75rem) for section titles.
*   **Body & Labels (Inter):** The industry standard for high-density data. `body-md` (0.875rem) is the workhorse for descriptive text, while `label-sm` (0.6875rem) in **All Caps** with 0.1rem tracking is used for metadata like "MARKET CAP" or "P/E RATIO."

**Hierarchy Note:** Large data points (e.g., Stock Price) should always use a higher font weight and a more prominent scale than their descriptive labels to ensure a clear "Data-First" reading order.

---

## 4. Elevation & Depth
Traditional drop shadows are too "heavy" for a sophisticated fintech app. We move beyond them using the following principles:

### The Layering Principle
Depth is achieved by "stacking" surface tiers. 
1.  **Bottom Layer:** `surface` (`#10131a`) - The main app background.
2.  **Mid Layer:** `surface_container_low` (`#191c22`) - Used for large grouping areas or sidebars.
3.  **Top Layer:** `surface_container_high` (`#272a31`) - Used for individual cards and interactive elements.

### Ambient Shadows
If an element must "float" (like a Tooltip or a Modal), use an extra-diffused shadow: `0px 12px 32px rgba(0, 0, 0, 0.4)`. The shadow color should never be pure black; it should be a tinted version of the background to feel like natural ambient light.

### The "Ghost Border" Fallback
If accessibility requires a container definition in high-density areas, use a **Ghost Border**: the `outline_variant` token at **15% opacity**. This provides a hint of structure without breaking the seamless, "no-line" aesthetic.

---

## 5. Components

### Modern Cards
Cards must not have borders. Use `surface_container_high` with a `lg` (0.5rem) roundedness. Spacing within cards should follow the `4` (0.9rem) or `5` (1.1rem) scale to ensure data never feels "squeezed."

### Buttons
*   **Primary:** Gradient of `primary` to `primary_container`. Bold text. `xl` (0.75rem) corner radius.
*   **Secondary:** Ghost style. No background, `outline` color for text, with a `surface_variant` hover state.

### Data Visualizations
*   **Gauges:** Use a thick stroke (8px+) for the arc. The active portion of the gauge should use the `secondary` or `tertiary_container` color based on the rating, with a glow effect (filter: drop-shadow) using the same color at 30% opacity.
*   **Line Charts:** Use the `primary` blue for the main trend line. Fill the area under the line with a gradient from `primary` (20% opacity) to transparent.

---

## 6. Do's and Don'ts

### Do
*   **Use Asymmetry:** Place high-value data points off-center to create a modern, editorial feel.
*   **Embrace Negative Space:** Use the `16` (3.5rem) spacing scale between major sections to let the "Deep Space" background provide breathing room.
*   **Nesting:** Place `surface_container_highest` elements inside `surface_container_low` areas to create a sense of physical importance.

### Don't
*   **Don't use Divider Lines:** Never use a 1px line to separate list items. Use a `0.5rem` vertical gap or a subtle hover state shift.
*   **Don't Use High-Contrast Borders:** Avoid `outline` at 100% opacity; it makes the UI look like a legacy spreadsheet.
*   **Don't Overcrowd:** If a screen feels busy, increase the spacing scale rather than shrinking the typography. The data must feel curated, not dumped.