# JailWatch VMS 2.1.0 — login and two-way perimeter monitoring

This Windows pilot adds:

- First-run administrator enrollment, named sign-in, administrator/operator roles, account disabling and password changes. No default password.
- Automatic camera-wall reconnection after sign-in; multi-camera views and recording from version 2.0 remain available.
- Outside-to-inside and inside-to-outside suspected crossings, with independent directional cooldowns and direction in event evidence/export.
- Optional fence-watch polygon and sustained-person warning; launch-area/time association raises review priority without asserting intent.
- Additional temporal bird checks, sampled launch/flight crops and source-time path matching. Recognized birds veto throw notifications even when a person is nearby.
- Optional silent review of unknown crossings, distinct from audible alarms.

Download `JailWatchVMS-Setup-2.1.0-x64.exe`, or extract all of `JailWatchVMS-2.1.0-Windows-x64.zip`. Python and the CPU model runtime are included. The installer is unsigned. Follow `START_HERE.md` and the bundled guides.

On upgrade, the first launch asks you to create an administrator. Existing camera/evidence files are retained. VMS cameras without a saved direction setting now use both directions; verify each camera's zones and settings before live use. Drawing the optional FENCE zone is required for the new proximity warning.

The release workflow runs source tests, builds the native Windows application, exercises enrollment/sign-in, four simulated RTSP views, bundled CPU inference, recording/playback and an operator alarm, then tests the installed copy. Read the attached validation JSON files for the outcome. Synthetic rule tests verify two-way crossings, context, silent review and bird vetoes; these are not measurements of real-world AI accuracy.

The generic model is unchanged. There is no claim of zero bird false alarms, universal CCTV compatibility, ONVIF certification or superiority to another VMS. Up to 16 live views and up to eight configured AI workers are software limits; AI defaults to two. Validate actual capacity and accuracy on your server. Signing out or closing the desktop app stops recording/alerts; use Windows lock to keep processing while securing the workstation.
