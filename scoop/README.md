# Scoop Bucket — AI Helpdesk Assistant

This directory contains the [Scoop](https://scoop.sh) manifest for AI Helpdesk Assistant.

## Install via Scoop

```powershell
# Add this repo as a custom bucket
scoop bucket add assistant https://github.com/gyzhoe/assistant-v2 -p scoop

# Install
scoop install ai-helpdesk-assistant
```

## Updating the hash

The `hash` field in `ai-helpdesk-assistant.json` must be the SHA256 of the installer `.exe`.
To recompute it after a new release:

```powershell
$url = "https://github.com/gyzhoe/assistant-v2/releases/download/v<VERSION>/AIHelpdeskAssistant-Setup-<VERSION>.exe"
(Invoke-WebRequest $url -UseBasicParsing).RawContentStream | Get-FileHash -Algorithm SHA256 | Select-Object -ExpandProperty Hash
```

Or using `scoop`'s built-in helper after bumping the version:

```powershell
scoop-hash https://github.com/gyzhoe/assistant-v2/releases/download/v<VERSION>/AIHelpdeskAssistant-Setup-<VERSION>.exe
```

Then update the `version` and `hash` fields in `ai-helpdesk-assistant.json` and commit.
