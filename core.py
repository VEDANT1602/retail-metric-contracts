"""Event-grain SQL for mature retail populations and integer-cent money."""
import random
import sqlite3


def whole(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    return value


def database(data):
    orders = data["orders"]
    ids = [r["order_id"] for r in orders]
    if any(not isinstance(i,str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("order identity must be unique nonempty text")
    known_orders=set(ids)
    db = sqlite3.connect(":memory:")
    db.executescript("""
    CREATE TABLE orders(order_id TEXT PRIMARY KEY,accepted_at INTEGER);
    CREATE TABLE payments(event_id TEXT,order_id TEXT,amount_cents INTEGER,observed_at INTEGER);
    CREATE TABLE refunds(event_id TEXT,order_id TEXT,amount_cents INTEGER,observed_at INTEGER);
    CREATE TABLE fulfillment(event_id TEXT,order_id TEXT,status TEXT,observed_at INTEGER);
    """)
    try:
        for row in orders:
            whole(row["accepted_at"], "accepted_at")
            db.execute("INSERT INTO orders VALUES(?,?)", (row["order_id"], row["accepted_at"]))
        for name in ["payments", "refunds", "fulfillment"]:
            seen = {}
            for row in data[name]:
                if not isinstance(row['event_id'],str) or not row['event_id'].strip():
                    raise ValueError("event identity must be nonempty text")
                if not isinstance(row['order_id'],str) or row["order_id"] not in known_orders:
                    raise ValueError("event references unknown order")
                whole(row["observed_at"], "observed_at")
                if row["event_id"] in seen and seen[row["event_id"]] != row:
                    raise ValueError("event identity reused with conflicting content")
                seen[row["event_id"]] = row
                if name == "fulfillment":
                    if row["status"] not in {"delivered", "cancelled"}:
                        raise ValueError("unknown fulfillment status")
                    values = row["event_id"], row["order_id"], row["status"], row["observed_at"]
                else:
                    whole(row["amount_cents"], "amount_cents")
                    values = row["event_id"], row["order_id"], row["amount_cents"], row["observed_at"]
                db.execute(f"INSERT INTO {name} VALUES(?,?,?,?)", values)
        return db
    except BaseException:
        db.close()
        raise


def metrics(data, as_of, maturity=5):
    whole(as_of, "as_of"); whole(maturity, "maturity")
    cutoff = as_of - maturity
    db = database(data)
    try:
        guarded = db.execute("""
        WITH mature AS (SELECT * FROM orders WHERE accepted_at<=?),
        p AS (SELECT order_id,SUM(amount_cents) cents FROM
              (SELECT DISTINCT * FROM payments WHERE observed_at<=?) GROUP BY order_id),
        r AS (SELECT order_id,SUM(amount_cents) cents FROM
              (SELECT DISTINCT * FROM refunds WHERE observed_at<=?) GROUP BY order_id),
        f AS (SELECT order_id,MAX(status='delivered') delivered FROM
              (SELECT DISTINCT * FROM fulfillment WHERE observed_at<=?) GROUP BY order_id)
        SELECT COUNT(*),COALESCE(SUM(COALESCE(f.delivered,0)),0),
               COALESCE(SUM(COALESCE(p.cents,0)),0),COALESCE(SUM(COALESCE(r.cents,0)),0)
        FROM mature o LEFT JOIN p USING(order_id) LEFT JOIN r USING(order_id) LEFT JOIN f USING(order_id)
        """, (cutoff, as_of, as_of, as_of)).fetchone()
        naive = db.execute("""
        SELECT COUNT(*),COALESCE(SUM(CASE WHEN f.status='delivered' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(p.amount_cents),0),COALESCE(SUM(r.amount_cents),0)
        FROM orders o
        LEFT JOIN payments p ON o.order_id=p.order_id AND p.observed_at<=?
        LEFT JOIN refunds r ON o.order_id=r.order_id AND r.observed_at<=?
        LEFT JOIN fulfillment f ON o.order_id=f.order_id AND f.observed_at<=?
        WHERE o.accepted_at<=?
        """, (as_of, as_of, as_of, cutoff)).fetchone()
        def result(row):
            denominator, completed, paid, refunded = map(int, row)
            return {"denominator": denominator, "delivered": completed,
                    "completion_rate": completed / denominator if denominator else None,
                    "captured_cents": paid, "refunded_cents": refunded, "net_cents": paid - refunded}
        # Rows expose order-grain results so an independent consumer can audit aggregates.
        raw = []
        for oid, accepted in db.execute("SELECT * FROM orders WHERE accepted_at<=? ORDER BY order_id", (cutoff,)):
            captured = sum(x[0] for x in db.execute("SELECT amount_cents FROM (SELECT DISTINCT * FROM payments) WHERE order_id=? AND observed_at<=?", (oid, as_of)))
            refunded = sum(x[0] for x in db.execute("SELECT amount_cents FROM (SELECT DISTINCT * FROM refunds) WHERE order_id=? AND observed_at<=?", (oid, as_of)))
            delivered = bool(db.execute("SELECT 1 FROM fulfillment WHERE order_id=? AND status='delivered' AND observed_at<=?", (oid,as_of)).fetchone())
            raw.append({"order_id": oid, "captured_cents": captured, "refunded_cents": refunded, "delivered": delivered})
        return {"as_of":as_of,"maturity_units":maturity,"accepted_cutoff":cutoff,
                "event_grain":result(guarded),"naive_join":result(naive)}, raw
    finally:
        db.close()


def generate():
    rng = random.Random(1602)
    data = {"orders":[],"payments":[],"refunds":[],"fulfillment":[],"as_of":100,"maturity":5}
    for i in range(500):
        oid = f"o{i:04d}"
        accepted = rng.randrange(90, 101)
        cents = rng.randrange(1000, 15000)
        data["orders"].append({"order_id":oid,"accepted_at":accepted})
        payment = {"event_id":f"p{i}","order_id":oid,"amount_cents":cents,"observed_at":accepted}
        data["payments"].append(payment)
        if i % 5 == 0: data["payments"].append(dict(payment))
        status = "cancelled" if i % 7 == 0 else "delivered"
        event = {"event_id":f"f{i}","order_id":oid,"status":status,"observed_at":accepted+2}
        data["fulfillment"].append(event)
        if i % 3 == 0: data["fulfillment"].append(dict(event))
        if i % 4 == 0:
            for j, amount in enumerate([cents//5, cents//10]):
                refund = {"event_id":f"r{i}-{j}","order_id":oid,"amount_cents":amount,"observed_at":accepted+3+j}
                data["refunds"].append(refund)
                if i % 8 == 0: data["refunds"].append(dict(refund))
    return data


def experiment(data):
    result, rows = metrics(data, data["as_of"], data["maturity"])
    report = f"""# Retail metric grain audit

Topic: retail operations. Decision: count mature accepted orders and net captured value without multiplying events through joins.

A raw multi-table join combines payment retries, refunds and delivery events. Its rows are not orders. My SQL first deduplicates event identities, aggregates each stream to order grain, then joins to an explicit accepted-order cohort. Both comparisons use the same as-of cutoff.

In 500 fictional orders, {result['event_grain']['denominator']} meet the maturity rule. The naive join produces {result['naive_join']['denominator']} rows and reports {result['naive_join']['net_cents']} net cents; event-grain SQL reports {result['event_grain']['net_cents']} net cents. Completion is {result['event_grain']['delivered']}/{result['event_grain']['denominator']}. decisions.json preserves one audit row per included order.

Completion means ever observed delivered by the as-of time, including an order with a later cancellation event. This is an explicit historical-delivery metric, not its latest operational status. These are simulated accounting units and a declared operational metric, not recognized revenue under a financial reporting standard. Refund timing, currencies, chargebacks and allocation across multiple merchants would require additional contracts. Next, I would get business owners to approve the population and maturity definition before building a dashboard.
"""
    return result, rows, None, report
