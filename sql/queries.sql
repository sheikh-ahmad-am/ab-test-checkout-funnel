-- =====================================================================
-- A/B Test & Checkout Funnel — SQL verification queries (MySQL 8 compatible)
-- Dataset: data/ab_experiment.csv (20,000 users, 50/50 control vs variant)
-- Table: ab_experiment(user_id, variant, device, traffic_source,
--                      first_touch, last_touch, week, stage_reached,
--                      purchased, revenue)
-- stage_reached order: visited < added_to_cart < checkout_started
--                      < payment_done < purchased
-- Every query below is a SELECT that reproduces a headline number from
-- the README "Results" section (real run 2026-09-26). Significance tests
-- (z-test, p-values, CIs) stay in Python; SQL reproduces the descriptive
-- conversion rates and funnel steps.
-- =====================================================================

-- SETUP (run once in MySQL Workbench; then run the queries below):
--   1. CREATE DATABASE IF NOT EXISTS ab_test;
--      USE ab_test;
--   2. CREATE TABLE ab_experiment (
--          user_id VARCHAR(20),
--          variant VARCHAR(20),
--          device VARCHAR(20),
--          traffic_source VARCHAR(20),
--          first_touch VARCHAR(20),
--          last_touch VARCHAR(20),
--          week INT,
--          stage_reached VARCHAR(20),
--          purchased TINYINT,
--          revenue DECIMAL(10,2)
--      );
--   3. LOAD DATA INFILE '/path/to/ab_experiment.csv'
--      INTO TABLE ab_experiment
--      FIELDS TERMINATED BY ',' IGNORE 1 LINES;

-- ---------------------------------------------------------------------
-- Q1. Purchase conversion by variant + absolute lift in percentage points.
-- What it answers: did the redesigned checkout lift purchases.
-- README link: control 11.98%, variant 14.50%, absolute lift +2.52pp.
-- ---------------------------------------------------------------------
SELECT variant,
       COUNT(*) AS users,
       SUM(purchased) AS purchases,
       ROUND(100.0 * SUM(purchased) / COUNT(*), 2) AS conv_rate_pct
FROM ab_experiment
GROUP BY variant
ORDER BY variant;

SELECT ROUND(
         100.0 * ( SUM(CASE WHEN variant = 'variant' THEN purchased ELSE 0 END)
                 / SUM(CASE WHEN variant = 'variant' THEN 1 ELSE 0 END)
                 - SUM(CASE WHEN variant = 'control' THEN purchased ELSE 0 END)
                 / SUM(CASE WHEN variant = 'control' THEN 1 ELSE 0 END) ),
         2) AS lift_pp
FROM ab_experiment;

-- ---------------------------------------------------------------------
-- Q2. Purchase conversion by device x variant, and lift per device.
-- What it answers: where the variant wins and where it is flat.
-- README link: desktop lift +7.00pp (significant); mobile -0.72pp
-- (not significant) -- the basis for the desktop-only rollout call.
-- ---------------------------------------------------------------------
SELECT device,
       variant,
       COUNT(*) AS users,
       ROUND(100.0 * SUM(purchased) / COUNT(*), 2) AS conv_rate_pct
FROM ab_experiment
GROUP BY device, variant
ORDER BY device, variant;

SELECT device,
       ROUND(
         100.0 * ( SUM(CASE WHEN variant = 'variant' THEN purchased ELSE 0 END)
                 / SUM(CASE WHEN variant = 'variant' THEN 1 ELSE 0 END)
                 - SUM(CASE WHEN variant = 'control' THEN purchased ELSE 0 END)
                 / SUM(CASE WHEN variant = 'control' THEN 1 ELSE 0 END) ),
         2) AS lift_pp
FROM ab_experiment
GROUP BY device
ORDER BY device;

-- ---------------------------------------------------------------------
-- Q3. Funnel step: checkout_started -> payment_done, by variant.
-- What it answers: conditional conversion at the step the redesign targets.
-- README link: control 65.89%, variant 73.95%, delta +8.06pp --
-- "the lift lives in the checkout stages".
-- ---------------------------------------------------------------------
WITH staged AS (
    SELECT variant,
           CASE stage_reached
               WHEN 'visited'          THEN 1
               WHEN 'added_to_cart'    THEN 2
               WHEN 'checkout_started' THEN 3
               WHEN 'payment_done'     THEN 4
               WHEN 'purchased'        THEN 5
           END AS stage_no
    FROM ab_experiment
)
SELECT variant,
       SUM(CASE WHEN stage_no >= 3 THEN 1 ELSE 0 END) AS reached_checkout_started,
       SUM(CASE WHEN stage_no >= 4 THEN 1 ELSE 0 END) AS reached_payment_done,
       ROUND(100.0 * SUM(CASE WHEN stage_no >= 4 THEN 1 ELSE 0 END)
                   / SUM(CASE WHEN stage_no >= 3 THEN 1 ELSE 0 END), 2)
           AS checkout_to_payment_pct
FROM staged
GROUP BY variant
ORDER BY variant;

-- ---------------------------------------------------------------------
-- Q4 (bonus). Full funnel: conditional conversion at every stage, by variant.
-- What it answers: the complete stage-by-stage drop-off comparison.
-- README link: visited->cart 34.10%/34.85% (+0.75pp);
-- cart->checkout 58.13%/61.08% (+2.95pp);
-- checkout->payment 65.89%/73.95% (+8.06pp);
-- payment->purchased 91.76%/92.11% (+0.35pp).
-- ---------------------------------------------------------------------
WITH staged AS (
    SELECT variant,
           CASE stage_reached
               WHEN 'visited'          THEN 1
               WHEN 'added_to_cart'    THEN 2
               WHEN 'checkout_started' THEN 3
               WHEN 'payment_done'     THEN 4
               WHEN 'purchased'        THEN 5
           END AS stage_no
    FROM ab_experiment
),
counts AS (
    SELECT variant,
           SUM(CASE WHEN stage_no >= 1 THEN 1 ELSE 0 END) AS s1_visited,
           SUM(CASE WHEN stage_no >= 2 THEN 1 ELSE 0 END) AS s2_cart,
           SUM(CASE WHEN stage_no >= 3 THEN 1 ELSE 0 END) AS s3_checkout,
           SUM(CASE WHEN stage_no >= 4 THEN 1 ELSE 0 END) AS s4_payment,
           SUM(CASE WHEN stage_no >= 5 THEN 1 ELSE 0 END) AS s5_purchased
    FROM staged
    GROUP BY variant
)
SELECT variant,
       ROUND(100.0 * s2_cart / s1_visited, 2)      AS visited_to_cart_pct,
       ROUND(100.0 * s3_checkout / s2_cart, 2)     AS cart_to_checkout_pct,
       ROUND(100.0 * s4_payment / s3_checkout, 2)  AS checkout_to_payment_pct,
       ROUND(100.0 * s5_purchased / s4_payment, 2) AS payment_to_purchased_pct
FROM counts
ORDER BY variant;
