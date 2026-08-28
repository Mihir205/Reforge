# Angular Control Flow Migration Guide

Angular v17 introduced a built-in control flow syntax that replaces the
structural directive approach (`*ngIf`, `*ngFor`, `*ngSwitch`).

---

## 1. `@if` Block — Replaces `*ngIf`

**Simple condition:**
```html
<!-- Legacy -->
<div *ngIf="condition">...</div>

<!-- New -->
@if (condition) {
  <div>...</div>
}
```

**With else:**
```html
<!-- Legacy -->
<div *ngIf="condition; else fallback">...</div>
<ng-template #fallback>fallback content</ng-template>

<!-- New -->
@if (condition) {
  <div>...</div>
} @else {
  fallback content
}
```

**With then/else:**
```html
<!-- Legacy -->
<div *ngIf="condition; then thenTpl; else elseTpl"></div>
<ng-template #thenTpl>then content</ng-template>
<ng-template #elseTpl>else content</ng-template>

<!-- New -->
@if (condition) {
  then content
} @else {
  else content
}
```

**With async pipe (aliased):**
```html
<!-- Legacy -->
<div *ngIf="data$ | async as data">{{ data.name }}</div>

<!-- New -->
@if (data$ | async; as data) {
  <div>{{ data.name }}</div>
}
```

---

## 2. `@for` Block — Replaces `*ngFor`

**Simple:**
```html
<!-- Legacy -->
<li *ngFor="let item of items">{{ item }}</li>

<!-- New — track is REQUIRED -->
@for (item of items; track item) {
  <li>{{ item }}</li>
}
```

**With trackBy:**
```html
<!-- Legacy -->
<li *ngFor="let item of items; trackBy: trackById">{{ item.name }}</li>

<!-- New -->
@for (item of items; track trackById($index, item)) {
  <li>{{ item.name }}</li>
}
```

**With local variables (index, first, last, even, odd, count):**
```html
<!-- Legacy -->
<li *ngFor="let item of items; let i = index; let isFirst = first">

<!-- New -->
@for (item of items; track item; let i = $index; let isFirst = $first) {
  <li>...</li>
}
```

**With empty block:**
```html
@for (item of items; track item.id) {
  <li>{{ item.name }}</li>
} @empty {
  <li>No items found.</li>
}
```

---

## 3. `@switch` Block — Replaces `*ngSwitch`

```html
<!-- Legacy -->
<div [ngSwitch]="status">
  <p *ngSwitchCase="'active'">Active</p>
  <p *ngSwitchCase="'inactive'">Inactive</p>
  <p *ngSwitchDefault>Unknown</p>
</div>

<!-- New -->
@switch (status) {
  @case ('active') { <p>Active</p> }
  @case ('inactive') { <p>Inactive</p> }
  @default { <p>Unknown</p> }
}
```

---

## Key Rules

1. **No semicolons inside conditions**: `@if (a && b)` not `@if (a && b;)`
2. **`track` is mandatory** in `@for` — use `track item` or `track item.id` or a trackBy fn.
3. **Async pipe aliasing**: use semicolon before `as`: `@if (obs$ | async; as val)`.
4. **Braces are part of the syntax**, not separate from the block.
5. **Remove the old ng-template blocks** that were only used for `*ngIf else/then` references.
6. **Local variable names change**: `$index`, `$first`, `$last`, `$even`, `$odd`, `$count`.
