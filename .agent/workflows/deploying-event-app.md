# Event App Deployment Guide

This workflow covers deployment for both **apps/cms** (Payload CMS) and **apps/web** (TanStack Start).

## Critical Learnings

⚠️ **DO NOT create `apps/web/wrangler.toml`** - The web app uses Cloudflare Workers Builds (auto-deploy from GitHub), NOT local wrangler deployment!

✅ **Keep version overrides** in root `package.json` - These ensure dependency stability

✅ **Enforce Node v20** - Cloudflare's default environment (v22) is incompatible with the build tools. Use `.nvmrc`.

## Pre-Deployment Checklist

1. [ ] All changes committed to git
2. [ ] Tests passing (if applicable)
3. [ ] Version overrides intact in root `package.json`
4. [ ] `.nvmrc` exists in root with content `20.19.6`
5. [ ] `apps/web/package.json` build script includes memory optimization: `NODE_OPTIONS="--max-old-space-size=4096"`
6. [ ] NO `apps/web/wrangler.toml` file exists

## Deployment Methods

### Option A: Auto-Deploy (Both Apps) ✅ RECOMMENDED

**When to use**: Regular deployments, both CMS and web changes

**Steps**:

```bash
# 1. Commit all changes
cd /home/ubuntu/event-app
git add -A
git commit -m "descriptive message"

# 2. Push to GitHub
git push origin main

# 3. Wait 2-3 minutes for Cloudflare Workers Builds

# 4. Verify deployment
# - CMS: https://event-app.brant-olson.workers.dev
# - Web: https://event-app-web.brant-olson.workers.dev
```

**What happens**:

- GitHub push triggers Cloudflare Workers Builds
- Cloudflare builds both `apps/cms` and `apps/web`
- Automatic deployment to production

### Option B: CMS-Only Deployment

**When to use**: Database migrations, CMS-only changes

**Steps**:

```bash
cd apps/cms

# Run migrations if needed
pnpm run payload migrate

# Deploy
pnpm run deploy
```

## Post-Deployment Verification

### 1. Check Deployment Status

- View Cloudflare Workers Builds dashboard
- Check for build errors

### 2. Test CMS

```bash
# Navigate to CMS admin
open https://event-app.brant-olson.workers.dev/admin

# Verify:
# - Can log in
# - Collections load
# - Database migrations applied
```

### 3. Test Web App

```bash
# Navigate to web app
open https://event-app-web.brant-olson.workers.dev

# Verify:
# - Page loads
# - User can log in
# - Events display
# - No console errors (F12)
```

### 4. Test Registration Flow (if modified)

1. Navigate to an event detail page
2. Click "Register Now"
3. Verify registration succeeds
4. Check RegistrationAudit collection in CMS admin
5. Test cancellation
6. Verify audit trail updated

## Troubleshooting

### Web App Build Fails (Router Client Error / Exit Code 1)

**Symptom**: Build fails silently or with "Error building router client".

**Cause 1**: Node Version Mismatch (Cloudflare uses v22 by default).
**Fix**: Ensure `.nvmrc` exists in root with `20.19.6`.

**Cause 2**: Out of Memory.
**Fix**: Ensure `apps/web/package.json` has `NODE_OPTIONS="--max-old-space-size=4096"` and sourcemaps are disabled in `app.config.ts`.

### Web App Build Fails (AsyncLocalStorage)

**Symptom**: AsyncLocalStorage bundling error.

**Cause**: `apps/web/wrangler.toml` exists (SHOULD NOT!).

**Fix**:

```bash
cd /home/ubuntu/event-app
rm apps/web/wrangler.toml
git add -A
git commit -m "fix: remove incorrect wrangler.toml"
git push origin main
```

### Dependency Conflicts

**Symptom**: Package installation failures, version mismatches

**Cause**: Version overrides removed from root `package.json`

**Fix**:

```bash
# Restore version overrides in package.json
git checkout HEAD -- package.json
pnpm install
```

## Configuration Reference

### Root package.json (KEEP THESE!)

```json
{
  "engines": {
    "node": ">=20.0.0"
  },
  "pnpm": {
    "overrides": {
      "@tanstack/react-start": "1.120.17",
      "@tanstack/react-router": "1.120.17",
      "vinxi": "0.5.8",
      "vite": "5.4.11"
    }
  }
}
```

### Apps Web (NO wrangler.toml needed!)

```
apps/web/
├── app.config.ts        ✅ TanStack Start config (sourcemap: false)
├── package.json         ✅ Dependencies
└── [NO wrangler.toml]   ⚠️ DO NOT CREATE!
```

## Deployment Checklist Template

```markdown
## Pre-Deploy

- [ ] Changes committed
- [ ] Tests passing
- [ ] No wrangler.toml in apps/web
- [ ] Version overrides intact
- [ ] .nvmrc present (Node v20)

## Deploy

- [ ] `git push origin main`
- [ ] Wait 2-3 min for Cloudflare build
- [ ] Check build logs for errors

## Verify

- [ ] CMS admin accessible
- [ ] Web app loads
- [ ] No console errors
- [ ] Core features working
```

## Quick Reference

| Task             | Command                                           |
| ---------------- | ------------------------------------------------- |
| Deploy both apps | `git push origin main`                            |
| Deploy CMS only  | `cd apps/cms && pnpm deploy`                      |
| Run migrations   | `cd apps/cms && pnpm payload migrate`             |
| Check CMS        | `https://event-app.brant-olson.workers.dev/admin` |
| Check Web        | `https://event-app-web.brant-olson.workers.dev`   |
