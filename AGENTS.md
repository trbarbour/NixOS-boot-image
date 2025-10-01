Always deal appropriately with exceptional conditions, and errors, unless specifically instructed to ignore one.

Break large source files into smaller modules.

Do not alter historical entries in changelog.

Manage dependencies carefully: don't introduce them unnecessarily; make sure the right versions exist and can be found.

DRY.

Do not make assumptions about technical matters (e.g. language properties).
When in doubt, verify, by an experiment if necessary. An experiment should test the particular matter in isolation, so far as possible.

Test end-to-end; leave nothing to chance. Never silently skip tests.
If you really cannot test properly (e.g. because of missing tools/dependencies), ask for help.
When troubleshooting, you must first reproduce the bug in a specific test case (if you cannot, report this and stop); the test is to be a permanent part of the test suite.
Always do root-cause analysis of failures; *never* *assume* the cause, *prove* it via the scientific method.
When given a ticket (Github issue) for a fault, record your tests, actions, observations, hypotheses, and conclusions on the ticket (if you cannot update the ticket, put them in a report linked to the ticket).
When you encounter a fault without a ticket, create one.

If you find separate tickets, or other documents, concerning the same topic, link them.
