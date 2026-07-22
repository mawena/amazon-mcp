# Amazon MCP — Design

**Date :** 2026-07-22
**Objectif :** Serveur MCP distant en Python 3 qui scrape amazon.fr pour donner à Claude accès aux prix des articles. Déployé sur un VPS à `https://amazon.mcp.mawena.cloud`.

## Contexte et contraintes

- Usage personnel, faible volume (quelques requêtes/jour).
- Clients : claude.ai (connecteur), Claude Code, Claude Desktop → transport **HTTP streamable** obligatoire.
- VPS : Nginx installé, Docker disponible, DNS `amazon.mcp.mawena.cloud` déjà pointé.
- Extensibilité exigée : ajouter facilement de nouveaux backends de scraping et de nouveaux types de pages ("patterns de recherche").

## Architecture

```
Claude (claude.ai / Code / Desktop)
        │ HTTPS
        ▼
Nginx (amazon.mcp.mawena.cloud, Let's Encrypt)
        │ proxy_pass → 127.0.0.1:8321
        ▼
Conteneur Docker "amazon-mcp"
 ├── FastMCP (SDK officiel `mcp`, HTTP streamable, chemin secret /mcp-<token>)
 ├── ScraperEngine (cascade de backends)
 ├── SQLite (volume : data/amazon.db)
 └── APScheduler (relevés périodiques)
```

Un seul service (option A retenue) : simple à déployer, SQLite sans serveur de BDD, façade REST ajoutable plus tard si besoin.

## Moteur de scraping en cascade

Interface commune `ScraperBackend.fetch(url) -> str` (HTML). Backends essayés dans l'ordre, escalade si échec réseau, HTTP ≠ 200, ou page captcha/robot détectée :

1. **RequestsBackend** — requests + headers réalistes (le plus léger)
2. **CurlCffiBackend** — curl_cffi, empreinte TLS Chrome
3. **PlaywrightBackend** — Chromium headless (dernier recours)

Ajout d'un backend = une classe + une entrée dans la liste ordonnée.

Anti-blocage :
- User-Agent Chrome fr-FR rotatif, `Accept-Language: fr-FR`
- Rate limit interne : ≥ 3 s entre deux requêtes vers Amazon
- Cache mémoire des résultats : TTL 15 min
- Détection captcha : marqueurs connus des pages robot Amazon

## Parsers

Modules séparés avec interface commune, un par type de page :
- `ProductParser` — page produit : titre, prix, devise, disponibilité, note, nb d'avis, vendeur
- `SearchParser` — page résultats : liste (titre, prix, ASIN, URL, note, Prime)

Ajout d'un pattern de recherche = un parser + un outil MCP.

## Outils MCP

| Outil | Paramètres | Retour |
|---|---|---|
| `search_products` | `query`, `max_results` (déf. 10) | liste : titre, prix, ASIN, URL, note, Prime |
| `get_product` | `url_or_asin` | prix, titre, disponibilité, note, nb d'avis, vendeur |
| `track_product` | `url_or_asin`, `label` optionnel | ajoute au suivi |
| `untrack_product` | `asin` | retire du suivi |
| `list_tracked` | — | articles suivis + dernier prix + variation |
| `get_price_history` | `asin`, `days` (déf. 30) | série de prix datés + min/max/actuel |

## Données & scheduling

SQLite `data/amazon.db` (volume Docker) :

- `tracked_products(asin PK, label, url, created_at)`
- `price_history(id PK, asin FK, price, currency, in_stock, scraped_at)`

APScheduler : relevé des articles suivis toutes les **6 h** avec jitter aléatoire, délai 5–15 s entre articles.

## Gestion d'erreurs

- Cascade épuisée → erreur MCP claire : « Amazon bloque actuellement, réessaie plus tard. »
- ASIN/URL invalide → message explicite.
- Produit indisponible → retourné avec `in_stock: false`, prix absent toléré.
- Le scheduler note l'échec et réessaie au cycle suivant (pas de retry agressif).

## Déploiement

- `Dockerfile` : Python 3.12 slim + Chromium (Playwright). `docker-compose.yml` : port `127.0.0.1:8321:8321`, volume `./data`.
- Nginx : vhost `amazon.mcp.mawena.cloud` → `proxy_pass http://127.0.0.1:8321`, `proxy_buffering off` (streaming SSE).
- HTTPS : `certbot --nginx`.
- Sécurité : chemin MCP secret `/mcp-<token>` généré à l'installation, stocké dans `.env`. Pas d'OAuth (usage perso).
- README : étapes VPS complètes + ajout du connecteur dans les 3 clients Claude.

## Tests

- Parsers testés sur **fixtures HTML** enregistrées (aucune requête réseau en test).
- Cascade testée avec mocks (backend 1 échoue → backend 2 prend le relais).
- Outils MCP testés en mémoire via le client de test du SDK.

## Hors périmètre (YAGNI)

- OAuth, multi-utilisateurs, proxies rotatifs payants, façade REST, autres marketplaces qu'amazon.fr, alertes de prix (notification) — ajoutables plus tard.

## Note légale

Le scraping viole les CGU d'Amazon. Usage personnel à très faible volume : risque pratique minime, design volontairement discret (rate limit, cache, jitter). Assumé par l'utilisateur.
