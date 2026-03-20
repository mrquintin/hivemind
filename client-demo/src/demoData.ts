/**
 * Scripted demo scenario: Chicago restaurant strategic decision.
 * One cohesive business case — all conclusions and outputs are pre-coded.
 */

export const SCENARIO = {
  company: "Marco's Table",
  decisionContext:
    "We're a neighborhood restaurant in Chicago (Lakeview) with our lease up in 18 months. Margins are thin and we need to pick one path: (1) Renew the lease and double down on the current concept with a menu refresh and brunch, (2) Open a second, smaller spot—a lunch counter near the Loop to capture office workers—or (3) Pivot toward delivery and catering and shrink dine-in. We have limited capital and need one clear direction.",
} as const;

// Theory network: strategic frameworks assigned to each "unit"
export const THEORY_UNITS = [
  "Porter's Five Forces",
  "Blue Ocean Strategy",
  "Resource-Based View",
  "Real Options (Investment Timing)",
  "Game Theory / Competitive Dynamics",
] as const;

// Practicality network: feasibility evaluation angles (tailored to small business / restaurant)
export const PRACTICALITY_UNITS = [
  "Legal & Licensing",
  "PR & Reputation Risk",
  "Financial Feasibility",
  "Talent & Labor",
  "Operational Capacity",
] as const;

// Client-accessible "data" files (restaurant-relevant)
export const DATA_FILES: { name: string; content: string }[] = [
  {
    name: "sales_breakdown.csv",
    content: `month, dine_in, delivery, catering, total
2024-01, 42000, 8800, 2100, 52900
2024-02, 38500, 9200, 0, 47700
2024-03, 44800, 10100, 3200, 58100
2024-04, 46200, 9500, 2800, 58500
2024-05, 44100, 11200, 4500, 59800
2024-06, 47800, 10800, 5200, 63800`,
  },
  {
    name: "labor_and_costs.txt",
    content: `LABOR (monthly avg)
- FOH: 2 full-time, 4 part-time. Turnover ~40% last 12 mo.
- BOH: 1 head chef, 2 line, 1 prep. Head chef willing to stay if concept grows.
- Total labor % of revenue: 34%.

FIXED COSTS
- Rent: $6,200/mo (lease ends Aug 2026).
- Utilities, insurance, etc.: ~$2,100/mo.`,
  },
  {
    name: "neighborhood_competitors.md",
    content: `# Lakeview / nearby competition (2024)
- 3 other sit-down American/Italian in 4-block radius; we're the only one with a dedicated brunch.
- Two fast-casual lunch spots opened near the Loop in the last year; lunch traffic up.
- One restaurant on our block closed (lease dispute); landlord open to 3-year renewal at +8% or 5-year at +12%.`,
  },
  {
    name: "lease_and_runway.txt",
    content: `Lease: 18 months remaining. Option to renew (see competitors note).
Cash on hand: ~$42k. No line of credit.
Break-even: ~$52k/month revenue. We've been at $53–64k past 6 months.
Second location: rough buildout estimate $80–120k; could do a small lunch counter for ~$60k if we keep menu tight.`,
  },
];

// Initial aggregate conclusions (before revision) — shown in monitor first
export const INITIAL_AGGREGATE_CONCLUSIONS = [
  "Renew lease and double down: add weekend brunch and private events to boost margins; refresh menu and bar program.",
  "Open a small lunch counter near the Loop; keep the current location as dinner flagship and use same brand.",
  "Pivot to delivery and catering as primary revenue; reduce dine-in hours and square footage at renewal.",
  "Hybrid: renew and add brunch first, then evaluate a second location in 12 months if margins improve.",
  "Renegotiate lease for a shorter term and defer big decisions until we have 6 more months of data.",
];

// After one revision: fewer conclusions, equal to sufficiency value (e.g. 2)
export const REVISED_AGGREGATE_CONCLUSIONS = [
  "Recommend renewing the lease and doubling down: add weekend brunch and private events; refresh the menu and bar to differentiate from competitors.",
  "Recommend opening a small lunch counter near the Loop to capture office traffic; keep Lakeview as the dinner flagship and share kitchen talent where possible.",
];

// Feasibility scores per solution, per practicality unit (scripted)
// First run: solution 1 passes (avg >= threshold), solution 2 fails (avg < threshold) → VETO
// Second run: both pass
export const FEASIBILITY_FIRST_RUN: Record<number, number[]> = {
  0: [78, 72, 75, 70, 65], // Solution 1: avg 72
  1: [52, 48, 45, 42, 38], // Solution 2: avg 45 → veto if threshold 60
};

export const FEASIBILITY_SECOND_RUN: Record<number, number[]> = {
  0: [80, 76, 78, 74, 72],
  1: [68, 65, 70, 66, 64],
};

// Final output document (shown in result modal)
export const OUTPUT_DOCUMENT = `HIVEMIND STRATEGIC ANALYSIS — MARCO'S TABLE (CHICAGO)
Generated: Demo Run | Sufficiency: 2 | Feasibility threshold: 60

EXECUTIVE SUMMARY
After theory network debate and practicality verification, the following strategic options are recommended for your Chicago restaurant.

—————————————————————————————————————————————
OPTION A: RENEW & DOUBLE DOWN (PRIMARY RECOMMENDATION)
—————————————————————————————————————————————
Renew the lease and invest in the current concept: add weekend brunch and private events, refresh the menu and bar program to stand out from nearby competitors.

Key steps:
1. Legal: Exercise renewal option; aim for 3-year at +8% to lock in certainty.
2. Operations: Launch brunch (Sat–Sun) with a focused menu; train existing FOH/BOH to cover.
3. Revenue: Add private events (rehearsal dinners, small corporate) — you already have some catering data; formalize a package and price list.
4. Menu: Refresh 4–6 signature items and bar list; keep labor and food cost in check.

Risks mitigated: No second location capital at risk; brunch and events use existing space and help fill slow slots.

—————————————————————————————————————————————
OPTION B: ADD A LUNCH COUNTER NEAR THE LOOP (ALTERNATIVE)
—————————————————————————————————————————————
Open a small lunch counter near the Loop to capture office workers; keep the Lakeview location as the dinner flagship and share kitchen talent where possible.

Key steps:
1. Site: Secure a small footprint (counter + limited seating) within 10 min walk of high-foot-traffic offices.
2. Menu: Keep it tight (5–8 items, same quality as dinner brand) to control labor and food cost.
3. Labor: Cross-train 1–2 from Lakeview; hire 2–3 for the counter. Head chef can oversee both.
4. Capital: Target ~$60k buildout; use cash flow from current location and minimal debt if possible.

Risks mitigated: Second location diversifies revenue; lunch counter has lower fixed cost than full second restaurant.

—————————————————————————————————————————————
CONCLUSION
—————————————————————————————————————————————
Both options passed feasibility. Option A (renew and double down) is recommended as the primary path: it uses the data you already have (catering interest, no brunch competition nearby) and avoids new real estate risk. Option B is a strong alternative if you secure a favorable lease for the counter and can spare the management focus. Pivoting to delivery/catering-only is not recommended given your current labor and space; better to add those revenue streams while keeping dine-in as the anchor.

— End of analysis —`;
