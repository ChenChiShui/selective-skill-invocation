---
description: Tool reference for VehicleControlAPI — available vehicle operations
when-to-use: When starting any vehicle control task involving VehicleControlAPI tools — call this before your first tool call to check available operations and their exact parameters
---

# VehicleControlAPI Tool Reference

Available tools (22 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `startEngine` | Start or stop the engine | `ignitionMode` (str: 'START'/'STOP') |
| `displayCarStatus` | Show vehicle status | `option` (str: 'fuel'/'tire'/'engine'/'climate'/'brake'/'all') |
| `display_log` | Show action log | `messages` (list of str) |
| `lockDoors` | Lock or unlock doors | `unlock` (bool), `door` (list: 'driver'/'passenger'/'rear_left'/'rear_right') |
| `activateParkingBrake` | Set parking brake | `mode` (str: 'engage'/'release') |
| `pressBrakePedal` | Press brake pedal | `pedalPosition` (float: 0.0–1.0) |
| `releaseBrakePedal` | Release brake pedal | — |
| `setCruiseControl` | Set cruise control | `speed` (float), `activate` (bool), `distanceToNextVehicle` (float) |
| `setHeadlights` | Control headlights | `mode` (str: 'on'/'off'/'auto') |
| `adjustClimateControl` | Set temperature/fan | `temperature` (float, required), `unit` (str: 'celsius'/'fahrenheit'), `fanSpeed` (int), `mode` (str) |
| `check_tire_pressure` | Check tire pressure | — |
| `fillFuelTank` | Fill fuel tank | `fuelAmount` (float, in gallons) |
| `find_nearest_tire_shop` | Find nearby tire shop | — |
| `set_navigation` | Set GPS destination | `destination` (str) |
| `get_current_speed` | Get current speed | — |
| `estimate_distance` | Estimate distance between two locations | `cityA` (str: **zipcode**), `cityB` (str: **zipcode**) |
| `estimate_drive_feasibility_by_mileage` | Check if trip is feasible with current fuel | `distance` (float, in miles) |
| `get_outside_temperature_from_google` | Get outside temperature | — |
| `get_outside_temperature_from_weather_com` | Get outside temperature | — |
| `get_zipcode_based_on_city` | Get zipcode for a city | `city` (str) |
| `gallon_to_liter` | Convert gallons to liters | `gallon` (float) |
| `liter_to_gallon` | Convert liters to gallons | `liter` (float) |

## Important Rules

- **No `openWindows`/`closeWindows`**: Window control is not supported.
- **No `playMusic`/`setVolume`**: Entertainment system is not supported.
- **No `callPhone`**: Phone/communication is not supported.
- **No `activateWipers`**: Wiper control is not supported.
- **No `openTrunk`/`openHood`/`openSunroof`**: These operations are not supported.
- **`estimate_distance` takes zipcodes**: Pass zipcodes, not city names. Use `get_zipcode_based_on_city` first if given city names.
- **`fillFuelTank` takes gallons**: Use `liter_to_gallon` first if given liters.

## Missing Tool Behavior

If the user requests an operation not in the table above, **do not call any tool**. Respond that the required tool is not available in the current VehicleControlAPI.
