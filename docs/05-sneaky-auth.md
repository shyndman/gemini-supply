# Sneaky Auth Prototype

This document captures the design for the experimental, fully automated metro.ca authentication flow. The prototype lives in `src/gemini_supply/auth_scratch.py` and is exposed via a temporary CLI script entry. Once the flow graduates into the main CLI, both the file and this page can be retired.

## Goals
- Automate the manual `auth-setup` experience by logging into metro.ca before the shopping agent starts.
- Keep the agent blind to login pages and Cloudflare challenges; only deliver authenticated tabs.
- Use Camoufox’s humanization features and a local vision model to mimic human behavior and dodge automation traps.

## High-Level Flow
1. Launch a headed Camoufox context with the following overrides:
   - `humanize=True`
   - `show_cursor=True`
   - `geoIP=True`
   - `proxy={"server": "192.168.86.38:39609"}`
   - `enforce_restrictions=False` (login routes must remain accessible)
2. Open `https://www.metro.ca`.
3. Dismiss the OneTrust cookie banner (`#onetrust-accept-btn-handler`) via a hover + click.
4. Hover and click the Flyers link (`a[href="/en/flyer"]`). If `CamoufoxHost.is_authenticated()` now returns `True`, stop; the existing session is valid.
5. Otherwise, open the login drawer:
   - Hover + click `.login--btn`.
   - Hover + click the CTA inside `#loginSidePanelForm .cta-basic-primary`.
6. Handle Cloudflare Turnstile on `auth.moiid.ca`:
   - Locate `iframe[id^="cf-chl-widget"]` and capture its bounding box and screenshot.
   - Send the image to a local VLM (`http://ollama-rocm.don/`, `qwen2.5vl:3b`) using `pydantic_ai.Agent` with `BinaryContent`.
   - Receive a bounding box in a 0–1000 coordinate space. Scale to the iframe size, select a random point within the central two-thirds of the box, and click there.
   - Allow up to ~20 attempts with small random jitters; rely on the subsequent page navigation as the success signal. No DOM-based verification step is required.
7. Fill the login form:
   - Credentials come from environment variables `GEMINI_METRO_USERNAME` and `GEMINI_METRO_PASSWORD`. The user resolves these through 1Password CLI secret references before running the script.
   - Hover + focus `#signInName`, type the username, press `Tab`.
   - Focus `#password`, type the password, press `Enter`.
8. Wait for the redirect back to metro.ca and re-run `is_authenticated()` to confirm the session. Close the host when complete.

## Vision Model Service
- Implemented as a LAN microservice; the prototype uses synchronous calls (`Agent.run_sync`) against the local endpoint.
- Example prompt:
  ```python
  result = agent.run_sync(
    [
      "Return the bounding box [x1, y1, x2, y2] of the single unchecked checkbox.",
      BinaryContent(data=screenshot_bytes, media_type="image/png"),
    ]
  )
  ```
- The script converts the 0–1000 coordinates to page space using the iframe dimensions and offsets, then chooses a point in the inner two-thirds rectangle to click.

## CLI Integration
- Add a temporary console script entry (e.g., `gemini-supply-auth-scratch`) in `pyproject.toml`.
- The command runs `auth_scratch.py` directly; no additional flags are required. If future experimentation needs knobs (headless mode, alternate proxy), they can be added ad hoc.

## Future Integration Notes
- Once validated, fold the routine into a `LoginCoordinator` invoked by the `shop` command before the agent runs.
- Provide a `--skip-auto-login` flag for manual fallback; when set, the CLI should launch Camoufox with the current defaults and skip the automated routine.
- After integration, delete the scratch script and this doc to keep the repo tidy.
