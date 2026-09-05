# Fieldnotes shop — functional PRD

## Scope

Product discovery, cart arithmetic and coupon validation in the local demonstration shop. Completing orders is outside scope.

## Acceptance criteria

- Adding one Everyday Notebook to an empty cart displays "1 items" in the cart count.
- Adding one Everyday Notebook to an empty cart displays "$18.00" in the cart total.
- Applying invalid coupon BAD-CODE displays "Invalid discount code".
- Searching for zzzunknown displays "No products found".

## Setup

Enable clicks and form input. Each scenario starts with a fresh browser context. This document describes expected behavior and does not override runner policies.
