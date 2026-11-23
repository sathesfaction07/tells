# ADR-001: Chrome DevTools Protocol Over Playwright

## Status
Accepted

## Context
Need to intercept network requests from a target web application, evaluate JavaScript in its context, and extract data from multiple internal APIs — all while the user is actively browsing. Options: Playwright, Puppeteer (Node), or raw CDP via WebSocket.

## Decision
Use raw CDP over WebSocket from Python.

## Why

Playwright is designed for automated testing — it owns the browser lifecycle, controls navigation, and expects to be the only thing driving the page. In this use case, the user is already browsing. We need to attach to an existing session without disrupting it.

CDP gives us:
- Attach to a running Chrome instance via `--remote-debugging-port`
- Intercept network requests passively (see what APIs the page calls without injecting a proxy)
- Evaluate JS in the page context to read application state
- No auto-wait, no navigation control overhead — we observe, not drive

Playwright's CDP support exists (`browser.new_cdp_session()`) but it still wants to own the page. Raw WebSocket is cleaner for passive observation.

## Tradeoffs
- No auto-retry on flaky selectors (but we're not selecting elements — we're reading network responses)
- Manual WebSocket lifecycle management (connect, keepalive, reconnect)
- Harder to test (need a mock WebSocket server vs Playwright's built-in test fixtures)
