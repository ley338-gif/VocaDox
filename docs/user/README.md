# User docs

Phase 1 status: the only user-facing feature is signing in. The full
conversation workspace (recording, review, documents, ...) ships in later
phases — see the root README's roadmap.

## Signing in

1. Go to `/login`.
2. Enter the username and password your administrator gave you (see
   `docs/admin/README.md` for how the first account is created).
3. On success you land on `/app`, a minimal placeholder home showing who
   you're signed in as, with a **Log out** button. The full workspace
   (Dashboard, Conversations, ...) replaces this in a later phase.

If your username or password is wrong, you'll see a generic "Invalid
username or password" message — the system deliberately doesn't say which
one was wrong, so an attacker can't use the error to guess valid
usernames.

## Staying signed in / signing out

Your session lasts up to 12 hours (server-enforced; not extended by
activity in Phase 1) and is tied to a cookie in your browser — it doesn't
work across different browsers/devices without signing in again in each.
Click **Log out** to end your session immediately; it's also invalidated
automatically once it expires.

## What you can see

What you're allowed to do is controlled by permissions your administrator
assigned (via your group and role memberships) — not everyone sees the
same thing. If a page says "Access denied," it means your account doesn't
currently have the permission that page requires; ask your administrator
if you believe that's wrong.
