"""
RAG Ingestion Pipeline (Context Stuffing).

Instead of a complex ChromaDB vector store, we just save the 
Angular Control Flow migration guide as a Markdown file.
The retriever will load this entire file into the LLM prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

# A simplified, distilled version of the Angular Control Flow docs
# optimized for LLM consumption.
ANGULAR_DOCS = """# Angular Control Flow Migration Guide

Angular v17 introduced a new built-in control flow syntax.

## 1. `@if` Block
Replaces `*ngIf`.
**Legacy:** `<div *ngIf="condition">...</div>`
**New:** `@if (condition) { <div>...</div> }`

**Legacy with else:**
```html
<div *ngIf="condition; else fallback">...</div>
<ng-template #fallback>fallback</ng-template>
```
**New:**
```html
@if (condition) {
  <div>...</div>
} @else {
  fallback
}
```

**Legacy with async as:**
```html
<div *ngIf="data$ | async as data">...</div>
```
**New:**
```html
@if (data$ | async; as data) {
  <div>...</div>
}
```

## 2. `@for` Block
Replaces `*ngFor`.
**Legacy:** `<div *ngFor="let item of items; trackBy: trackFn; let i = index">...</div>`
**New:**
```html
@for (item of items; track item.id; let i = $index) {
  <div>...</div>
} @empty {
  <div>No items</div>
}
```

## 3. `@switch` Block
Replaces `*ngSwitch`.
**Legacy:**
```html
<div [ngSwitch]="condition">
  <div *ngSwitchCase="value1">...</div>
  <div *ngSwitchDefault>...</div>
</div>
```
**New:**
```html
@switch (condition) {
  @case (value1) { <div>...</div> }
  @default { <div>...</div> }
}
```
"""

def ingest_docs(data_dir: str = "automigrate/rag/data"):
    """Write the migration guide to disk so the agent can read it."""
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    file_path = path / "angular_control_flow.md"
    file_path.write_text(ANGULAR_DOCS, encoding="utf-8")
    
    print(f"Successfully ingested docs into {file_path}")

if __name__ == "__main__":
    ingest_docs()
