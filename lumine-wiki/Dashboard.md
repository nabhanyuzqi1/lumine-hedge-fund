---
title: "LLM Maintenance Dashboard"
aliases: ["Dashboard"]
type: moc
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#dashboard", "#meta"]
---

# LLM Maintenance Dashboard

Dashboard otomatis untuk tracking backlog maintenance vault.

## ⚠️ LLM Maintenance Backlog

```dataview
TABLE status, updated
FROM "02_Wiki"
WHERE status = "conflict" OR contains(file.tasks.text, "PENDING UPDATE") OR contains(file.tasks.text, "DATA CONTRADICTION")
```

## 📊 Vault Statistics

### Pages by Status

```dataview
TABLE length(rows) as "Count"
FROM "02_Wiki"
GROUP BY status
```

### Pages by Type

```dataview
TABLE length(rows) as "Count"
FROM "02_Wiki"
GROUP BY type
```

### Recently Created

```dataview
TABLE created, type, status
FROM "02_Wiki"
SORT created DESC
LIMIT 10
```

## 🔗 Unresolved Links

Check links that point to non-existent pages (Dataview plugin required for auto-detection via `dv.app.metadataCache.unresolvedLinks`).

## 📋 Tasks

- [ ] Review `01_Raw_Sources/` for new documents to ingest
- [ ] Resolve any `> [!bug] DATA CONTRADICTION` blocks
- [ ] Update `> [!warning] PENDING UPDATE` pages
- [ ] Create stub pages for unresolved wikilinks
