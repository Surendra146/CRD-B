# Payment gateway removal

The online payment gateway, checkout, payment webhook, gateway settings API and
gateway toggle have been removed. SaaS subscriptions are now managed manually by
authorized active PlatformStaff. See [MANUAL_SUBSCRIPTIONS.md](MANUAL_SUBSCRIPTIONS.md)
for migration `f91c320ab005`, role grants, lifecycle rules and test commands.

Existing plans, subscription periods, entitlements and invoice records remain.
Invoice reference columns are renamed in place. Applied migrations stay frozen;
the new migration has not been applied automatically.
