"""Finance domain services: Payment Structure → Invoice → Payment.

Separation of concerns (spec §4):

* **Payment Structure** (:mod:`.billing`) — what the school charges.
* **Invoice** — the amount one student owes, frozen at issue time.
* **Payment** — money actually received, verified server-side.

Nothing here trusts a client-supplied total or status. Invoice balances are
derived from `Payment` rows in the `VERIFIED` state (spec §10).
"""
