"""Post-GA: persistent cross-conversation speaker/person identity.

A `KnownSpeaker` is an organization-scoped, named identity ("Dr. Müller",
"Yvonne") that a `ConversationParticipant` (app.conversations.models) may
optionally link to — see the module docstring on
alembic/versions/0013_known_speakers.py for why this is metadata-only
(no voice/biometric matching) by deliberate, disclosed choice.
"""
