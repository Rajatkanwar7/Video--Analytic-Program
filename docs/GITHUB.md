# GitHub download and updates

Destination: `Rajatkanwar7/Video--Analytic-Program`, branch `main`.

The repository contains the application source, Windows launchers, installation guide and automated tests. Camera setup and monitoring run on your CCTV computer.

## Download and run

1. Open [Video--Analytic-Program](https://github.com/Rajatkanwar7/Video--Analytic-Program).
2. Choose **Code → Download ZIP** and extract the download.
3. Install **Python 3.11, 64-bit**, then run **INSTALL_WINDOWS.bat**.
4. Run **START_WINDOWS.bat**, enter the camera source, draw zones and start monitoring. See [installation](INSTALLATION.md) for details.

## Update from your own computer

If you use GitHub Desktop, clone the repository, make changes in that checkout, review the changed files, commit and push. Keep camera configuration, recordings, model weights and alert evidence out of the changes.

For Git users, clone the repository first:

```bash
git clone https://github.com/Rajatkanwar7/Video--Analytic-Program.git
```

Work inside the cloned folder, preserving its Git metadata. From that folder, stage only the application files:

```bash
git add README.md LICENSE .gitignore .github INSTALL_WINDOWS.bat START_WINDOWS.bat config.example.json docs examples install_linux.sh jailwatch pyproject.toml requirements-base.txt requirements.txt scripts tests
git diff --cached --stat
git commit -m "Update JailWatch CCTV monitoring application"
git push origin main
```

Use Git's normal sign-in mechanism on your computer. Do not paste passwords or access tokens into chat. After a successful push, check the repository's [Actions tab](https://github.com/Rajatkanwar7/Video--Analytic-Program/actions) for the Windows/Linux test matrix. If branch rules require a pull request, push a new branch and open a pull request instead of changing the rules.

GitHub publication distributes the program. Run `INSTALL_WINDOWS.bat`, then `START_WINDOWS.bat`, on the CCTV computer to install and use it.
