# MediScout

Monitor new Medicover appointments with MediScout, designed to work with the latest authentication system (as of December 2024).

- Automate appointment monitoring
- Stateful with sqlite. Don't get notified about already seen appointments
- Supports notifications via telegram.
- Easy setup and automation with Docker. Can be run on k8s

---

## Configuration (One-Time Setup)
1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Fill in the `.env` file with your credentials.
3. Run the following command to build the Docker image:
    ```bash
    docker build --rm -t mediscout .
    ```
---

## Basic Usage

### Running
MediScout can be run in following ways:
- One of searches that can be automated with cron
- Long-running container

### Running a container
MediScout can be run simply in docker like:
```bash
docker run --rm --env-file=.env -v /your/mount/path:/app/db mediscout start
```
Or in kubernetes. Example deployment: [here](example-deployment.yaml)


After running a container mediscout will check availability for all watches that were created.

Below commands can be run as one-of containers or after ssh-ing into running Mediscout container with `python mediczuwacz.py rest of command`
To check active watches run:
```bash
docker run --rm --env-file=.env -v /your/mount/path:/app/db mediscout list-watches
```

To add new watch run:
```bash
docker run --rm --env-file=.env -v /your/mount/path:/app/db mediscout add-watch -r 207 -s 19054 -f "2025-01-04"
```

To remove watch run (ID can be taken from list-watches command):
```bash
docker run --rm --env-file=.env -v /your/mount/path:/app/db mediscout remove-watch -i 1
```

### One-of runs with Parameters
#### Example 1: Search for an Appointment
For a pediatrician (`Pediatra`) in Warsaw:
```bash
docker run --rm --env-file=.env mediscout find-appointment -r 204 -s 132 -f "2024-12-11"
```

#### Example 2: Search and Send Notifications
To search and send notifications via Telegram:
```bash
docker run --rm --env-file=.env mediscout find-appointment -r 204 -s 132 -f "2024-12-11" -n telegram -t "Pediatra"
```

#### Example 3: Search for an Appointment in particular Clinic (Łukiska - 49284)
To search and send notifications via Telegram:
```bash
docker run --rm --env-file=.env mediscout find-appointment -r 204 -s 132 -f "2024-12-11" -c 49284 -n telegram -t "Pediatra"
```

#### Example 4: Search for a Specific Doctor
Use -d param:
```bash
docker run --rm --env-file=.env mediscout find-appointment -r 204 -s 132 -d 394 -f "2024-12-16"
```

---

## How to Know IDs?
In commands, you use different IDs (e.g., `204` for Warsaw). How do you find other values?

Run the following commands:

- To list available regions:
  ```bash
  docker run --rm --env-file=.env mediscout list-filters regions
  ```

- To list available specialties:
  ```bash
  docker run --rm --env-file=.env mediscout list-filters specialties
  ```

- To list doctors for a specific region and specialty:
  ```bash
  docker run --rm --env-file=.env mediscout list-filters doctors -r 204 -s 132
  ```

---

## Telegram Notifications
Use the Telegram app to send notifications to your channel by following these steps:

### Step 1: Create a Telegram Bot
Follow this guide to create a Telegram Bot: [Create Telegram Bot](https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a).

### Step 2: Update `.env`
Add the following lines to your `.env` file:
```bash
NOTIFIERS_TELEGRAM_CHAT_ID=111222333
NOTIFIERS_TELEGRAM_TOKEN=mySecretToken
```

### Step 3: Run the Command
Run the following command to send Telegram notifications:
```bash
docker run --rm --env-file=.env mediscout find-appointment -r 204 -s 132 -f "2024-12-11" -n telegram -t "Pediatra"
```

---

## Changelog

### v0.1 - 2025-01-11
- Repository initialized;

---

## Acknowledgements
Special thanks to the following projects for their inspiration:
- [apqlzm/medihunter](https://github.com/apqlzm/medihunter)
- [atais/medibot](https://github.com/atais/medibot)
- [SteveSteve24/Mediczuwacz](https://github.com/SteveSteve24/MediCzuwacz)


