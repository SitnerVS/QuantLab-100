# Bybit Demo: self-hosted runner setup

## Why this runner is required

Bybit's official V5 integration guide states that API requests from IP addresses located in the United States or Mainland China receive HTTP 403. GitHub-hosted runners can egress from restricted US IP space. The Bybit Demo check therefore runs only on a self-hosted macOS runner using the account owner's own network. No proxy or geolocation workaround is used.

## Security design

- The workflow is manual-only (workflow_dispatch); it is not triggered by pull requests or pushes.
- It checks wallet balance and open linear positions only.
- It does not create, amend, or cancel orders.
- It uses GitHub repository secrets BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET.
- The runner label must include self-hosted, macOS, and quantlab-bybit-demo.
- Do not run untrusted repository code on this machine. Keep the runner dedicated to this repository and stop it when not in use.

## One-time machine setup

1. Open repository Settings -> Actions -> Runners -> New self-hosted runner.
2. Select macOS and follow GitHub's displayed download/configuration commands on the Mac that will host the runner.
3. During configuration, add the custom label quantlab-bybit-demo.
4. Start the runner using the GitHub-provided command.
5. In Actions, select Bybit Demo connection (self-hosted EU runner) and run workflow manually.

GitHub generates a short-lived registration token and displays the exact commands. Never publish that token or the runner's .credentials files.

## Expected result

A successful run uploads bybit-demo-connection-<run> with reports/bybit_demo_connection.json showing environment DEMO, authenticated true, and orders_submitted 0.

If Bybit still rejects the request, stop here and investigate account-region eligibility with Bybit support. Do not use a VPN or proxy to evade regional restrictions.
