# Amazon MCP

Serveur MCP (Model Context Protocol) qui scrape **amazon.fr** pour donner à Claude accès aux prix des articles : recherche, fiche produit, suivi de prix avec historique.

## Outils exposés à Claude

| Outil | Description |
|---|---|
| `search_products(query, max_results=10)` | Recherche : titre, prix, ASIN, URL, note, Prime |
| `get_product(url_or_asin)` | Fiche produit : prix, disponibilité, note, avis, vendeur |
| `track_product(url_or_asin, label=None)` | Ajoute un produit au suivi de prix automatique |
| `untrack_product(asin)` | Retire un produit du suivi |
| `list_tracked()` | Produits suivis + dernier prix + variation |
| `get_price_history(asin, days=30)` | Historique de prix (série datée, min/max/actuel) |

Le suivi relève les prix automatiquement toutes les 6 h (jitter aléatoire).

## Architecture

- **Cascade de scraping** : `requests` → `curl_cffi` (empreinte TLS Chrome) → `Playwright` (Chromium headless). Escalade automatique si captcha/blocage détecté. Ajouter un backend = une sous-classe de `ScraperBackend` + une entrée dans `default_backends()` ([engine.py](amazon_mcp/scraping/engine.py)).
- **Parsers** modulaires par type de page ([parsers/](amazon_mcp/parsers/)) — ajouter un pattern de recherche = un parser + un outil MCP.
- **SQLite** (`data/amazon.db`) pour le suivi et l'historique.
- Rate-limit interne (≥ 3 s entre requêtes Amazon) + cache 15 min.

## Développement local

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium   # optionnel : uniquement pour le backend Playwright
.venv/bin/pytest                        # aucun test ne touche le réseau
cp .env.example .env
.venv/bin/python -m amazon_mcp.server   # écoute sur http://0.0.0.0:8321<MCP_SECRET_PATH>
```

## Déploiement sur le VPS (amazon.mcp.mawena.cloud)

Prérequis (déjà en place) : Docker, Nginx, DNS `amazon.mcp.mawena.cloud` → VPS.

### 1. Cloner et configurer

```bash
git clone <repo> /opt/amazon-mcp && cd /opt/amazon-mcp
cp .env.example .env
# Générer le chemin secret et le mettre dans .env :
python3 -c "import secrets; print('/mcp-'+secrets.token_urlsafe(12))"
nano .env   # MCP_SECRET_PATH=/mcp-<le-token-généré>
```

> ⚠️ Le chemin secret est la seule protection d'accès : ne le partage jamais et ne le commite pas.

### 2. Lancer le conteneur

```bash
docker compose up -d --build
# Vérifier :
docker compose logs -f amazon-mcp
```

### 3. Nginx + HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/amazon-mcp
sudo ln -s /etc/nginx/sites-available/amazon-mcp /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d amazon.mcp.mawena.cloud
```

### 4. Tester

```bash
curl -i -X POST https://amazon.mcp.mawena.cloud<MCP_SECRET_PATH> \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Réponse attendue : un événement SSE contenant `"serverInfo":{"name":"Amazon FR"...}`.

## Connecter les clients Claude

L'URL complète du serveur est : `https://amazon.mcp.mawena.cloud<MCP_SECRET_PATH>`

- **claude.ai / app Claude** : Paramètres → Connecteurs → *Ajouter un connecteur personnalisé* → coller l'URL.
- **Claude Code** :
  ```bash
  claude mcp add --transport http amazon https://amazon.mcp.mawena.cloud<MCP_SECRET_PATH>
  ```
- **Claude Desktop** : Paramètres → Connecteurs → *Ajouter un connecteur personnalisé* → coller l'URL.

Ensuite, demande simplement à Claude : *« Cherche-moi le prix d'un clavier mécanique sur Amazon »* ou *« Suis le prix de https://www.amazon.fr/dp/B08N5WRWNW »*.

## Maintenance

```bash
docker compose logs -f          # logs (scraping, scheduler, erreurs)
docker compose up -d --build    # redéployer après un git pull
sqlite3 data/amazon.db 'SELECT * FROM price_history ORDER BY scraped_at DESC LIMIT 10;'
```

## Note légale

Le scraping automatisé est contraire aux CGU d'Amazon. Ce projet est prévu pour un **usage personnel à très faible volume** (rate-limit, cache, horaires avec jitter). À utiliser en connaissance de cause.
