---
description: Ask the AEP-X agent crew to do a task in a project (approval required)
argument-hint: "<project name or id> <task>"
---

Use the aepx-ide skill to run an agent task in the AEP-X IDE.

Arguments: $ARGUMENTS — a project (name or id) followed by the task.

1. Find the project (`GET /api/v1/projects`), then create the run with the task.
2. Show the plan steps and ask the user to approve. Do not approve on your own.
3. After the user approves, record the decision, enqueue the run, and poll until it finishes.
4. Show the result. Offer to save code blocks that name a file into the project with `PUT …/files/{path}`.
