# Retail Metric Contracts

Two orders, two captures, two refunds. Capture 100 cents on the first order and 50 on the second. Refund 20 and 10 cents from the first. The net is 120 cents. An extra copy of a payment or delivery event should leave both that total and the two-order denominator unchanged. The [hand-calculated test](tests/test_contracts.py#L34) turns this example into an assertion.

The [SQLite queries](core.py) first select orders mature at the observation cutoff, deduplicate events, and aggregate payments, refunds and fulfillment to one row per order. The comparison query joins the raw event tables at the same cutoff. Each additional matching event can multiply another table's rows.

| Result on 500 fictional orders | One row per eligible order | Raw event join |
| --- | ---: | ---: |
| Count used as denominator | 263 | 678 |
| Count marked delivered | 219 | 555 |
| Net captured cents | 1,965,477 | 4,970,212 |

The [order-level ledger](results/decisions.json) lets you reconcile the 1,965,477 cents. [Recorded totals and cutoff](results/metrics.json)

## Run the reconciliation

The queries run on the SQLite version bundled with Python 3.11.

```bash
python -m unittest discover -s tests -v
python run.py --output runs/local
```

[Data card](docs/data-card.md) · [Run manifest](results/manifest.json) · [Source and contribution notes](docs/provenance.md)
