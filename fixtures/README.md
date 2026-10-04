# Synthetic fixtures only

`make_demo.py` creates original text-only source in a temporary Git repository.
It exercises immutable Git/blob inspection and the release/staging pipeline.
The simulated review records say **synthetic**, never human audited. No real
Paste Inbox source, user captures, or human approval is included. Zero package
tests are claimed: Depot tests do not execute submitted package code.
