"""
generate_ab_data.py — Synthetic e-commerce A/B test dataset.

Experiment: redesigned checkout flow ("variant") vs current flow ("control").
~20,000 users, 50/50 random assignment, seed 42 (fully reproducible).

Baked-in ground truth (unknown to the analyst):
- The redesign lifts purchase conversion by ~+2.5pp overall...
- ...but the lift is concentrated on DESKTOP. Mobile is flat / slightly negative.
- Cart-add behaviour is identical across arms — the lift lives in the
  checkout stages (checkout_started -> payment_done especially).

Outputs (written to the current directory — run this from data/):
- ab_experiment.csv      — one row per user
- baseline_monthly.csv   — 6 months of pre-experiment MoM baseline conversion
"""

import numpy as np
import pandas as pd

SEED = 42
N_USERS = 20_000
rng = np.random.default_rng(SEED)

STAGES = ["visited", "added_to_cart", "checkout_started", "payment_done", "purchased"]

# --- assignment & covariates -------------------------------------------------
variant = rng.choice(["control", "variant"], size=N_USERS, p=[0.5, 0.5])
device = rng.choice(["mobile", "desktop"], size=N_USERS, p=[0.58, 0.42])
traffic_source = rng.choice(
    ["organic", "paid", "social", "email"], size=N_USERS, p=[0.35, 0.30, 0.20, 0.15]
)
week = rng.integers(1, 5, size=N_USERS)  # experiment week 1..4

# --- stage-conditional conversion probabilities --------------------------------
# (p_cart|visited, p_checkout|cart, p_payment|checkout, p_purchased|payment)
STAGE_P = {
    ("control", "mobile"): (0.32, 0.55, 0.62, 0.92),
    ("control", "desktop"): (0.38, 0.62, 0.68, 0.92),
    ("variant", "mobile"): (0.32, 0.55, 0.60, 0.93),
    # variant desktop: the redesign removes desktop checkout friction
    ("variant", "desktop"): (0.38, 0.68, 0.86, 0.93),
}


def furthest_stage(v, d):
    """Simulate one user's funnel progression; return furthest stage reached."""
    p_cart, p_checkout, p_payment, p_purchased = STAGE_P[(v, d)]
    stage = "visited"
    if rng.random() < p_cart:
        stage = "added_to_cart"
        if rng.random() < p_checkout:
            stage = "checkout_started"
            if rng.random() < p_payment:
                stage = "payment_done"
                if rng.random() < p_purchased:
                    stage = "purchased"
    return stage


stage_reached = np.array([furthest_stage(v, d) for v, d in zip(variant, device)])
purchased = (stage_reached == "purchased").astype(int)

# --- revenue (0 unless purchased) ---------------------------------------------
# Lognormal basket sizes; desktop baskets run slightly larger.
mu = np.where(device == "desktop", 7.62, 7.42)
revenue = np.where(
    purchased == 1, np.round(rng.lognormal(mean=mu, sigma=0.55)).astype(int), 0
)

# --- attribution touchpoints (illustrative) -----------------------------------
# last_touch = the session's traffic source;
# first_touch skews toward discovery channels (organic/social).
last_touch = traffic_source.copy()
keep_same = rng.random(N_USERS) < 0.60
discovery = rng.choice(
    ["organic", "social", "paid", "email"], size=N_USERS, p=[0.40, 0.35, 0.15, 0.10]
)
first_touch = np.where(keep_same, traffic_source, discovery)

df = pd.DataFrame(
    {
        "user_id": [f"u{i:06d}" for i in range(N_USERS)],
        "variant": variant,
        "device": device,
        "traffic_source": traffic_source,
        "first_touch": first_touch,
        "last_touch": last_touch,
        "week": week,
        "stage_reached": stage_reached,
        "purchased": purchased,
        "revenue": revenue,
    }
)
df.to_csv("ab_experiment.csv", index=False)
print(f"wrote ab_experiment.csv: {len(df):,} users, "
      f"{purchased.sum():,} purchases ({purchased.mean():.2%} overall)")

# --- MoM baseline: 6 months before the experiment -------------------------------
baseline = pd.DataFrame(
    {
        "month": ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
        "users": [182_000, 188_000, 191_000, 195_000, 201_000, 205_000],
        # flat ~12% purchase conversion — no pre-existing upward trend
        "purchase_conversion": [0.119, 0.121, 0.118, 0.122, 0.120, 0.119],
    }
)
baseline["purchases"] = (baseline["users"] * baseline["purchase_conversion"]).round().astype(int)
baseline.to_csv("baseline_monthly.csv", index=False)
print("wrote baseline_monthly.csv: 6 months of pre-experiment baseline")
