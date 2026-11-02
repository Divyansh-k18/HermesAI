# Demo script (about 4 minutes)

A walkthrough that shows the whole idea with real data. Everything below runs against the real backend and database.

## Before you start

- Backend and frontend running (see README).
- A fresh account is best. Use a private window.

## 1. Set the scene (30 seconds)

Say: "Most automation tools run in the background and you trust them. Hermes makes each run visible, and puts a person in the loop where it matters. Here is a sales-order flow."

## 2. Load the sample (30 seconds)

1. Register, then create an organization.
2. Open **Workflows** and click **Load sample**.
3. The builder opens with eight steps. Point out the branch: orders over ₹50,000 go to a manager. The top bar shows **active · v1**.

Say: "This version is published and frozen. Editing it creates a new draft, so what ran is always provable."

## 3. A large order pauses (1 minute)

1. Click **Run**. The data is pre-filled with an order of 75,000.
2. Click **Run**. You land on the run page showing **waiting for approval**.
3. Show the step trace: trigger, capture total, condition, then the approval step waiting.
4. Point at the **Approvals** tab badge showing 1.

Say: "The run is parked in the database. Restart the server and it is still here."

## 4. Approve it (30 seconds)

1. Add a comment and click **Approve**.
2. The run continues, marks the order approved, and finishes as **succeeded**.
3. Expand a step to show its input and output.

## 5. Reject another (45 seconds)

1. Go back to the workflow, click **Run**, set the total to 120000, and run it.
2. Click **Reject** with a comment.
3. The run ends as **rejected**. Show that "Mark order approved" never ran.

Say: "A rejected order can never be treated as approved, by design."

## 6. Show the controls and the record (45 seconds)

- Open **Overview**: real counts and the seven-day chart.
- Open **Audit log**: who ran, who decided, with trace IDs.
- Optional: invite a teammate as a member. They can run workflows but cannot see or decide approvals.

## Questions to expect

- **Is it connected to HubSpot, ERPNext, or Gmail?** Not yet. Those steps exist in the builder and fail with a clear message. The connector framework and encrypted credential storage are next.
- **Does it use Temporal?** Not yet. The engine keeps all state in the database and is built with the same step boundaries, so moving to Temporal is a change of runner, not of design.
- **Is it secure?** The foundations are in place: server-side sessions, CSRF, organization isolation, role checks on every action, hashed tokens, and an audit trail. No formal security review has been done.
- **Where is the AI?** Not built yet. The agent step is reserved and fails clearly. Approvals and policy checks come first so AI can be added safely.
