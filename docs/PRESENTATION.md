# AIVAR — presentation outline and speaker notes

Six slides for a five-minute technical walkthrough. Use the [jury guide](JURY_GUIDE.md) for the live sequence and [verification](VERIFICATION.md) for current evidence. These are slide-ready contents, not a claim that a slide deck or video has been published.

## Slide 1 — Maintaining tests is a decision problem

**Message:** Developers still coordinate what to test, whether coverage is meaningful, and whether failures need repair or escalation.

Show: URL → test plan → execution → failure → uncertain ownership.

Say: “AIVAR takes responsibility for the transitions, not just generation.” Avoid unsupported industry statistics.

## Slide 2 — One URL, a visible testing lifecycle

Show the README's Mermaid flow: Planner, coverage, Generator, Executor, retry, Healer, Defect Classifier, report and persistent suite.

Explain optional Markdown PRD, focus, interaction permission and separate page/scenario budgets. Show one real assertion and its PRD link.

## Slide 3 — Repair the locator; preserve the expectation

Show a controlled example: `#heading-original` → failure → unchanged retry → `#heading-new` → confirmed pass. Keep the expected text `Catalog` visible on both sides.

Explain unique semantic identity, one repair proposal, full replay and retained screenshots. Then show changed content staying failed. The fixture is deliberate fault injection, not a discovered customer defect.

## Slide 4 — Every run improves the test history

Show the live PRD acceptance result: two cases retained, one added. Existing assertions remain unchanged; a previously unresolved placeholder assertion remains unresolved.

Explain matching by URL/scope/engine/policy, immutable historical snapshots and what “new,” “repaired,” and “regression” mean. Show a remaining coverage gap to make scope visible.

## Slide 5 — Small stack, explicit trade-offs

Show Python/FastAPI, OpenAI structured planning, Playwright, SQLite, plain JavaScript and portable evidence exports.

Explain: V1 keeps the bounded direct workflow; optional V2 adds LangGraph checkpoints and explicit agent contracts. No arbitrary generated code, no automatic business-rule rewriting, no distributed hosting claim.

## Slide 6 — Evidence and next steps

Show verified local browser repair/reuse/regression checks, the current unit-test count from `VERIFICATION.md`, and actual OpenAI outcomes of 1/2 then 2/3 passing. Open the ZIP's `START_HERE.md` and `report.html`.

Next: typed attribute/value assertions, evaluated broader repair, durable jobs, multi-user isolation and measured QA maintenance effort. Close with: “AIVAR provides a maintained suite and an explanation of what is still uncertain.”
