# Retail metric grain audit

Topic: retail operations. Decision: count mature accepted orders and net captured value without multiplying events through joins.

A raw multi-table join combines payment retries, refunds and delivery events. Its rows are not orders. My SQL first deduplicates event identities, aggregates each stream to order grain, then joins to an explicit accepted-order cohort. Both comparisons use the same as-of cutoff.

In 500 fictional orders, 263 meet the maturity rule. The naive join produces 678 rows and reports 4970212 net cents; event-grain SQL reports 1965477 net cents. Completion is 219/263. decisions.json preserves one audit row per included order.

Completion means ever observed delivered by the as-of time, including an order with a later cancellation event. This is an explicit historical-delivery metric, not its latest operational status. These are simulated accounting units and a declared operational metric, not recognized revenue under a financial reporting standard. Refund timing, currencies, chargebacks and allocation across multiple merchants would require additional contracts. Next, I would get business owners to approve the population and maturity definition before building a dashboard.
