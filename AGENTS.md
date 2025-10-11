## Design

Break large source files into smaller modules.

Manage dependencies carefully: don't introduce them unnecessarily; make sure the right versions exist and can be found.

Do not make assumptions about technical matters (e.g. language properties).
When in doubt, verify, by an experiment if necessary. An experiment should test the particular matter in isolation, so far as possible.


## Programming

DRY.

Always deal appropriately with exceptional conditions, and errors, unless specifically instructed to ignore one.


## Troubleshooting / Debugging

It is okay to start by "milking the front-panel", but if the bug(s) are stubborn you should plan to systematically use *half-splitting*. How can you tell if bugs are stubborn ? If you have already tried and failed to find them. How can you tell if you have already tried ? By keeping records of your test runs and their outcomes.

When troubleshooting, you must first reproduce the bug in a specific test case (if you cannot, report this and stop); the test is to be a permanent part of the test suite.

Always do root-cause analysis of failures; *never* *assume* the cause, *prove* it via the scientific method.

When given a ticket (Github issue) for a fault, record your tests, actions, observations, hypotheses, and conclusions on the ticket (if you cannot update the ticket, put them in a report linked to the ticket).
When you encounter a fault without a ticket, create one.

If you find separate tickets, or other documents, concerning the same topic, link them.

When you have difficulty making progress, consider how many unknowns you are dealing with, and how to reduce the number of unknowns. Use divide-and-conquer to separate the unknowns so that you can solve them individually. You can write a toy project to resolve one particular unknown in isolation from others. When each unknown has been resolved individually, the combination will be more tractable. At least, record a list of the unknowns, and make a plan for resolving each of them.


# Time

Don't rush. Take time to understand, and do things the right way. Do it once, do it right!

If something is expensive to compute, and you need it as input into code you are experimenting with, don't recompute it for each experiment, save a copy and use it for several experiments.


# Task tracking

It is important not to flounder or get stuck in a loop. Every time you undertake a task, aim to produce at least some useful output. If you could not achieve the goal this time, at least record what you have done, what worked, what did not, and your ideas about why; then someone can take the work forward, instead of it being wasted.

Document your major activities in files in the project, so that you can tell if you are repeating inefficient/fruitless behaviour. Include the actual date-time in each filename, so you can easily view them in chronlogical order.
If you find recurring infelicities (e.g. a build taking too long), make a plan for improving it, and record the plan.

If an anomaly occurs, either address it immediately, or make a record of it, so you can address it later. Do not ignore it.

Keep track of all tasks, so they get done, not skipped/lost. Maintain a queue of tasks to perform. When you see something you need to do, either do it immediately (if straightforward), or document it and put it on the queue.
Each time you start work (on a user query), first check the queue of tasks. If the queue is non-empty, put the user's task on the back of the queue (and tell the user), then work through the queued tasks. Each time you successfully complete a task, move it off the queue.

Do not alter historical entries in changelog.


# Codex environment (For Codex Agent Only)

The Codex environment exposes two optional automation hooks outside the repository itself: a Setup script that runs whenever the project workspace is first created (or restored from cache) and a Maintenance script that runs on every subsequent container start. Write/maintain suitable setup and maintenance helper scripts (in the repository), and I will point the hooks at them. You can configure these scripts so that they will set up everything you need before you start work (next time) on a task for this project. When the scripts run, they have full network access, so can install all necessary tools and dependencies.
