# Streaming Path Authentication Configuration

IPTV Proxy v2 includes a **Proxy Hostname** setting that lets you specify a custom domain for generated streaming URLs. Combined with path-based authentication in your reverse proxy, this allows you to:

- Keep admin UI secured behind authentication
- Expose streaming endpoints publicly for media players
- Use a clean, custom domain for streaming URLs

## Configuration

### 1. Set Proxy Hostname

In the Settings page (`/settings`):
1. Navigate to **Proxy Configuration**
2. Enter your streaming domain (e.g., `streams.example.com`)
3. Click **Save Proxy Settings**

All generated M3U playlists and EPG files will now use this hostname in their URLs.

### 2. Configure Reverse Proxy

Your reverse proxy should:
- Route streaming paths (`/playlist`, `/epg`, `/stream`, `/image`) **without** authentication
- Route admin paths (`/`, `/accounts`, `/filters`, `/api`, etc.) **with** authentication

## Traefik Configuration

### Option A: Single Domain with Path-Based Auth

Most straightforward - use one domain with different auth rules per path:

```yaml
# docker-compose.yml
services:
  iptv-proxy:
    image: your-iptv-proxy-image
    labels:
      - "traefik.enable=true"
      
      # Admin router (requires auth for non-streaming paths)
      - "traefik.http.routers.iptv-admin.rule=Host(`proxy.example.com`) && !PathPrefix(`/playlist`, `/epg`, `/stream`, `/image`)"
      - "traefik.http.routers.iptv-admin.middlewares=auth@file"
      - "traefik.http.routers.iptv-admin.entrypoints=websecure"
      - "traefik.http.routers.iptv-admin.tls.certresolver=letsencrypt"
      
      # Streaming router (public, no auth)
      - "traefik.http.routers.iptv-streams.rule=Host(`proxy.example.com`) && PathPrefix(`/playlist`, `/epg`, `/stream`, `/image`)"
      - "traefik.http.routers.iptv-streams.entrypoints=websecure"
      - "traefik.http.routers.iptv-streams.tls.certresolver=letsencrypt"
      
      # Both route to same service
      - "traefik.http.services.iptv.loadbalancer.server.port=8000"
```

**Proxy Hostname Setting:** Leave empty or set to `proxy.example.com`

### Option B: Separate Domains

Use different domains for admin and streaming:

```yaml
# docker-compose.yml
services:
  iptv-proxy:
    labels:
      - "traefik.enable=true"
      
      # Admin domain (with auth)
      - "traefik.http.routers.iptv-admin.rule=Host(`admin.internal.com`)"
      - "traefik.http.routers.iptv-admin.middlewares=auth@file"
      - "traefik.http.routers.iptv-admin.entrypoints=websecure"
      - "traefik.http.routers.iptv-admin.tls.certresolver=letsencrypt"
      
      # Streaming domain (public, no auth)
      - "traefik.http.routers.iptv-streams.rule=Host(`streams.example.com`)"
      - "traefik.http.routers.iptv-streams.entrypoints=websecure"
      - "traefik.http.routers.iptv-streams.tls.certresolver=letsencrypt"
      
      # Both route to same service
      - "traefik.http.services.iptv.loadbalancer.server.port=8000"
```

**Proxy Hostname Setting:** Set to `streams.example.com`

### Auth Middleware Example

In your Traefik configuration file:

```yaml
# traefik.yml or dynamic config
http:
  middlewares:
    auth:
      basicAuth:
        users:
          - "admin:$apr1$hash..."  # htpasswd format
        # Or use forwardAuth for SSO
```

## nginx Configuration

```nginx
# Admin location (with auth)
location / {
    auth_basic "Admin Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://iptv-proxy:8000;
}

# Streaming paths (no auth)
location ~ ^/(playlist|epg|stream|image) {
    proxy_pass http://iptv-proxy:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## Security Considerations

1. **Rate Limiting** - Apply rate limits to streaming paths to prevent abuse:
   ```yaml
   - "traefik.http.middlewares.ratelimit.ratelimit.average=100"
   - "traefik.http.middlewares.ratelimit.ratelimit.burst=50"
   - "traefik.http.routers.iptv-streams.middlewares=ratelimit"
   ```

2. **Geographic Restrictions** - Consider IP whitelisting or geo-blocking on streaming router

3. **URL Security** - Stream URLs contain predictable IDs (account_id, stream_id). They are not secret.

4. **HTTPS Only** - Always use HTTPS for both admin and streaming endpoints

5. **Monitoring** - Watch for unusual traffic patterns on public streaming paths

## Testing

After configuration:

1. **Admin Access**: Visit your admin domain/path - should require authentication
2. **Streaming Access**: Try accessing `/playlist/1.m3u` - should work without auth
3. **URL Check**: Generate a playlist and verify it uses your custom hostname
4. **Media Player**: Test M3U in VLC/Plex/etc. - streams should work without prompting for auth

## Troubleshooting

### URLs still use wrong hostname
- Check Settings → Proxy Configuration
- Ensure hostname is saved correctly
- Clear browser cache
- Regenerate playlists

### Authentication required for streams
- Check your reverse proxy path rules
- Verify streaming paths are in the "no auth" router
- Check middleware order in Traefik

### Streams not accessible
- Verify reverse proxy is routing to correct port (8000)
- Check Docker network connectivity
- Review reverse proxy logs

### Getting 404 on streaming paths
- Ensure paths are correct: `/playlist/`, `/epg/`, `/stream/`, `/image/`
- Check that main app is running (not proxy_app)
- Verify port mapping in docker-compose

## Migration from Dual-Port Setup

If upgrading from an earlier version with separate proxy_app:

1. Remove `proxy_app.py` references
2. Update `docker-compose.yml` to single port
3. Update reverse proxy config to use path-based routing
4. Restart containers
5. Test both admin and streaming access
