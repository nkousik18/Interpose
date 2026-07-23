"""Root-level test configuration.

Automated tests must never depend on whatever secrets happen to be in a developer's
local `.env` -- the LLM-calling agents (A2/A3/A4) have a documented fallback path for
when no API key is configured (`interpose.control_plane.llm`), and the whole suite
relies on that fallback being exercised deterministically. Without this, a developer
who's added a real `GROQ_API_KEY` for manual smoke-testing (see
concepts/24-narrative-generation-with-a-real-llm.md) would get different test
behavior -- and possibly real, billed API calls -- than CI does. Runs before any test
module is imported, overriding whatever `.env` would otherwise supply.
"""

import os

os.environ["GROQ_API_KEY"] = ""
