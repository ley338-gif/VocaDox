# Admin: recording policy

## Consent notice

`Settings.recording_consent_notice`
(`VOCADOX_RECORDING_CONSENT_NOTICE`) is the text shown to users before a
browser recording starts. Default: "Confirm that required
consent/authorization for this recording has been obtained." Configurable
per deployment, but **displaying any notice does not itself satisfy your
organization's legal consent obligations** — see
`docs/security/recording-privacy.md`. Update this text to match your
organization's actual policy/legal requirements; VocaDox does not
validate or enforce that the text says anything specific.

## Permissions

Who can record/upload is governed by ordinary RBAC permissions
(`conversation:record`, `conversation:upload`), assignable per role like
any other permission — see `docs/architecture/conversations.md`,
"Permissions." There is no separate recording-specific admin toggle beyond
standard role/permission assignment.

## Browser support

Recording requires `getUserMedia` + `MediaRecorder`. If your organization
has a browser-support policy, communicate it alongside VocaDox's own
tested set (current Chrome/Edge, Firefox — see `docs/user/recording.md`);
Safari support is inconsistent and not currently claimed.
