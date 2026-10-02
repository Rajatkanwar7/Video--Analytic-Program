# Accounts and workstation access

On first start, create the administrator username and a passphrase of 15–128 characters. Usernames have 3–40 lowercase letters, numbers, dots, underscores or hyphens. There is no default account, recovery password or cloud login. On subsequent starts, sign in before viewing the camera inventory, footage or alarms.

In **Settings → Manage operator accounts**, an administrator can create accounts and enable/disable them. Keep a second administrator account for recovery. Users change their own passphrase through **Settings → Change my password**, providing the current password. If an operator forgets a password, an administrator can disable that account and create a replacement account. This version has no email recovery service or administrator password-reset form. Preserve administrator access and a protected backup of the data folder.

| Role | Allowed in the desktop UI |
| --- | --- |
| Operator | View/connect/disconnect cameras; start/stop recording; playback and export; review/acknowledge alerts; change own password. |
| Administrator | All operator actions, camera and zone configuration, ONVIF discovery, model/storage settings, account management. |

Disabling an account or changing its password invalidates its previous sessions. Signing out stops live views, recording and detection for this desktop session and returns to the login window. Closing the app has the same monitoring consequence. Sessions are kept only in process memory and last until sign-out, application exit or account revocation; there is no automatic idle logout that silently stops recording. **Windows lock** can secure an unattended workstation while processing continues.

Authentication uses unique 24-byte salts and PBKDF2-HMAC-SHA256 with 600,000 iterations. Failed sign-ins are recorded without passwords; five failures temporarily lock the username for 30 seconds, increasing to at most five minutes for repeated failures. The state persists across restarts. The local audit table retains the most recent 5,000 account events. Password-storage background: [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). This implementation does not claim FIPS certification.

## Security boundary

This is local operator access control, not a hardened multi-user recording server. The operating-system account and folder permissions protect saved recordings, camera credentials and databases. Anyone who can modify those files or run arbitrary code as that Windows user can bypass application-level controls. Developer CLI/legacy GUI tools are intended for trusted OS users and do not use the VMS login gate. Separate untrusted users with Windows accounts and appropriate permissions; protect backups and exported evidence. There is no HTTP listener, remote login, MFA or directory-service integration.

On upgrade from 2.0, existing cameras/evidence remain in the same data folder. The first operator must enroll an administrator before those devices are accessible in the new GUI. Account storage errors fail closed rather than silently creating a replacement database. Do not delete `accounts.sqlite3` to troubleshoot a normal password error.
