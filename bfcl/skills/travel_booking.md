---
description: Tool reference for TravelAPI — available flight booking and travel management operations
when-to-use: When starting any travel booking task involving TravelAPI tools — call this before your first tool call to check available operations and their exact parameters
---

# TravelAPI Tool Reference

Available tools (18 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `authenticate_travel` | Log in and get access token | `client_id` (str), `client_secret` (str), `refresh_token` (str), `grant_type` (str), `user_first_name` (str), `user_last_name` (str) |
| `travel_get_login_status` | Check login status | — |
| `verify_traveler_information` | Verify passport/traveler info | `first_name` (str), `last_name` (str), `date_of_birth` (str: 'YYYY-MM-DD'), `passport_number` (str) |
| `list_all_airports` | List all available airports | — |
| `get_nearest_airport_by_city` | Find airport code by city name | `location` (str) → returns 3-letter airport code |
| `get_flight_cost` | Get flight price | `travel_from` (str: **airport code**), `travel_to` (str: **airport code**), `travel_date` (str: 'YYYY-MM-DD'), `travel_class` (str: 'economy'/'business') |
| `book_flight` | Book a flight | `access_token` (str), `card_id` (str), `travel_date` (str: 'YYYY-MM-DD'), `travel_from` (str: airport code), `travel_to` (str: airport code), `travel_class` (str) |
| `cancel_booking` | Cancel a booking | `access_token` (str), `booking_id` (str) |
| `get_booking_history` | Get all past bookings | `access_token` (str) |
| `retrieve_invoice` | Get invoice for a booking | `access_token` (str), `booking_id` (str, optional), `insurance_id` (str, optional) |
| `purchase_insurance` | Buy travel insurance | `access_token` (str), `insurance_type` (str), `insurance_cost` (float), `booking_id` (str), `card_id` (str) |
| `contact_customer_support` | Contact support | `booking_id` (str), `message` (str) |
| `register_credit_card` | Add a credit card | `access_token` (str), `card_number` (str), `expiration_date` (str), `cardholder_name` (str), `card_verification_number` (str) |
| `get_all_credit_cards` | List all registered cards | — |
| `get_credit_card_balance` | Check card balance | `access_token` (str), `card_id` (str) |
| `set_budget_limit` | Set a travel budget limit | `access_token` (str), `budget_limit` (float) |
| `get_budget_fiscal_year` | Get budget info | `lastModifiedAfter` (str, optional), `includeRemoved` (bool, optional) |
| `compute_exchange_rate` | Convert currency | `base_currency` (str), `target_currency` (str), `value` (float) |

## Important Rules

- **No `update_booking`**: Modifying existing bookings is not supported; cancel and rebook instead.
- **No `check_in`**: Online check-in is not available.
- **No `seat_selection`**: Seat preferences cannot be set via API.
- **No `book_hotel`/`car_rental`**: Only flight booking is supported.
- **No `track_flight`/`flight_status`**: Real-time tracking is not supported.
- **No `get_loyalty_points`**: Loyalty program is not supported.
- **`get_flight_cost` and `book_flight` require airport codes**: Use `get_nearest_airport_by_city` first if given city names.
- **`travel_date` format**: Always use 'YYYY-MM-DD'.

## Missing Tool Behavior

If the user requests an operation not in the table above, **do not call any tool**. Respond that the required tool is not available in the current TravelAPI.
