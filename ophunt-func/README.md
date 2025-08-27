# ophunt-func

PowerShell Azure Function for **ophunt**, running locally with [Azurite](https://github.com/Azure/Azurite) as the Azure Storage emulator.  
This project lets you expose your `pull_data.ps1` script through an HTTP endpoint for local development.

---

## Project Structure

```
ophunt-func/
├─ host.json
├─ local.settings.json        # local secrets/config (ignored by git)
├─ profile.ps1
├─ requirements.psd1
└─ ophunt/
   ├─ function.json
   ├─ run.ps1
   └─ pull_data.ps1           # your custom script
```

---

## Prerequisites

- **WSL Ubuntu / Linux**
- [.NET SDK 8.0+](https://dotnet.microsoft.com/en-us/download)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- [Node.js 20+](https://nodejs.org/) (required for Azurite)  
  Install with [nvm](https://github.com/nvm-sh/nvm) for easiest setup.

Install Azurite globally:
```bash
npm install -g azurite
```

---

## Local Settings

Create `local.settings.json` in the project root:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "powershell",
    "FINNHUB_TOKEN": "REPLACE_WITH_YOUR_TOKEN"
  }
}
```

- `AzureWebJobsStorage` → points Functions runtime to Azurite  
- `FINNHUB_TOKEN` → required for your `pull_data.ps1` script  

This file is ignored by git (`.gitignore`).

---

## Running Locally

1. **Start Azurite** (in a separate terminal):

   ```bash
   azurite --location ~/.azurite --silent
   ```

   Test it:
   ```bash
   curl -sI http://127.0.0.1:10000/devstoreaccount1 | head -n1
   # HTTP/1.1 400 Bad Request  ← means Azurite is listening
   ```

2. **Start the Function Host** (from project root):

   ```bash
   cd ophunt-func
   func start
   ```

   You should see:
   ```
   Functions:

           ophunt: [GET,POST] http://localhost:7071/api/ophunt
   ```

---

## Usage

### GET (default JSON)
```bash
curl "http://localhost:7071/api/ophunt?symbol=GME&limit=10&chunkSize=5&dte=21&dateCode=250926"
```

### GET (raw text passthrough)
```bash
curl "http://localhost:7071/api/ophunt?symbol=GME&limit=10&chunkSize=5&dte=21&dateCode=250926&format=txt"
```

### POST (JSON body)
```bash
curl -X POST "http://localhost:7071/api/ophunt"   -H "Content-Type: application/json"   -d '{"symbol":"GME","limit":10000,"chunkSize":50,"dte":21,"dateCode":"250926","format":"txt"}'
```

---

## Editing & Restarting

- After modifying `run.ps1` or `pull_data.ps1`, restart the Functions host:
  ```bash
  pkill -f "func host start" 2>/dev/null || true
  func start
  ```
- No need to restart Azurite unless you closed it or changed ports.

---

## Troubleshooting

- **No job functions found**  
  → Run `func start` from project root (`host.json`), not inside `ophunt/`.

- **Dotnet is required for PowerShell Functions**  
  → Install .NET SDK 8.0+.

- **Azurite port in use**  
  ```bash
  pkill -f azurite
  azurite --location ~/.azurite --silent --blobPort 10010 --queuePort 10011 --tablePort 10012
  ```

  Then update `AzureWebJobsStorage` with a custom connection string.

---

## Notes

- `FINNHUB_TOKEN` is injected via `local.settings.json` (never commit it).  
- Azurite artifacts and secrets are already ignored in `.gitignore`.  
- Logs from your script (`Write-Host`) will appear in the Functions host console.

---
