"""Writes the 13 seed trios into golden/trios/.

Every one of these was executed against the DuckDB fixtures before being
committed here: all 13 parse, pass the validator, and return non-empty
results. Metric definitions match semantic/metrics.yaml exactly.

    python scripts/seed_trios.py
"""
import json
import pathlib

null = None

TRIOS = [
  {
    "id": "aov",
    "metrics_used": [
      "aov",
      "revenue"
    ],
    "tables_used": [
      "order_items"
    ],
    "question_variants": [
      "average order value",
      "what is our AOV",
      "how much does a typical order come to",
      "average basket size in money"
    ],
    "sql": "SELECT FORMAT_TIMESTAMP('%Y-%m', oi.created_at) AS month,\n  ROUND(SUM(oi.sale_price) / COUNT(DISTINCT oi.order_id), 2) AS aov\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nWHERE oi.status NOT IN ('Cancelled', 'Returned') AND EXTRACT(YEAR FROM oi.created_at) = 2023\nGROUP BY month ORDER BY month",
    "report": "AOV divides net revenue by DISTINCT orders, not by line items. Averaging sale_price directly gives mean item price, which is a different and usually much smaller number.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "brand_comparison",
    "metrics_used": [
      "revenue",
      "item_return_rate"
    ],
    "tables_used": [
      "order_items",
      "products"
    ],
    "question_variants": [
      "compare two brands",
      "why does one brand outperform another",
      "brand performance"
    ],
    "sql": "SELECT p.brand,\n  COUNT(*) AS items_sold,\n  ROUND(SUM(oi.sale_price), 2) AS revenue,\n  ROUND(AVG(p.retail_price), 2) AS avg_price_point,\n  ROUND(AVG(p.retail_price - p.cost), 2) AS avg_margin,\n  ROUND(100.0 * COUNTIF(oi.status = 'Returned') / COUNT(*), 2) AS return_pct\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.products` AS p ON p.id = oi.product_id\nGROUP BY p.brand ORDER BY revenue DESC",
    "report": "A brand revenue gap has three candidate drivers: units sold, price point, and returns. Pull all three in one query so the comparison can attribute the difference instead of just stating it.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "category_revenue",
    "metrics_used": [
      "revenue"
    ],
    "tables_used": [
      "order_items",
      "products"
    ],
    "question_variants": [
      "revenue by category",
      "which categories sell best",
      "category performance",
      "top product categories"
    ],
    "sql": "SELECT p.category, p.department,\n  COUNT(*) AS items_sold,\n  ROUND(SUM(oi.sale_price), 2) AS revenue\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.products` AS p ON p.id = oi.product_id\nWHERE oi.status NOT IN ('Cancelled', 'Returned')\nGROUP BY p.category, p.department ORDER BY revenue DESC",
    "report": "Category split by department, because the same category name behaves differently across Men and Women lines and a combined figure hides that.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "item_return_rate",
    "metrics_used": [
      "item_return_rate"
    ],
    "tables_used": [
      "order_items"
    ],
    "question_variants": [
      "item return rate",
      "what share of items get returned",
      "return rate by category"
    ],
    "sql": "SELECT p.category,\n  COUNT(*) AS items_sold,\n  ROUND(100.0 * COUNTIF(oi.status = 'Returned') / COUNT(*), 2) AS item_return_rate_pct\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.products` AS p ON p.id = oi.product_id\nGROUP BY p.category HAVING COUNT(*) >= 50 ORDER BY item_return_rate_pct DESC",
    "report": "Item-level return rate. The denominator is every item sold, so cancelled and returned rows stay in it. HAVING guards against tiny categories producing meaningless percentages.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "monthly_revenue",
    "metrics_used": [
      "revenue"
    ],
    "tables_used": [
      "order_items"
    ],
    "question_variants": [
      "monthly revenue",
      "revenue by month",
      "how did revenue trend over the year",
      "show me sales per month"
    ],
    "sql": "SELECT FORMAT_TIMESTAMP('%Y-%m', oi.created_at) AS month,\n  ROUND(SUM(oi.sale_price), 2) AS revenue,\n  COUNT(DISTINCT oi.order_id) AS orders\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nWHERE oi.status NOT IN ('Cancelled', 'Returned') AND EXTRACT(YEAR FROM oi.created_at) = 2023\nGROUP BY month ORDER BY month",
    "report": "Revenue is reported net of cancelled and returned items. Order count is included alongside revenue because a revenue change is only interpretable once you know whether order volume or basket size moved.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "new_buyer_cohorts",
    "metrics_used": [
      "revenue"
    ],
    "tables_used": [
      "order_items",
      "users"
    ],
    "question_variants": [
      "cohort analysis",
      "how do newer customers compare to older ones",
      "signup cohort spending"
    ],
    "sql": "SELECT FORMAT_TIMESTAMP('%Y-%m', u.created_at) AS signup_month,\n  COUNT(DISTINCT u.id) AS signups,\n  COUNT(DISTINCT oi.user_id) AS activated,\n  ROUND(SUM(oi.sale_price) / NULLIF(COUNT(DISTINCT oi.user_id), 0), 2) AS revenue_per_active\nFROM `bigquery-public-data.thelook_ecommerce.users` AS u\nLEFT JOIN `bigquery-public-data.thelook_ecommerce.order_items` AS oi ON oi.user_id = u.id AND oi.status NOT IN ('Cancelled', 'Returned')\nGROUP BY signup_month ORDER BY signup_month",
    "report": "LEFT JOIN keeps cohorts with no purchases, so activation rate is visible. NULLIF guards the division. Recent cohorts have had less time to accumulate spend, which must be stated whenever cohorts are compared.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "order_return_rate",
    "metrics_used": [
      "order_return_rate"
    ],
    "tables_used": [
      "orders"
    ],
    "question_variants": [
      "order return rate",
      "what share of orders come back",
      "how many orders are returned"
    ],
    "sql": "SELECT FORMAT_TIMESTAMP('%Y-%m', o.created_at) AS month,\n  COUNT(*) AS orders,\n  ROUND(100.0 * COUNTIF(o.status = 'Returned') / COUNT(*), 2) AS order_return_rate_pct\nFROM `bigquery-public-data.thelook_ecommerce.orders` AS o\nGROUP BY month ORDER BY month",
    "report": "Order-level return rate, distinct from the item-level metric. An order of four items with one return counts fully here and as 25% there. Always state which one is being reported.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "product_margin",
    "metrics_used": [
      "revenue"
    ],
    "tables_used": [
      "order_items",
      "products"
    ],
    "question_variants": [
      "which products are most profitable",
      "margin by product",
      "best products by profit not revenue"
    ],
    "sql": "SELECT p.id AS product_id, p.name, p.brand, p.category,\n  COUNT(*) AS units,\n  ROUND(SUM(oi.sale_price), 2) AS revenue,\n  ROUND(SUM(oi.sale_price - p.cost), 2) AS gross_profit\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.products` AS p ON p.id = oi.product_id\nWHERE oi.status NOT IN ('Cancelled', 'Returned')\nGROUP BY p.id, p.name, p.brand, p.category\nORDER BY gross_profit DESC LIMIT 20",
    "report": "Ranking on revenue alone promotes high-price low-margin products. Gross profit uses products.cost, which is the only cost field available and is per unit.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "repeat_vs_single",
    "metrics_used": [
      "revenue"
    ],
    "tables_used": [
      "order_items"
    ],
    "question_variants": [
      "repeat customers versus one time buyers",
      "how much comes from repeat business",
      "customer loyalty split"
    ],
    "sql": "WITH per_user AS (\n  SELECT oi.user_id,\n    COUNT(DISTINCT oi.order_id) AS orders,\n    SUM(oi.sale_price) AS spend\n  FROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\n  WHERE oi.status NOT IN ('Cancelled', 'Returned')\n  GROUP BY oi.user_id)\nSELECT CASE WHEN orders = 1 THEN 'single-order' ELSE 'repeat' END AS segment,\n  COUNT(*) AS buyers,\n  ROUND(SUM(spend), 2) AS revenue,\n  ROUND(AVG(spend), 2) AS avg_spend\nFROM per_user GROUP BY segment ORDER BY revenue DESC",
    "report": "Uses a CTE to collapse to one row per buyer before segmenting. Segmenting on the raw item table would count a buyer once per item and distort every average.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "state_spend_comparison",
    "metrics_used": [
      "revenue",
      "aov"
    ],
    "tables_used": [
      "order_items",
      "users"
    ],
    "question_variants": [
      "compare spending between states",
      "why do customers in one state spend less",
      "state by state performance",
      "how does Texas compare to California"
    ],
    "sql": "SELECT u.state,\n  COUNT(DISTINCT u.id) AS buyers,\n  COUNT(DISTINCT oi.order_id) AS orders,\n  ROUND(SUM(oi.sale_price) / COUNT(DISTINCT u.id), 2) AS spend_per_buyer,\n  ROUND(SUM(oi.sale_price) / COUNT(DISTINCT oi.order_id), 2) AS aov,\n  ROUND(COUNT(DISTINCT oi.order_id) / COUNT(DISTINCT u.id), 2) AS orders_per_buyer\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.users` AS u ON u.id = oi.user_id\nWHERE oi.status NOT IN ('Cancelled', 'Returned')\nGROUP BY u.state ORDER BY spend_per_buyer DESC",
    "report": "Comparing states on raw revenue only measures population. Normalise per buyer, then decompose: spend_per_buyer = aov x orders_per_buyer. That decomposition is what turns 'they spend less' into either 'they buy cheaper things' or 'they buy less often' \u2014 the two require different responses.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "top_customers",
    "metrics_used": [
      "revenue"
    ],
    "tables_used": [
      "order_items",
      "users"
    ],
    "question_variants": [
      "top customers",
      "who spends the most",
      "highest value customers",
      "biggest spenders"
    ],
    "sql": "SELECT oi.user_id, u.state, u.traffic_source,\n  ROUND(SUM(oi.sale_price), 2) AS lifetime_value,\n  COUNT(DISTINCT oi.order_id) AS orders\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.users` AS u ON u.id = oi.user_id\nWHERE oi.status NOT IN ('Cancelled', 'Returned')\nGROUP BY oi.user_id, u.state, u.traffic_source\nORDER BY lifetime_value DESC LIMIT 20",
    "report": "Customers are identified by user_id only. Name, email and address are never selected. State and traffic source are included because they are the attributes that make a ranking actionable without identifying anyone.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "traffic_source",
    "metrics_used": [
      "revenue",
      "aov"
    ],
    "tables_used": [
      "order_items",
      "users"
    ],
    "question_variants": [
      "which channel brings the best customers",
      "traffic source performance",
      "acquisition channel value"
    ],
    "sql": "SELECT u.traffic_source,\n  COUNT(DISTINCT u.id) AS buyers,\n  ROUND(SUM(oi.sale_price), 2) AS revenue,\n  ROUND(SUM(oi.sale_price) / COUNT(DISTINCT u.id), 2) AS revenue_per_buyer\nFROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\nJOIN `bigquery-public-data.thelook_ecommerce.users` AS u ON u.id = oi.user_id\nWHERE oi.status NOT IN ('Cancelled', 'Returned')\nGROUP BY u.traffic_source ORDER BY revenue_per_buyer DESC",
    "report": "Channels are judged on revenue per acquired buyer, not total revenue. A channel delivering many low-value buyers can top the raw revenue table while being the worse channel.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  },
  {
    "id": "churn_rate",
    "metrics_used": [
      "churn"
    ],
    "tables_used": [
      "order_items"
    ],
    "question_variants": [
      "churn rate",
      "why did churn spike",
      "how many customers are we losing",
      "customer retention by month",
      "monthly churn trend"
    ],
    "sql": "WITH monthly_active AS (\n  SELECT DISTINCT oi.user_id, FORMAT_TIMESTAMP('%Y-%m', oi.created_at) AS month\n  FROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi\n  WHERE oi.status NOT IN ('Cancelled', 'Returned')\n),\nmonth_pairs AS (\n  SELECT m1.month AS current_month,\n    MIN(m2.month) AS next_month\n  FROM (SELECT DISTINCT month FROM monthly_active) m1\n  JOIN (SELECT DISTINCT month FROM monthly_active) m2 ON m2.month > m1.month\n  GROUP BY m1.month\n)\nSELECT mp.current_month AS month,\n  COUNT(DISTINCT a.user_id) AS active_users,\n  COUNT(DISTINCT CASE WHEN b.user_id IS NULL THEN a.user_id END) AS churned,\n  ROUND(100.0 * COUNT(DISTINCT CASE WHEN b.user_id IS NULL THEN a.user_id END) / NULLIF(COUNT(DISTINCT a.user_id), 0), 2) AS churn_rate_pct\nFROM month_pairs mp\nJOIN monthly_active a ON a.month = mp.current_month\nLEFT JOIN monthly_active b ON b.user_id = a.user_id AND b.month = mp.next_month\nGROUP BY mp.current_month\nORDER BY mp.current_month",
    "report": "Churn rate is the percentage of active users in month M who placed no orders in month M+1. A user who returns in M+2 still counts as churned in M. Always distinguish churn from low activity.",
    "quality_score": 0.9,
    "provenance": "authored",
    "supersedes": null
  }
]

if __name__ == "__main__":
    d = pathlib.Path("golden/trios")
    d.mkdir(parents=True, exist_ok=True)
    for t in TRIOS:
        (d / f"{t['id']}.json").write_text(json.dumps(t, indent=2))
    print(f"wrote {len(TRIOS)} trios to {d}")
