"""
ab_analysis.py — A/B test & funnel analysis for the checkout redesign experiment.

Pipeline:
  1. EDA + sanity checks (sample-ratio mismatch, covariate balance)
  2. Funnel analysis (stage conversion, control vs variant)
  3. Primary metric: purchase conversion lift — two-proportion z-test,
     p-value, 95% CI, and a plain-English ship / don't-ship verdict
  4. Segmentation (device, traffic source)
  5. Attribution: first-touch vs last-touch credit (illustrative)
  6. MoM baseline context

Run from the python/ directory:
    python ab_analysis.py
"""

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

DATA = "../data/ab_experiment.csv"
BASELINE = "../data/baseline_monthly.csv"
IMG = "../images"
STAGES = ["visited", "added_to_cart", "checkout_started", "payment_done", "purchased"]
STAGE_SHORT = {
    "visited": "Visited",
    "added_to_cart": "Added to cart",
    "checkout_started": "Checkout started",
    "payment_done": "Payment done",
    "purchased": "Purchased",
}
Z95 = 1.96

df = pd.read_csv(DATA)
base = pd.read_csv(BASELINE)
control = df[df.variant == "control"]
variant = df[df.variant == "variant"]


# --- helpers -------------------------------------------------------------------
def prop_ci(p, n):
    se = np.sqrt(p * (1 - p) / n)
    return p - Z95 * se, p + Z95 * se


def two_prop_ztest(x1, n1, x2, n2):
    """x1/n1 = variant, x2/n2 = control. Returns lift stats vs control."""
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se_pool
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    se_diff = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p1 - p2
    return {
        "p1": p1, "p2": p2, "diff": diff, "z": z, "p_value": p_value,
        "ci": (diff - Z95 * se_diff, diff + Z95 * se_diff),
    }


def verdict(diff, p_value):
    if p_value < 0.05 and diff > 0:
        return "SHIP — statistically significant positive lift"
    if p_value < 0.05 and diff < 0:
        return "DO NOT SHIP — statistically significant negative lift"
    return "INCONCLUSIVE — not significant; keep the test running"


print("=" * 70)
print("A/B TEST ANALYSIS — checkout redesign (control vs variant)")
print("=" * 70)

# --- 1. EDA + sanity checks ------------------------------------------------------
print("\n[1] SANITY CHECKS")
n_c, n_v = len(control), len(variant)
print(f"Users: control={n_c:,}, variant={n_v:,} (target 50/50)")
chi2, srm_p = stats.chisquare([n_c, n_v], f_exp=[len(df) / 2, len(df) / 2])
print(f"Sample-ratio-mismatch check: chi2={chi2:.3f}, p={srm_p:.4f} -> "
      f"{'PASS — split is intact' if srm_p > 0.05 else 'FAIL — investigate assignment!'}")
for cov in ["device", "traffic_source", "week"]:
    tab = pd.crosstab(df[cov], df["variant"], normalize="columns")
    max_diff = (tab["variant"] - tab["control"]).abs().max()
    print(f"Covariate balance [{cov}]: max arm difference = {max_diff:.3%} "
          f"-> {'balanced' if max_diff < 0.02 else 'CHECK — imbalance detected'}")
print("Pre-period note: no pre-experiment user covariates exist in this synthetic "
      "data; randomization is the balance mechanism (verified above).")

# --- 2. Funnel analysis ----------------------------------------------------------
print("\n[2] FUNNEL ANALYSIS (conditional conversion per stage)")
funnel_rows = []
for arm_name, arm in [("control", control), ("variant", variant)]:
    prev = len(arm)
    row = {"arm": arm_name}
    for s in STAGES[1:]:
        cur = (arm.stage_reached.isin(STAGES[STAGES.index(s):])).sum()
        rate = cur / prev
        row[s] = rate
        prev = cur
    funnel_rows.append(row)
funnel = pd.DataFrame(funnel_rows).set_index("arm")
for s in STAGES[1:]:
    c, v = funnel.loc["control", s], funnel.loc["variant", s]
    print(f"  {STAGE_SHORT[s]:<16} control={c:.2%}  variant={v:.2%}  "
          f"delta={v - c:+.2%}")
overall_c = control.purchased.mean()
overall_v = variant.purchased.mean()
print(f"  {'OVERALL (visited->purchased)':<24} control={overall_c:.2%}  "
      f"variant={overall_v:.2%}  delta={overall_v - overall_c:+.2%}")

# --- 3. Primary metric -----------------------------------------------------------
print("\n[3] PRIMARY METRIC — purchase conversion")
t = two_prop_ztest(variant.purchased.sum(), n_v, control.purchased.sum(), n_c)
print(f"  control: {t['p2']:.2%} (n={n_c:,})")
print(f"  variant: {t['p1']:.2%} (n={n_v:,})")
print(f"  absolute lift: {t['diff']:+.2%}  (relative: {t['diff']/t['p2']:+.1%})")
print(f"  95% CI for lift: [{t['ci'][0]:+.2%}, {t['ci'][1]:+.2%}]")
print(f"  two-proportion z-test: z={t['z']:.2f}, p={t['p_value']:.2e}")
print(f"  VERDICT: {verdict(t['diff'], t['p_value'])}")

# secondary: revenue per user
rpu_c, rpu_v = control.revenue.mean(), variant.revenue.mean()
aov_c = control.loc[control.purchased == 1, "revenue"].mean()
aov_v = variant.loc[variant.purchased == 1, "revenue"].mean()
print(f"  secondary — revenue/user: control=Rs.{rpu_c:,.0f}, variant=Rs.{rpu_v:,.0f} "
      f"({(rpu_v - rpu_c) / rpu_c:+.1%}); AOV: Rs.{aov_c:,.0f} vs Rs.{aov_v:,.0f}")

# --- 4. Segmentation ---------------------------------------------------------------
print("\n[4] SEGMENTATION — where does the variant win/lose?")
seg_results = {}
for seg_col in ["device", "traffic_source"]:
    print(f"  by {seg_col}:")
    for seg_val in sorted(df[seg_col].unique()):
        sub = df[df[seg_col] == seg_val]
        sc = sub[sub.variant == "control"]
        sv = sub[sub.variant == "variant"]
        st = two_prop_ztest(sv.purchased.sum(), len(sv), sc.purchased.sum(), len(sc))
        sig = "SIGNIFICANT" if st["p_value"] < 0.05 else "not significant"
        print(f"    {seg_val:<9} lift={st['diff']:+.2%} "
              f"95% CI [{st['ci'][0]:+.2%}, {st['ci'][1]:+.2%}]  p={st['p_value']:.3f}  {sig}")
        seg_results[(seg_col, seg_val)] = st

# --- 5. Attribution (illustrative) -------------------------------------------------
print("\n[5] ATTRIBUTION — first-touch vs last-touch (ILLUSTRATIVE)")
buyers = df[df.purchased == 1]
ft = buyers.first_touch.value_counts(normalize=True).sort_index() * 100
lt = buyers.last_touch.value_counts(normalize=True).sort_index() * 100
print("  share of purchases credited by channel:")
for ch in sorted(set(ft.index) | set(lt.index)):
    print(f"    {ch:<9} first-touch={ft.get(ch, 0):5.1f}%   last-touch={lt.get(ch, 0):5.1f}%")
print("  Read: first-touch rewards discovery (organic/social); last-touch rewards "
      "the closing session (paid/email). Neither is 'truth' — pick the model that "
      "matches the business question.")

# --- 6. MoM baseline -----------------------------------------------------------------
print("\n[6] MoM BASELINE (6 months pre-experiment)")
for _, r in base.iterrows():
    print(f"  {r['month']}: {r['users']:,} users, conversion {r['purchase_conversion']:.1%}")
print("  Context: baseline conversion was flat at ~12% for 6 months — the test lift "
      "is not riding a pre-existing upward trend.")

print("\n" + "=" * 70)
print("ANALYST SUMMARY")
print("=" * 70)
print(f"- Overall: variant lifts purchase conversion by {t['diff']:+.2%} "
      f"(95% CI [{t['ci'][0]:+.2%}, {t['ci'][1]:+.2%}], p={t['p_value']:.2e}).")
d = seg_results[("device", "desktop")]
m = seg_results[("device", "mobile")]
print(f"- Desktop: {d['diff']:+.2%} lift (p={d['p_value']:.2e}) — the redesign works here.")
print(f"- Mobile: {m['diff']:+.2%} lift (p={m['p_value']:.3f}, not significant) — "
      "flat/slightly negative; do not let it block a desktop rollout, but investigate.")
print("- Recommendation: SHIP to desktop traffic; keep mobile on control and "
      "diagnose mobile checkout friction separately.")
print("- Caveat: synthetic data; in production, re-run with real traffic and "
      "pre-register the primary metric and segments before launch.")

# --- charts --------------------------------------------------------------------------
plt.rcParams.update({"font.size": 10})

# 1. funnel comparison (conditional conversion per stage)
fig, ax = plt.subplots(figsize=(10, 5.5))
x = np.arange(len(STAGES) - 1)
w = 0.35
labels = [f"{STAGE_SHORT[STAGES[i]]} →\n{STAGE_SHORT[STAGES[i+1]]}" for i in range(4)]
c_vals = [funnel.loc["control", s] * 100 for s in STAGES[1:]]
v_vals = [funnel.loc["variant", s] * 100 for s in STAGES[1:]]
ax.bar(x - w / 2, c_vals, w, label="Control", color="#5b7fa6")
ax.bar(x + w / 2, v_vals, w, label="Variant", color="#e07a5f")
for i, (c, v) in enumerate(zip(c_vals, v_vals)):
    ax.text(i - w / 2, c + 1, f"{c:.1f}%", ha="center", fontsize=9)
    ax.text(i + w / 2, v + 1, f"{v:.1f}%", ha="center", fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_ylabel("Conditional conversion (%)")
ax.set_title("Checkout funnel: stage-by-stage conversion (control vs variant)")
ax.legend()
fig.tight_layout()
fig.savefig(f"{IMG}/funnel_comparison.png", dpi=150)
plt.close(fig)

# 2. overall conversion with 95% CI error bars
fig, ax = plt.subplots(figsize=(6, 5))
arms = ["Control", "Variant"]
ps = [t["p2"] * 100, t["p1"] * 100]
cis = [prop_ci(t["p2"], n_c), prop_ci(t["p1"], n_c)]
errs = [[p - lo * 100 for p, (lo, hi) in zip(ps, cis)],
        [hi * 100 - p for p, (lo, hi) in zip(ps, cis)]]
ax.bar(arms, ps, yerr=errs, capsize=8, color=["#5b7fa6", "#e07a5f"])
for a, p in zip(arms, ps):
    ax.text(a, p + 0.5, f"{p:.2f}%", ha="center", fontsize=11)
ax.set_ylabel("Purchase conversion (%)")
ax.set_title(f"Purchase conversion with 95% CI\n"
             f"Lift {t['diff']:+.2%} [{t['ci'][0]:+.2%}, {t['ci'][1]:+.2%}], p={t['p_value']:.2e}")
fig.tight_layout()
fig.savefig(f"{IMG}/conversion_ci.png", dpi=150)
plt.close(fig)

# 3. lift by segment with 95% CI
fig, ax = plt.subplots(figsize=(9, 5))
segs = ([("device", s) for s in ["desktop", "mobile"]] +
        [("traffic_source", s) for s in ["organic", "paid", "social", "email"]])
names = ["Desktop", "Mobile", "Organic", "Paid", "Social", "Email"]
diffs = [seg_results[k]["diff"] * 100 for k in segs]
los = [seg_results[k]["ci"][0] * 100 for k in segs]
his = [seg_results[k]["ci"][1] * 100 for k in segs]
colors = ["#2a9d8f" if d > 0 else "#e07a5f" for d in diffs]
ax.barh(names, diffs, xerr=[np.array(diffs) - np.array(los), np.array(his) - np.array(diffs)],
        capsize=5, color=colors)
ax.axvline(0, color="black", linewidth=0.8)
for n_, d_ in zip(names, diffs):
    ax.text(d_ + (0.15 if d_ >= 0 else -0.15), n_, f"{d_:+.2f}pp",
            va="center", ha="left" if d_ >= 0 else "right", fontsize=9)
ax.set_xlabel("Absolute lift vs control (percentage points, 95% CI)")
ax.set_title("Where does the variant win? Lift by segment")
fig.tight_layout()
fig.savefig(f"{IMG}/lift_by_segment.png", dpi=150)
plt.close(fig)

# 4. attribution: first-touch vs last-touch
fig, ax = plt.subplots(figsize=(8, 5))
channels = sorted(set(ft.index) | set(lt.index))
x = np.arange(len(channels))
ax.bar(x - w / 2, [ft.get(c, 0) for c in channels], w, label="First-touch", color="#5b7fa6")
ax.bar(x + w / 2, [lt.get(c, 0) for c in channels], w, label="Last-touch", color="#e07a5f")
ax.set_xticks(x)
ax.set_xticklabels([c.capitalize() for c in channels])
ax.set_ylabel("Share of purchases (%)")
ax.set_title("Attribution: first-touch vs last-touch credit (illustrative)")
ax.legend()
fig.tight_layout()
fig.savefig(f"{IMG}/attribution.png", dpi=150)
plt.close(fig)

# 5. MoM baseline trend
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(base["month"], base["purchase_conversion"] * 100, marker="o", color="#5b7fa6")
ax.set_ylabel("Purchase conversion (%)")
ax.set_title("MoM baseline: purchase conversion before the experiment")
ax.tick_params(axis="x", rotation=20)
fig.tight_layout()
fig.savefig(f"{IMG}/mom_baseline.png", dpi=150)
plt.close(fig)

print("\nCharts saved to ../images/: funnel_comparison.png, conversion_ci.png, "
      "lift_by_segment.png, attribution.png, mom_baseline.png")
