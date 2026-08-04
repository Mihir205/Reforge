# Angular Control Flow Migration Guide

The new `@if`, `@else`, `@for`, and `@switch` syntax provides a built-in, intuitive, and better performing way to handle control flow in Angular templates compared to the legacy structural directives `*ngIf`, `*ngFor`, and `[ngSwitch]`.

## `@if` Block
The `@if` block replaces `*ngIf`.
Legacy:
```html
<div *ngIf="loggedIn; else anonymousUser">
  The user is logged in
</div>
<ng-template #anonymousUser>
  The user is not logged in
</ng-template>
```
New:
```html
@if (loggedIn) {
  <div>The user is logged in</div>
} @else {
  The user is not logged in
}
```

## `@for` Block
The `@for` block replaces `*ngFor`. It requires a `track` expression.
Legacy:
```html
<ul>
  <li *ngFor="let item of items; trackBy: trackById">
    {{ item.name }}
  </li>
</ul>
```
New:
```html
<ul>
  @for (item of items; track item.id) {
    <li>{{ item.name }}</li>
  } @empty {
    <li>No items found</li>
  }
</ul>
```
Implicit variables available in `@for`: `$index`, `$first`, `$last`, `$even`, `$odd`, `$count`.

## `@switch` Block
The `@switch` block replaces `[ngSwitch]`.
Legacy:
```html
<div [ngSwitch]="accessLevel">
  <admin-dashboard *ngSwitchCase="'admin'"></admin-dashboard>
  <moderator-dashboard *ngSwitchCase="'moderator'"></moderator-dashboard>
  <user-dashboard *ngSwitchDefault></user-dashboard>
</div>
```
New:
```html
@switch (accessLevel) {
  @case ('admin') { <admin-dashboard/> }
  @case ('moderator') { <moderator-dashboard/> }
  @default { <user-dashboard/> }
}
```

## Async Pipe with `@if`
When migrating `*ngIf="data$ | async as data"`, use `@if`:
```html
@if (data$ | async; as data) {
  <user-profile [data]="data"></user-profile>
}
```
Notice the semicolon separating the condition and the aliasing `as` statement.
