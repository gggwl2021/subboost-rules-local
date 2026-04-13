# subboost-rules-local

Local rule repository with a SubBoost-compatible directory layout.

## Layout

```text
geo/
  geosite/
    category-ads-all.mrs
    private.mrs
    geolocation-cn.mrs
    geolocation-!cn.mrs
    category-ai-chat-!cn.mrs
    openai.mrs
    anthropic.mrs
    cn.mrs
  geoip/
    private.mrs
    cn.mrs
```

## SubBoost Base URL

Once pushed to GitHub, use the repository raw `geo` directory as the base URL:

```text
https://raw.githubusercontent.com/<owner>/<repo>/main/geo
```

Then SubBoost can keep using relative paths such as:

```yaml
rule-providers:
  category-ads-all: {type: http, behavior: domain, url: /geosite/category-ads-all.mrs, path: ./ruleset/category-ads-all.mrs, interval: 86400, format: mrs}
  private: {type: http, behavior: domain, url: /geosite/private.mrs, path: ./ruleset/private.mrs, interval: 86400, format: mrs}
  private-ip: {type: http, behavior: ipcidr, url: /geoip/private.mrs, path: ./ruleset/private-ip.mrs, interval: 86400, format: mrs}
  geolocation-cn: {type: http, behavior: domain, url: /geosite/geolocation-cn.mrs, path: ./ruleset/geolocation-cn.mrs, interval: 86400, format: mrs}
  cn-ip: {type: http, behavior: ipcidr, url: /geoip/cn.mrs, path: ./ruleset/cn-ip.mrs, interval: 86400, format: mrs}
  geolocation-!cn: {type: http, behavior: domain, url: /geosite/geolocation-!cn.mrs, path: ./ruleset/geolocation-!cn.mrs, interval: 86400, format: mrs}
  category-ai-chat-!cn: {type: http, behavior: domain, url: /geosite/category-ai-chat-!cn.mrs, path: ./ruleset/category-ai-chat-!cn.mrs, interval: 86400, format: mrs}
  openai: {type: http, behavior: domain, url: /geosite/openai.mrs, path: ./ruleset/openai.mrs, interval: 86400, format: mrs}
  anthropic: {type: http, behavior: domain, url: /geosite/anthropic.mrs, path: ./ruleset/anthropic.mrs, interval: 86400, format: mrs}
```

## Strategy

- Mirror stable base rule-sets from `MetaCubeX/meta-rules-dat` for:
  - `category-ads-all`
  - `private`
  - `private-ip`
  - `geolocation-cn`
  - `cn-ip`
  - `geolocation-!cn`
  - `cn`
- Build fresher AI rule-sets locally for:
  - `category-ai-chat-!cn`
  - `openai`
  - `anthropic`

## Upstream AI Sources

- `teslaproduuction/ClashDomainsList`
- `jimmyzhou521-stack/ai-projects-proxy-rules`

## Build

Run:

```bash
python3 scripts/update_rules.py
```

The script will:

1. Download mirrored base `.mrs` assets.
2. Refresh AI source snapshots from the selected upstream repositories.
3. Merge and normalize AI domain rules for `openai`, `anthropic`, and `category-ai-chat-!cn`.
4. Generate a minimal `geosite.dat` and custom Mihomo `.mrs` files directly in Python.

## Notes

- Base rule-sets are mirrored from `MetaCubeX/meta-rules-dat`.
- AI rule-sets are refreshed from newer upstream text sources and rebuilt locally.
- Generated debug snapshots are placed in `build/` and are ignored by Git.
- The builder requires `zstd` to be available in `PATH`.
