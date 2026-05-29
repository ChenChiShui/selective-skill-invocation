---
description: Memory skill — how to search for available flights correctly
when-to-use: When you need to find available flights for booking or modification. Call this to understand search rules and interpret results correctly.
---

# search_flights

## How to search

- **Direct flight**: `search_direct_flight(origin=..., destination=..., date=...)`
- **One-stop flight**: `search_onestop_flight(origin=..., destination=..., date=...)`
- Date format: YYYY-MM-DD
- Origin/destination: use airport codes (e.g., JFK, SEA, EWR)
- Use `list_all_airports()` if you don't know the airport code

## How to interpret results

- Status **"available"** → can be booked ✓
- Status **"delayed"** or **"on time"** → flight not yet departed but **cannot be booked** ✗
- Status **"flying"** → already departed, **cannot be booked** ✗

## For flight modifications

- New flight must keep the same origin, destination, and trip type
- Kept segments prices are NOT updated to current price
- Basic economy flights **cannot change flights** (only cabin)
