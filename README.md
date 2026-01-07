# Alldebrid/Torbox Tinfoil Server

A self-hosted Tinfoil server that serves Nintendo Switch game files directly from your Alldebrid account.

## About

The Alldebrid Tinfoil Server allows you to easily set up your own custom Tinfoil shop of curated items from your Alldebrid magnet downloads. This allows you to use Alldebrid as a repository rather than storing your files on your own server.

> [!IMPORTANT]
> *This project does not allow piracy or condone it in any way. This is meant to be used with games you own and have the rights to.*

### Credits

This project is based on [torbox-tinfoil-server](https://github.com/TorBox-App/torbox-tinfoil-server) by TorBox. Thank you to the TorBox team for creating the original implementation!

## How It Works

1. Upload magnet links or torrent files to your Alldebrid account (via their website or API)
2. Alldebrid downloads and caches the content on their servers
3. This server fetches the list of **ready** magnets from your Alldebrid account
4. It filters for Switch-compatible files (.nsp, .nsz, .xci, .xcz)
5. Tinfoil on your Nintendo Switch downloads directly from Alldebrid's servers

## Requirements

1. An Alldebrid account with an active subscription. Sign up [here](https://alldebrid.com/).
2. A server or computer that can run Python 3.10+ or Docker.
3. A Nintendo Switch with Tinfoil installed.

## Environment Variables

To run this project, you will need to add the following environment variables to your `.env` file.

| Variable | Description | Default |
|----------|-------------|---------|
| `PROVIDER` | Choose backend: `alldebrid` or `torbox`. | `alldebrid` |
| `ALLDEBRID_API_KEY` | Your Alldebrid API key. Required if PROVIDER is `alldebrid`. | - |
| `TORBOX_API_KEY` | Your TorBox API key. Required if PROVIDER is `torbox`. | - |
| `AUTH_USERNAME` | The login username for Tinfoil authentication. | `admin` |
| `AUTH_PASSWORD` | The login password for Tinfoil authentication. | `adminadmin` |
| `PORT` | The port that the server will run on. | `8000` |
| `SWITCH_UID` | Lock the server to a specific Switch UID. Leave blank to allow any Switch. | - |

## Features (v1.1.0)
- **Multi-Provider Support:** Switch between Alldebrid and Torbox easily. Torbox support has been fully restored and integrated.
- **Partial Content Support (`Range` Headers):** Fixes Tinfoil freezing and validation errors. This optimization is now applied to **both** Alldebrid and Torbox connections.
- **Smart Redirects (307):** Preserves headers during 302/307 redirects for maximum compatibility.
- **VPS Block Detection:** Automatically detects and alerts if your VPS IP is blocked by the provider.
- **URL Unquoting:** Fixes "Failed to open NSP" errors caused by double-encoded links.

## Connection Details

Configure Tinfoil with these settings:

| Setting | Value |
|---------|-------|
| **Protocol** | `http` (or `https` if using a reverse proxy) |
| **Host** | Your server's IP address (e.g., `192.168.1.2`) |
| **Port** | `8000` (or your custom `PORT`) |
| **Path** | Leave blank |
| **Username** | Your `AUTH_USERNAME` (default: `admin`) |
| **Password** | Your `AUTH_PASSWORD` (default: `adminadmin`) |
| **Title** | `Alldebrid Tinfoil Server` |
| **Enabled** | `YES` |

## Running with Docker (Recommended)

### Using Docker Run

```bash
docker run -d \
    -p 8000:8000 \
    -e ALLDEBRID_API_KEY=<YOUR_API_KEY> \
    -e AUTH_USERNAME=admin \
    -e AUTH_PASSWORD=adminadmin \
    ghcr.io/<your-username>/alldebrid-tinfoil-server:latest
```

### Using Docker Compose

```yaml
name: alldebrid-tinfoil-server
services:
  alldebrid-tinfoil-server:
    image: ghcr.io/<your-username>/alldebrid-tinfoil-server:latest
    ports:
      - 8000:8000
    environment:
      - ALLDEBRID_API_KEY=<YOUR_API_KEY>
      - AUTH_USERNAME=admin
      - AUTH_PASSWORD=adminadmin
    restart: unless-stopped
```

## Running Locally (Without Docker)

1. Make sure you have Python 3.10+ installed.

2. Clone this repository:
```bash
git clone https://github.com/<your-username>/alldebrid-tinfoil-server.git
cd alldebrid-tinfoil-server
```

3. Create a `.env` file:
```bash
cp .env.example .env
```

4. Edit the `.env` file and add your Alldebrid API key.

5. Install the requirements:
```bash
pip install -r requirements.txt
```

6. Run the server:
```bash
python main.py
```

7. Connect from Tinfoil using the connection details above.

## Building Docker Image Locally

```bash
docker build -t alldebrid-tinfoil-server .
docker run -d -p 8000:8000 -e ALLDEBRID_API_KEY=<YOUR_KEY> alldebrid-tinfoil-server
```

## Contributing

Contributions are always welcome!

Please make sure to follow [Conventional Commits](https://conventionalcommits.org/) when creating commit messages.

## License

This project is licensed under the same license as the original torbox-tinfoil-server project.
