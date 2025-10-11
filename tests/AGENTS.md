## Testing

NEVER SKIP TESTS! Never let tests be skipped! Never abort a test, unless it seems unlikely to finish (allow it at least 30 minutes). If a test cannot run, or did not complete, count it as a failure, and record the failure so that it will be addressed.

Test end-to-end; leave nothing to chance. A test that takes a long time (e.g. 15 minutes) is better than not testing adequately.
Write a comprehensive test plan (include it in the project), that starts with downloading and installing tools. Write scripts (preferably nix) to do so, and add them to the project.
Check the output from these scripts, in case some measure (e.g. source a file) is needed to bring tools into scope.
You should have sufficient Internet access to download any tools you need. If not, add the extra DNS domains you need to the list in the test plan, and ask for access.
If you really cannot test properly (e.g. because of missing tools/dependencies), write a report about the difficulties and ask for help.

Make tests pass by changing the code under test, **not** by changing the test. The **only** time you may change a test is if you establish that the test itself is contrary to requirements, or (rarely) technically infeasible. If you change a test, you must report doing so.

If bug(s) are stubborn you should use *half-splitting*.
