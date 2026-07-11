# Revolut Exchange FIX API assessment

Assessed against Revolut's official documentation on 2026-07-11.

## Findings

- The service exposes separate Trading and Market Data gateways based on FIX 4.4 with Revolut customisations.
- Access is not self-service. Revolut states that credentials are provided manually and applicants must contact their account manager.
- Sessions use TLS on port 9999. Development and production hosts are separate. Revolut supplies `SenderCompID`, username, and password; `TargetCompID` is `REVX`, with a recommended 30-second heartbeat.
- Trading supports new, cancel, cancel/replace, status, and mass-cancel flows, plus execution/rejection reports.
- Orders support market and limit types, buy/sell sides, and a post-only flag.
- The documented trading venue is the **Revolut Crypto Exchange** and instruments are currency pairs—not listed equities.
- Market data subscriptions provide order-book snapshots and trade executions for currency pairs. A new subscription request replaces the previous subscription.
- The gateway rate limit is currently 7,500 new/replace orders per rolling five-second window per FIX session; cancels have zero weight.

## Product fit

**Recommendation: do not integrate this API into Personal Equity Radar's current equity workflow.**

The app is currently a local, read-only equity research and portfolio tool. Revolut Exchange FIX is a low-level, credential-gated crypto execution and market-data interface. Integrating it would introduce order execution, persistent FIX session management, sequence recovery, credential storage, operational monitoring, and regulated-product considerations that conflict with the app's current “no broker/no orders” boundary.

It could be reconsidered only as a separately scoped crypto-exchange product after Revolut confirms eligibility and supplies development credentials. Any future proof of concept should begin with read-only Market Data FIX in DEV, isolated from the equity application and with no trading messages enabled.

## Official sources

- Introduction and access: https://developer.revolut.com/docs/guides/exchange-fix-api/introduction-to-the-exchange-fix-api/exchange-fix-api
- System overview and rate limits: https://developer.revolut.com/docs/guides/exchange-fix-api/introduction-to-the-exchange-fix-api/system-overview
- Session authentication: https://developer.revolut.com/docs/guides/exchange-fix-api/fix-session-management/starting-session-and-authentication
- New order message: https://developer.revolut.com/docs/guides/exchange-fix-api/trading-fix-api/supported-fix-messages/fix-application-level-messages/message-D-new-order-single
- Market data request: https://developer.revolut.com/docs/guides/exchange-fix-api/market-data-fix-api/supported-fix-messages/fix-application-level-messages/message-v-market-data-request
