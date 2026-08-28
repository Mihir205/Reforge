# Angular Control Flow Migration Guide

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
