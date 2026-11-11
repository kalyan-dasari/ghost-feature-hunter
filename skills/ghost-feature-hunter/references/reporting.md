# Report interpretation

Start with the report summary, then inspect each checkpoint and its evidence. Keep the feature scope and the journey file visible while reviewing. Check whether the environment, account, input data, and assertions match the intended scenario.

For each FAIL, summarize:

1. What behavior was expected, and why that expectation is authoritative.
2. What the adapter observed, including its evidence reference and timestamp.
3. Which source or runtime component may explain the difference.
4. What further check would confirm the suspected root cause.
5. A targeted fix or regression check, without modifying application code before the user approves it.

For each UNKNOWN, name the missing prerequisite or ambiguity and the concrete action that could resolve it. For PASS, describe only the exact assertion that passed. A report with all PASS results does not prove behavior outside its journey.

Recommended compact summary:

```text
Feature: <name and scope>
Results: <PASS> PASS, <FAIL> FAIL, <UNKNOWN> UNKNOWN
Failures: <checkpoint, observed result, evidence reference>
Unverified: <checkpoint and missing prerequisite>
Next step: <targeted action>
```
