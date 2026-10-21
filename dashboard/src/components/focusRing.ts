/**
 * One focus-ring recipe for the whole app.
 *
 * Nothing in LeadForge shipped with a visible keyboard focus state, which made
 * the product unusable without a mouse. Rather than hand-rolling a ring on
 * every button (and forgetting half of them), every interactive component
 * spreads this constant into its `className`.
 *
 * `focus-visible` (not `focus`) means the ring appears for keyboard and
 * assistive-technology users but not on mouse click, which keeps the UI calm
 * for pointer users. The 2px offset keeps the ring off the element's own
 * background so it reads clearly on both white panels and tinted cards.
 */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2";
