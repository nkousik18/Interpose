# SLA, SLO, and latency budgets (p99, "<100ms")

## The three letters people mix up

- **SLA (Service Level *Agreement*)**: a promise made to someone external — often with
  consequences (a refund, a penalty clause) if broken. "We guarantee 99.9% uptime or you get
  credited." It's a business/contractual concept.
- **SLO (Service Level *Objective*)**: an internal target a team holds itself to, usually
  stricter than the SLA, so they notice trouble before it becomes an SLA breach. "We *aim* for
  99.95% uptime" even if the contract only promises 99.9%.
- **SLI (Service Level *Indicator*)**: the actual metric you measure to know if you're hitting
  the SLO — e.g. "percentage of requests completed under 100ms."

Sentinel is a portfolio project with no paying customers, so there's no real SLA here. What the
scoping doc states are **SLOs** — internal engineering targets — even though people loosely say
"SLA" in casual conversation. Knowing the distinction is exactly the kind of thing that reads
as senior in an interview.

## Why latency gets stated as a percentile, not an average

The scoping doc's target is "p99 < 100ms" — the 99th percentile of added latency should be
under 100 milliseconds. Not "the average call adds 100ms."

Averages hide the calls that matter most. Imagine 1,000 calls where 990 add 5ms and 10 add
2,000ms. The *average* looks fine (~25ms). But if you're one of the unlucky 10, the system was
unusably slow for you — and in a proxy that sits in front of every single agent tool call,
those slow outliers are exactly the ones likely to cause a human to notice something's wrong,
or a chained agent workflow to time out. Percentiles (p50/p95/p99) describe the *shape* of the
distribution instead of collapsing it into one number that erases the tail.

"p99 < 100ms" reads as: *"99 times out of 100, this adds less than 100ms. The worst 1% might be
slower, and here's how much slower we tolerate before it's a problem."*

## Why Sentinel cares about latency at all

Sentinel adds itself into the path of *every* tool call an agent makes. If it adds meaningful
delay, it makes every agent workflow built on top of it slower — a bad trade for a governance
layer whose value proposition is "you get this for basically free." The 100ms budget isn't
arbitrary; Section 6.18 of the scoping doc breaks down exactly where that budget goes (parsing
the request, evaluating policy, writing the audit intent record, forwarding, etc.) — we'll
revisit that concretely when we build the gateway's request lifecycle in Week 1.

## Related

- [[02-sentinel-gateway-overview]] — the "data plane" is exactly the part this latency budget
  applies to; the control and analytics planes are explicitly allowed to be slower.
