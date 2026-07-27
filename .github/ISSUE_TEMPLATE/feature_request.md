---
name: Feature or route request
about: A route, field, or behavior the app has that this library doesn't cover yet
title: ""
labels: enhancement
assignees: ""
---

<!--
DO NOT paste real credentials, cookies, NetFunnel keys, PNRs, card-shaped
values, or raw response bodies from SRT into this issue. It is public.
Sanitize every value below. If you have to share a real response to make the
request concrete, use a GitHub Security Advisory instead, which is private.
-->

**What's missing**

What the app can do that this library can't, or what this library refuses
that you believe the app allows.

**Evidence**

This project implements only what it can evidence — see `CONTRIBUTING.md`'s
"Evidence, not assertion" section. The more of this you can give, the more
directly actionable the request is:

- A `file:line` citation from the decompiled app (a JS bundle path and line
  range), if you have one.
- A sanitized description of a live request/response shape — field *names*,
  not real values.
- Whether this touches a mutation (reserve/cancel/pay/refund/coupon). If so,
  read `CONTRIBUTING.md`'s "Changing the mutation consent / safety model"
  section before proposing an implementation — a mutation category cannot be
  live-enabled without a real live-verified round trip.

**Why it matters**

What you're trying to do that you currently can't.
