# Retail Metric Contracts

**A dashboard can be mathematically correct and still count the wrong population.**

I made the decision concrete: report completion for mature accepted orders and net captured cents as of one cutoff. Raw joins multiply payment retries, partial refunds and fulfillment events. My framework is **define population → deduplicate event identity → aggregate to order grain → join → audit denominators**.

The implementation executes real SQLite queries against 500 original fictional orders. The comparator uses the same observation and maturity boundaries but directly joins the event tables. [The report](results/report.md) and one-row-per-order audit expose the difference rather than presenting a dashboard with unexplained totals.


## Recorded result

Of 500 fictional orders, **263** meet the maturity contract and **219** were observed delivered. Event-grain SQL reports **1,965,477 net cents**; the raw join reports **4,970,212** over **678 multiplied rows**. The order-level audit reconciles the corrected total. These are simulated cents and a declared operational metric.

## Reproduce and inspect

Python 3.11, CPU only. No API keys, paid services, provider calls, customer records or external data download.

```bash
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run.py --output runs/local
```

`core.py` contains the generator and actual comparison. `data/dataset.json` is the committed original input. `results/decisions.json` preserves the evaluated rows/traces. `results/metrics.json` and `results/report.md` state the measured outcomes. `results/manifest.json` binds core source, input, and output bytes with SHA-256. A fresh run writes to the requested directory and leaves committed results available for comparison.

This is a new independent portfolio experiment. Its results do not establish historical employer/client outcomes, production adoption, or service scale. Read the [data card](docs/data-card.md) and [provenance](docs/provenance.md) before interpreting the numbers.
