Always deal appropriately with exceptional conditions, and errors, unless specifically instructed to ignore one.

Break large source files into smaller modules.

Do not alter historical entries in changelog.

Manage dependencies carefully: don't introduce them unnecessarily; make sure the right versions exist and can be found.

DRY.

Do not make assumptions about technical matters (e.g. language properties).
When in doubt, verify, by an experiment if necessary. An experiment should test the particular matter in isolation, so far as possible.

NEVER SKIP TESTS! Never let tests be skipped! Never abort a test, unless it seems unlikely to finish (allow it at least 30 minutes). If a test cannot run, or did not complete, count it as a failure, and record the failure so that it will be addressed.

Test end-to-end; leave nothing to chance. A test that takes a long time (e.g. 15 minutes) is better than not testing adequately.
Write a comprehensive test plan (include it in the project), that starts with downloading and installing tools. Write scripts (preferably nix) to do so, and add them to the project.
Check the output from these scripts, in case some measure (e.g. source a file) is needed to bring tools into scope.
You should have sufficient Internet access to download any tools you need. If not, add the extra DNS domains you need to the list in the test plan, and ask for access.
If you really cannot test properly (e.g. because of missing tools/dependencies), write a report about the difficulties and ask for help.

Make tests pass by changing the code under test, *not* by changing the test. The *only* time you may change a test is if you establish that the test itself is contrary to requirements, or (rarely) technically infeasible. If you change a test, you must report doing so.

When troubleshooting, you must first reproduce the bug in a specific test case (if you cannot, report this and stop); the test is to be a permanent part of the test suite.
Always do root-cause analysis of failures; *never* *assume* the cause, *prove* it via the scientific method.

When given a ticket (Github issue) for a fault, record your tests, actions, observations, hypotheses, and conclusions on the ticket (if you cannot update the ticket, put them in a report linked to the ticket).
When you encounter a fault without a ticket, create one.

If you find separate tickets, or other documents, concerning the same topic, link them.

When you have difficulty making progress, consider how many unknowns you are dealing with, and how to reduce the number of unknowns. Use divide-and-conquer to separate the unknowns so that you can solve them individually. You can write a toy project to resolve one particular unknown in isolation from others. When each unknown has been resolved individually, the combination will be more tractable. At least, record a list of the unknowns, and make a plan for resolving each of them.

It is important not to flounder or get stuck in a loop. Every time you undertake a task, aim to produce at least some useful output. If you could not achieve the goal this time, at least record what you have done, what worked, what did not, and your ideas about why; then someone can take the work forward, instead of it being wasted.

Document your major activities in files in the project, so that you can tell if you are repeating inefficient/fruitless behaviour. Include the actual date-time in each filename, so you can easily view them in chronlogical order.
If you find recurring infelicities (e.g. a build taking too long), make a plan for improving it, and record the plan.

If an anomaly occurs, either address it immediately, or make a record of it, so you can address it later. Do not ignore it.

If something is expensive to compute, and you need it as input into code you are experimenting with, don't recompute it for each experiment, save a copy and use it for several experiments (until you get the code right).

Don't rush. Take time to understand, and do things the right way. Do it once, do it right!

Keep track of all tasks, so they get done, not skipped/lost. Maintain a queue of tasks to perform. When you see something you need to do, either do it immediately (if straightforward), or document it and put it on the queue.
Each time you start work (on a user query), first check the queue of tasks. If the queue is non-empty, put the user's task on the back of the queue (and tell the user), then work through the queued tasks.

=== For Codex Agent Only ===
The Codex environment exposes two optional automation hooks outside the repository itself: a Setup script that runs whenever the project workspace is first created (or restored from cache) and a Maintenance script that runs on every subsequent container start. Write/maintain suitable setup and maintenance helper scripts (in the repository), and I will point the hooks at them. You can configure these scripts so that they will set up everything you need before you start work (next time) on a task for this project. When the scripts run, they have full network access, so can install all necessary tools and dependencies.
